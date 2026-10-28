"""ImageFX cue player. Audience windows/audio are never armed on startup."""

from __future__ import annotations

import copy
import json
import math
import sys
import time
import uuid
from pathlib import Path


class ShowControlExt:
    def __init__(self, ownerComp):
        self.ownerComp = ownerComp
        source = str(Path(ownerComp.par.Libraryroot.eval()) / "src")
        if source not in sys.path:
            sys.path.insert(0, source)
        from tdimagefx import show
        self.model = show
        self.document = show.validate_show(json.loads(ownerComp.op("show_data").text))
        self.engine = show.CueEngine(self.document["cues"], self)
        self.prepared = {}
        self.tracks = {}
        self.audio = {}
        self.automations = {}
        self._level_fades = {}
        self._mapping_key = None
        self._ui_time = 0.0
        self._busy = False
        self._look_edit = None
        self._look_preview_cue_id = None
        self.StopLiveLook()
        # TD can reinitialize an extension after an operator-tree edit. Keep
        # only a committed, locked image across that same-session event. The
        # startup value and owner id prevent a saved/copied TOE resurrecting it.
        session = ownerComp.fetch("imagefx_saved_preview_session", None, search=False)
        if not isinstance(session, dict):
            session = {}
        preview = ownerComp.op("look_result")
        preview_index = next((i for i, cue in enumerate(self.document["cues"])
                              if session and cue["id"] == session.get("cue")), None)
        keep_preview = (isinstance(session, dict) and session.get("owner") == ownerComp.id
                        and preview_index is not None and preview is not None and preview.isTOP
                        and preview.lock and preview.fetch("imagefx_saved_preview", False, search=False))
        if keep_preview:
            self._look_preview_cue_id = session["cue"]
        ownerComp.par.Lookediting = False
        ownerComp.par.Lookstatus = ("Saved preview (frozen); Recall Look to edit again" if keep_preview else
                                   "No look draft; select a visual cue and Recall Look")
        ownerComp.op("look_preview").par.top = preview.path if keep_preview else "black"
        # A user may save a working TOE during rehearsal. Never resurrect its
        # dynamic media readers/voices when reopening or reinitializing it.
        ownerComp.par.Audioenabled = False
        ownerComp.par.Masterblackout = True
        for node in list(ownerComp.children):
            if node.fetch("imagefx_show_runtime", False, search=False) and not (keep_preview and node == preview):
                node.destroy()
        for track in (1, 2, 3):
            ownerComp.par["Track{}visible".format(track)] = False
            ownerComp.par["Track{}blend".format(track)] = 0
            ownerComp.par["Track{}level".format(track)] = 1
            for side in (0, 1):
                source_top = ownerComp.op("track{}_source{}".format(track, side))
                source_top.lock = False
                source_top.par.top = "black"
        template = ownerComp.op("deck_template")
        template.allowCooking = True
        template.op("fx_rack").initializeExtensions()
        self._default_rack = json.loads(template.op("fx_rack").ExportPreset())
        template.allowCooking = False
        # Allocate the six reusable A/B decks while the show is disarmed. A
        # first GO must not copy thousands of operators on the presentation
        # thread while another track is on air.
        # Finish extension initialization before mutating the copied networks.
        # Warming them inside __init__ caused repeated initialization during
        # preload in native testing, replacing the prepared deck with defaults.
        run("args[0]._warm_decks()", self, delayFrames=1)
        ownerComp.par.Audioenabled = False
        ownerComp.par.Masterblackout = True
        self.SelectCue(preview_index + 1 if keep_preview else 1)
        self.Refresh()

    def _p(self, name):
        return self.ownerComp.par[name].eval()

    def _status(self, message):
        self.ownerComp.par.Status = str(message)[:500]

    def _guard_no_look_edit(self, allow_running=False):
        if self._look_edit is not None and not (allow_running and self.IsRunningLookEdit()):
            raise ValueError("Update Cue, Save as New Cue, or Cancel Changes before continuing")

    def _guard_edit(self, allow_look_edit=False):
        if self.engine.state != "stopped":
            raise ValueError("Stop All before editing/loading the show")
        if not allow_look_edit:
            self._guard_no_look_edit()

    def _save_document_dat(self):
        self.ownerComp.op("show_data").text = json.dumps(self.document, indent=2, allow_nan=False)

    def _validated_cues(self, cues):
        document = self.model.validate_show(dict(self.document, cues=cues))
        if len(json.dumps(document, ensure_ascii=False, allow_nan=False).encode("utf-8")) > self.model.MAX_SHOW_BYTES:
            raise ValueError("Show exceeds 8 MiB")
        return document

    def _replace_cues(self, cues, allow_look_edit=False):
        self._guard_edit(allow_look_edit=allow_look_edit)
        document = self._validated_cues(cues)
        if not allow_look_edit:
            self._clear_look_result()
        self.stop_all()
        self.document = document
        self.engine = self.model.CueEngine(document["cues"], self)
        self._save_document_dat()
        self.Refresh()

    def SelectCue(self, index=None):
        index = int(self._p("Selectedcue") if index is None else index)
        if not self.document["cues"]:
            return
        index = max(1, min(index, len(self.document["cues"])))
        if self._look_edit is not None and not self.IsRunningLookEdit():
            target = self._look_index()
            if index != target + 1:
                self.ownerComp.par.Selectedcue = target + 1
                self._status("Finish or cancel the current look draft before selecting another cue")
                return
        self.ownerComp.par.Selectedcue = index
        cue = self.document["cues"][index - 1]
        if getattr(self, "_look_preview_cue_id", None) not in (None, cue["id"]):
            self._clear_look_result()
        names = {
            "Cuename": "name", "Cuekind": "kind", "Mediafile": "source", "Track": "track",
            "Prewait": "prewait", "Duration": "duration", "Fade": "fade", "Follow": "follow",
            "Postwait": "postwait", "Loop": "loop", "Mediain": "media_in", "Speed": "speed",
            "Gain": "gain", "Hold": "hold", "Target": "target", "Easing": "easing",
            "Cueenabled": "enabled", "Notes": "notes", "Movieaudio": "movie_audio",
            "Blackoutscope": "blackout_scope",
        }
        self._busy = True
        try:
            for parameter, field in names.items():
                self.ownerComp.par[parameter] = cue[field]
            self.ownerComp.par.Timestamp = "" if cue["at"] is None else str(cue["at"])
            self.ownerComp.par.Targetvalue = json.dumps(cue["value"])
        finally:
            self._busy = False
        self.engine.selected = index - 1
        self.Refresh()

    def SelectRow(self, row):
        index = (int(self._p("Cuepage")) - 1) * 12 + row + 1
        if index <= len(self.document["cues"]):
            self.SelectCue(index)

    def CueLabel(self, row, compact=False):
        index = (int(self._p("Cuepage")) - 1) * 12 + row
        if not 0 <= row < 12 or not 0 <= index < len(self.document["cues"]):
            return ""
        cue = self.document["cues"][index]
        state = "ERROR" if cue["id"] in self.engine.errors else "PLAY" if cue["id"] in self.engine.active else "WAIT" if cue["id"] in self.engine.pending else "disabled" if not cue["enabled"] else "ready"
        name = self._row_preview(cue["name"], 24) if compact else cue["name"][:48]
        return "{} {:03d}   {}   | {} / track {} | {}".format(">" if int(self._p("Selectedcue")) == index + 1 else "", index + 1, name, cue["kind"], cue["track"], state)

    @staticmethod
    def _row_preview(value, columns):
        """Single-line display only; never shorten the saved note or cue name."""
        import unicodedata
        text = " ".join(value.split())
        widths = [0 if unicodedata.combining(c) else
                  2 if unicodedata.east_asian_width(c) in {"W", "F"} else 1
                  for c in text]
        if sum(widths) <= columns:
            return text
        used, result = 0, []
        for char, width in zip(text, widths):
            if used + width > columns - 1:
                break
            result.append(char)
            used += width
        return "".join(result).rstrip() + "…"

    def CueRowNotes(self, row):
        """Committed notes aligned with the visible cue page, not the editor buffer."""
        index = (int(self._p("Cuepage")) - 1) * 12 + row
        if not 0 <= row < 12 or not 0 <= index < len(self.document["cues"]):
            return ""
        return self._row_preview(self.document["cues"][index]["notes"], 52) or "—"

    def ApplyCue(self):
        self._guard_edit()
        cues = copy.deepcopy(self.document["cues"])
        index = int(self._p("Selectedcue")) - 1
        if not 0 <= index < len(cues):
            raise ValueError("Select a cue first")
        cue = cues[index]
        names = {
            "Cuename": "name", "Cuekind": "kind", "Mediafile": "source", "Track": "track",
            "Prewait": "prewait", "Duration": "duration", "Fade": "fade", "Follow": "follow",
            "Postwait": "postwait", "Loop": "loop", "Mediain": "media_in", "Speed": "speed",
            "Gain": "gain", "Hold": "hold", "Target": "target", "Easing": "easing",
            "Cueenabled": "enabled", "Notes": "notes", "Movieaudio": "movie_audio",
            "Blackoutscope": "blackout_scope",
        }
        for parameter, field in names.items():
            cue[field] = self._p(parameter)
        cue["at"] = self.model.timestamp(self._p("Timestamp"))
        raw = str(self._p("Targetvalue"))
        try:
            cue["value"] = json.loads(raw)
        except ValueError:
            cue["value"] = raw
        self._replace_cues(cues)
        self.SelectCue(index + 1)
        self._status("Cue saved in workspace; Save Show writes it to disk")

    def SaveCueNotes(self):
        """Metadata-only edit: never restart transport, reload media or commit a look."""
        index = int(self._p("Selectedcue")) - 1
        if not 0 <= index < len(self.document["cues"]):
            raise ValueError("Select a cue first")
        if self._look_edit is not None and not self.IsRunningLookEdit():
            index = self._look_index()
        cues = copy.deepcopy(self.document["cues"])
        cues[index]["notes"] = self._p("Notes")
        validated = self._validated_cues(cues)
        cue = self.document["cues"][index]
        cue["notes"] = validated["cues"][index]["notes"]
        for engine_cue in self.engine.cues:
            if engine_cue["id"] == cue["id"]:
                engine_cue["notes"] = cue["notes"]
        if self._look_edit is not None and self._look_edit["cue"]["id"] == cue["id"]:
            self._look_edit["cue"]["notes"] = cue["notes"]
        self._save_document_dat()
        self.Refresh()
        self._status("Cue notes updated without changing playback or the look. Save Show writes them to disk.")

    def OpenCueNotes(self):
        self.ownerComp.currentPage = "Cue Notes"
        navigation = self.ownerComp.op('inspector_navigation')
        if navigation is not None:
            navigation.par.Section = 'Cue Notes'
        else:
            self.ownerComp.openParameters()

    def CueNotesLabel(self):
        index = int(self._p("Selectedcue")) - 1
        if not 0 <= index < len(self.document["cues"]):
            return "No cue selected"
        cue = self.document["cues"][index]
        return "{:03d} | {}".format(index + 1, cue["name"])

    def ProjectionSource(self, track):
        """Preview replaces a logical track BEFORE mapping and safety blackouts."""
        fallback = "track{}".format(int(track))
        draft = self._look_edit
        enabled = getattr(self.ownerComp.par, "Looklive", None)
        if (enabled is None or not enabled.eval() or draft is None
                or self.engine.state != "stopped" or int(self._p("Looklivetrack")) != int(track)):
            return fallback
        deck = draft["deck"]
        if deck is None or deck != self.ownerComp.op("look_editor"):
            return fallback
        top = deck.op("out1_image")
        return top.path if top is not None else fallback

    def ShowLiveLook(self):
        if self.IsRunningLookEdit():
            raise ValueError("Running-cue edits are already on projection; Update Cue Look or Cancel Changes")
        self._guard_edit(allow_look_edit=True)
        self._look_index()
        self.ownerComp.par.Looklive = True
        self._status("LIVE DRAFT on track {}; cue unchanged until Update Cue. Output blackouts still apply.".format(self._p("Looklivetrack")))

    def StopLiveLook(self):
        if getattr(self.ownerComp.par, "Looklive", None) is not None:
            self.ownerComp.par.Looklive = False

    def LiveLookStatus(self):
        if self.IsRunningLookEdit():
            draft = self._look_edit
            state = "LIVE CUE EDIT" if draft.get("deck") is not None else "CUE ENDED / DRAFT RETAINED"
            return "{} | {} / track {} | Update Cue Look to keep; Cancel to discard".format(
                state, draft["cue"]["name"][:36], draft["cue"]["track"])
        enabled = getattr(self.ownerComp.par, "Looklive", None)
        if enabled is None or not enabled.eval() or self._look_edit is None:
            return "OFF-AIR | Show Live Look to audition; Update Cue to keep changes"
        track = int(self._p("Looklivetrack"))
        routing = self._p("Routingmode")
        outputs = [i for i in (1, 2, 3) if self.OutputTrack(i) == track]
        destinations = ",".join(str(i) for i in outputs) or "none (check Routing)"
        return "LIVE DRAFT (not saved) | Track {} > P{} | {}".format(
            track, destinations, "MASTER BLACKOUT ON" if self._p("Masterblackout") else "output mapping/blackouts apply")

    def AddCue(self):
        cues = copy.deepcopy(self.document["cues"])
        cues.append(self.model.new_cue())
        self._replace_cues(cues)
        self.SelectCue(len(cues))

    def AddBlackout(self):
        self._guard_edit()
        cues = copy.deepcopy(self.document["cues"])
        index = min(max(0, int(self._p("Selectedcue"))), len(cues))
        cue = self.model.new_cue()
        cue.update(name="Blackout", kind="blackout", duration=0.0,
                   track=int(self._p("Track")), blackout_scope="all")
        cues.insert(index, cue)
        self._replace_cues(cues)
        self.SelectCue(index + 1)
        self._status("Blackout inserted after selected cue; set scope/fade then Apply Cue. Audio is unchanged.")

    def DuplicateCue(self):
        index = int(self._p("Selectedcue")) - 1
        cues = copy.deepcopy(self.document["cues"])
        if not 0 <= index < len(cues):
            return
        cue = copy.deepcopy(cues[index])
        cue["id"] = self.model.new_cue()["id"]
        cue["name"] += " copy"
        cues.insert(index + 1, cue)
        self._replace_cues(cues)
        self.SelectCue(index + 2)

    def RemoveCue(self):
        index = int(self._p("Selectedcue")) - 1
        cues = copy.deepcopy(self.document["cues"])
        if 0 <= index < len(cues):
            cues.pop(index)
            self._replace_cues(cues)
            self.SelectCue(max(1, index + 1))

    def MoveCue(self, step):
        index = int(self._p("Selectedcue")) - 1
        target = index + step
        cues = copy.deepcopy(self.document["cues"])
        if 0 <= index < len(cues) and 0 <= target < len(cues):
            cues[index], cues[target] = cues[target], cues[index]
            self._replace_cues(cues)
            self.SelectCue(target + 1)

    def CaptureLook(self):
        self._guard_edit()
        index = int(self._p("Selectedcue")) - 1
        if not 0 <= index < len(self.document["cues"]):
            raise ValueError("Select a cue first")
        look = self._capture_look(self.ownerComp.parent(), capture_animation=True)
        cues = copy.deepcopy(self.document["cues"])
        cues[index]["look"] = look
        self._replace_cues(cues)
        self.SelectCue(index + 1)
        self._status("Captured the demo modules and eight-slot rack into this cue")

    def _capture_look(self, demo, active=True, capture_animation=False):
        """Static controls for comparisons; commits also capture effective clocks."""
        look = {"toggles": {name: bool(demo.par[name]) for name in self.model.TOGGLES if demo.par[name] is not None}, "modules": {}}
        for name in self.model.MODULES:
            module = demo.op(name)
            if module is None: continue
            look["modules"][name] = {
                p.name: p.eval() for p in module.customPars
                if self._safe_parameter(p) and p.name not in {"Enabled", "Autotime", "Manualtime"}
            }
        look["rack"] = json.loads(demo.op("fx_rack").ExportPreset())
        if demo.fetch("imagefx_branch", False):
            # A/B racks inherit the composition clock. Its changing playhead is
            # not an editable look value and must not make captures differ on
            # every frame or overwrite the restored timing expression.
            look["rack"].update(autotime=False, time=0.0)
        if capture_animation:
            clocks = {}
            inherited = bool(demo.fetch("imagefx_branch", False))
            saved = demo.fetch("imagefx_look_animation", {}, search=False)
            for name in (*self.model.MODULES, "fx_rack"):
                module = demo.op(name)
                if module is not None and getattr(module.par, "Autotime", None) is not None:
                    clocks[name] = {"time": float(module.par.Time.eval()),
                                    "running": saved.get(name, {}).get("running", True) if inherited
                                    else bool(module.par.Autotime)}
                    if name in {"ink_dream_flow", "ink_brush_flow", "ink_radial_flow"}:
                        renderer_clock = module.op("animation_clock")
                        if renderer_clock is not None:
                            clocks[name]["render_time"] = self.model.ink_render_time(
                                clocks[name]["time"], float(module.par.Animationspeed.eval()),
                                module.fetch(self.model.INK_CLOCK_KEY, None, search=False))
                            if module.par['Fieldspeed'] is not None:
                                clocks[name]['field_time'] = self.model.ink_render_time(
                                    clocks[name]['render_time'], float(module.par.Fieldspeed.eval()),
                                    module.fetch(self.model.INK_FIELD_CLOCK_KEY, None, search=False))
            look["animation"] = clocks
        look["order"] = demo.op("workflow").module.current(demo)
        force_files = {}
        for name in self.model.FLOW_MODULES:
            module = demo.op(name)
            if module is not None and module.par['Dancecache'] is not None:
                force_files[name] = {p:module.par[p].eval() for p in ('Dancevideo','Dancecache')}
        if force_files:
            look['force_files'] = self.model.resolve_force_files(force_files,project.folder,
                modules=look['modules'],toggles=look['toggles'],active=active)
        puppet=demo.op('dance_puppet')
        if puppet is not None:
            look['puppet_files']=self.model.resolve_puppet_files(
                {name:puppet.par[name].eval() for name in ('Renderfile','Fanrenderfile','Chainrenderfile','Dancevideo','Motioncache','Characterprofile')},project.folder,
                selections=look['modules']['dance_puppet'],enabled=active and look['toggles'].get('Dancepuppetenabled',False))
        layer = demo.op("layer_composite")
        look["layer_files"] = self.model.resolve_layer_files(
            {name: layer.par[name].eval() for name in ("Backdropfile", "Topfile")},
            project.folder,
            selections=look["modules"]["layer_composite"],
            enabled=active and look["toggles"]["Layercompositeenabled"],
        )
        composition=demo.op("image_composition")
        if composition is not None:
            activity=self.model.composition_activity(look,active)
            enabled=any(activity.values())
            look["composition_files"]=self.model.resolve_composition_files(
                {name:composition.par[name].eval() for name in ("Afile","Bfile")},project.folder,
                selections=look["modules"]["image_composition"],enabled=enabled,active_prefixes={p for p,on in activity.items() if on})
            look["branches"]={name:self._capture_look(composition.op(name),activity[name[0].upper()],capture_animation=capture_animation) for name in ("a_effects","b_effects")}
        return look

    def RecallLook(self):
        """Build a private editable preview; never replace the main demo or a cue."""
        self._guard_edit()
        index = int(self._p("Selectedcue")) - 1
        if not 0 <= index < len(self.document["cues"]):
            raise ValueError("Select a cue first")
        cue = copy.deepcopy(self.document["cues"][index])
        if cue["kind"] != "visual":
            raise ValueError("Recall Look needs a Visual cue")
        path = self._media_path(cue)
        if self.ownerComp.op("look_editor") is not None:
            raise ValueError("A look_editor component already exists; it will not be overwritten")
        self._clear_look_result()
        deck = None
        try:
            deck = self._new_deck("look_editor")
            self._apply_look(deck, cue["look"])
            self._set_deck_resolution(deck)
            movie = self._load_deck_media(deck, cue, path)
            for name in (*self.model.MODULES, "fx_rack"):
                module = deck.op(name)
                if getattr(module.par, "Autotime", None) is not None:
                    # The saved phase is independent of wall-clock uptime.
                    clock = cue["look"].get("animation", {}).get(name, {})
                    module.store("imagefx_look_time_origin", absTime.seconds)
                    module.store("imagefx_look_time_phase", clock.get("time", 0.0))
                    if name=='dance_puppet':
                        module.store('puppet_preview_clock',dict(origin=float(absTime.seconds),phase=float(clock.get('time',0.0)),speed=float(module.par.Timescale),running=bool(clock.get('running',True))))
                        module.storeStartupValue('puppet_preview_clock',None)
                        module.par.Time.expr="me.op('puppet_runtime').module.preview_time(me)"
                    else:
                        module.par.Time.expr = "me.fetch('imagefx_look_time_phase', 0) + (absTime.seconds - me.fetch('imagefx_look_time_origin', 0)) * me.par.Timescale if me.par.Autotime else me.par.Manualtime"
                    module.par.Autotime = clock.get("running", True)
            if movie is not None:
                movie.par.play = True
            deck.allowCooking = True
            self._look_edit = {"cue": cue, "deck": deck}
            if getattr(self.ownerComp.par, "Looklivetrack", None) is not None:
                self.ownerComp.par.Looklivetrack = cue["track"]
            self.ownerComp.op("look_preview").par.top = deck.op("out1_image").path
            self.ownerComp.par.Lookediting = True
            self.ownerComp.par.Lookstatus = "Editing: {} | {}".format(cue["name"], deck.path)
            self._status("Off-air draft ready. Edit modules inside show_control/look_editor; then Update, Save New, or Cancel")
        except Exception:
            self._look_edit = None
            self.ownerComp.op("look_preview").par.top = "black"
            self.ownerComp.par.Lookediting = False
            if deck is not None:
                deck.destroy()
            raise

    def _look_index(self):
        if self._look_edit is None:
            raise ValueError("Recall Look before editing a captured look")
        original = self._look_edit["cue"]
        for index, cue in enumerate(self.document["cues"]):
            if cue["id"] == original["id"]:
                if cue != original:
                    raise ValueError("Original cue changed outside this editor; cancel and recall it again")
                return index
        raise ValueError("Original cue no longer exists; cancel this draft")

    def IsRunningLookEdit(self):
        return bool(self._look_edit and self._look_edit.get("mode") == "running")

    def RunningLookDeck(self):
        """An editor may only touch the exact playback instance it started on."""
        if not self.IsRunningLookEdit():
            raise ValueError("No running-cue edit is active")
        draft = self._look_edit
        item = self.tracks.get(draft["cue"]["track"])
        deck = draft.get("deck")
        if (deck is None or item is None or item is not draft.get("item") or item.get("finished")
                or item["cue"]["id"] != draft["cue"]["id"]
                or deck != item.get("deck") or deck.id != draft["deck_id"]
                or deck != self.ownerComp.op("deck{}_{}".format(item["track"], item["side"]))):
            raise ValueError("The edited cue has ended or changed; Update Cue Look or Cancel Changes")
        return deck

    def EditRunningLook(self):
        """Audition in-place: no copying, media reload, clock reset or rerouting."""
        self._guard_no_look_edit()
        if self.engine.state != "running":
            raise ValueError("Run or resume a visual cue, select its PLAY row, then Edit Running Cue")
        index = int(self._p("Selectedcue")) - 1
        if not 0 <= index < len(self.document["cues"]):
            raise ValueError("Select the running visual cue")
        cue = self.document["cues"][index]
        item = self.tracks.get(cue["track"])
        if (cue["kind"] != "visual" or not item or item["cue"]["id"] != cue["id"]
                or item.get("finished") or cue["id"] not in self.engine.active):
            raise ValueError("Select the visual cue currently showing PLAY on its track")
        if item.get("fading"):
            raise ValueError("Wait for this cue's crossfade to finish before editing")
        if any(value["cue"]["track"] == cue["track"] for value in self.automations.values()):
            raise ValueError("Wait for parameter automation on this track to finish before editing")
        deck = item["deck"]
        original = self._capture_look(deck)
        self._clear_look_result()
        self.StopLiveLook()
        self._look_edit = dict(mode="running", cue=copy.deepcopy(cue), deck=deck,
                               deck_id=deck.id, item=item, original=original)
        # The track source retains its last rendered frame during Pause, while
        # the underlying deck deliberately stops cooking. Preview that same
        # pre-mapping source so resize/redraw never shows an uncooked deck.
        self.ownerComp.op("look_preview").par.top = "track{}_source{}".format(item["track"], item["side"])
        self.ownerComp.par.Lookediting = True
        self.ownerComp.par.Lookstatus = "LIVE EDIT: " + cue["name"]
        self._status("Running cue stays on air. Choose Effect Module > Edit Controls; Update Cue Look or Cancel Changes.")

    @staticmethod
    def _keep_starting_clocks(look, saved):
        """Commit settings, not elapsed rehearsal time, as a cue's next start."""
        look.pop("animation", None)
        if "animation" in saved:
            look["animation"] = copy.deepcopy(saved["animation"])
        if "rack" in look:
            for name, default in (("time", 0.0), ("autotime", True)):
                look["rack"][name] = saved.get("rack", {}).get(name, default)
        for name, branch in look.get("branches", {}).items():
            ShowControlExt._keep_starting_clocks(branch, saved.get("branches", {}).get(name, {}))
        return look

    def _running_look_snapshot(self):
        draft = self._look_edit
        if draft.get("deck") is None:
            if draft.get("capture_error"):
                raise ValueError("Ended draft could not be captured: " + draft["capture_error"] + "; Cancel Changes")
            return copy.deepcopy(draft["pending_look"])
        return self._keep_starting_clocks(self._capture_look(self.RunningLookDeck()), draft["cue"]["look"])

    def _restore_running_values(self, deck, look):
        """Restore changed values only; never load media or reset playback clocks."""
        for name, values in look.get("modules", {}).items():
            module = deck.op(name)
            for key, value in values.items():
                if module.par[key].eval() != value:
                    self._assign(module, key, value)
        for module_name, field in (("layer_composite", "layer_files"), ("image_composition", "composition_files"), ("dance_puppet", "puppet_files")):
            module = deck.op(module_name)
            for name, value in look.get(field, {}).items():
                if module.par[name].eval() != value:
                    module.par[name] = value
        for module_name, files in look.get('force_files',{}).items():
            module = deck.op(module_name)
            for name, value in files.items():
                if module.par[name].eval() != value: module.par[name] = value
        rack = deck.op("fx_rack")
        current = json.loads(rack.ExportPreset())
        preset = copy.deepcopy(look["rack"])
        for key in ("time", "autotime"):
            preset[key] = current[key]
        if preset != current:
            # Branch rack time can be expression-bound; ImportPreset must not
            # replace that binding while restoring slot settings.
            clock = rack.par.Manualtime
            mode, expression = clock.mode, clock.expr
            rack.ImportPreset(preset)
            clock.expr, clock.mode = expression, mode
        for name, branch in look.get("branches", {}).items():
            self._restore_running_values(deck.op("image_composition/" + name), branch)
        for name, value in look.get("toggles", {}).items():
            if bool(deck.par[name]) != value:
                deck.par[name] = value
        workflow = deck.op("workflow").module
        if list(workflow.current(deck)) != look.get("order"):
            workflow.apply_order(deck, look["order"])

    def _detach_running_look(self, item):
        """Retain a value-only draft before its deck is held, stopped or reused."""
        if not self.IsRunningLookEdit() or self._look_edit.get("item") is not item:
            return
        draft = self._look_edit
        try:
            draft["pending_look"] = self._running_look_snapshot()
        except Exception as exc:
            draft["capture_error"] = str(exc)
        # Keep the auditioned image through a hold or outgoing crossfade. The
        # deck is reset on reuse; reverting it here would create a visible pop.
        draft["deck"], draft["item"] = None, None
        self.ownerComp.op("look_preview").par.top = "black"
        self.ownerComp.par.Lookstatus = "Cue ended; draft retained. Update Cue Look or Cancel Changes."

    def _finish_running_look(self):
        # This deck belongs to playback, not the editor: NEVER destroy it.
        self._look_edit = None
        self.ownerComp.par.Lookediting = False
        self.ownerComp.op("look_preview").par.top = "black"
        self.ownerComp.par.Lookstatus = "No look draft; Edit Running Cue or Recall Look"

    def _commit_running_look(self):
        index = self._look_index()
        look = self._running_look_snapshot()
        cues = copy.deepcopy(self.document["cues"])
        cues[index]["look"] = look
        validated = self._validated_cues(cues)
        cue = self.document["cues"][index]
        cue["look"] = validated["cues"][index]["look"]
        for engine_cue in self.engine.cues:
            if engine_cue["id"] == cue["id"]:
                engine_cue["look"] = copy.deepcopy(cue["look"])
        self._save_document_dat()
        self._finish_running_look()
        self.Refresh()
        self._status("Cue look updated without restarting playback. Starting phase and timing unchanged; Save Show writes it to disk.")

    def _clear_look_result(self):
        result = self.ownerComp.op("look_result")
        if result is not None and result.fetch("imagefx_saved_preview", False, search=False):
            self.ownerComp.op("look_preview").par.top = "black"
            result.destroy()
        self._look_preview_cue_id = None
        self.ownerComp.store("imagefx_saved_preview_session", None)
        if self._look_edit is None:
            self.ownerComp.par.Lookstatus = "No look draft; select a visual cue and Recall Look"

    def _snapshot_look(self, deck):
        """Keep one locked TOP, not an entire live effect network, after commit."""
        import td
        result = self.ownerComp.create(td.selectTOP, "look_result")
        result.store("imagefx_show_runtime", True)
        result.store("imagefx_saved_preview", True)
        try:
            source = deck.op("out1_image")
            result.par.top = source.path
            result.cook(force=True)
            result.lock = True
            if (result.width, result.height) != (source.width, source.height):
                raise ValueError("Could not retain the look preview; draft remains open")
            return result
        except Exception:
            result.destroy()
            raise

    def _finish_look_edit(self, preview=None):
        self.StopLiveLook()
        self.ownerComp.op("look_preview").par.top = preview.path if preview is not None else "black"
        if self._look_edit is not None:
            self._look_edit["deck"].destroy()
        self._look_edit = None
        self.ownerComp.par.Lookediting = False
        self.ownerComp.par.Lookstatus = ("Saved preview (frozen); Recall Look to edit again" if preview is not None else
                                         "No look draft; select a visual cue and Recall Look")

    def _commit_look(self, as_new=False):
        if self.IsRunningLookEdit():
            if as_new:
                raise ValueError("Use Update Cue Look or Cancel Changes for a running-cue edit")
            return self._commit_running_look()
        self._guard_edit(allow_look_edit=True)
        index = self._look_index()
        if self.ownerComp.op("look_result") is not None:
            raise ValueError("A look_result component already exists; it will not be overwritten")
        self._look_edit["deck"].op("out1_image").cook(force=True)
        look = self._capture_look(self._look_edit["deck"], capture_animation=True)
        cues = copy.deepcopy(self.document["cues"])
        if as_new:
            cue = copy.deepcopy(cues[index])
            cue.update(id=self.model.new_cue()["id"], name=cue["name"][:153] + " edited",
                       at=None, follow="manual", enabled=False, look=look)
            cues.append(cue)
            selected = len(cues)
        else:
            cues[index]["look"] = look
            selected = index + 1
        # Failed capture/validation leaves the draft open and the original intact.
        # Validate before creating/removing any TOPs (native tree changes can
        # invalidate an extension even when a transaction is rejected).
        self._validated_cues(cues)
        preview = self._snapshot_look(self._look_edit["deck"])
        try:
            self._replace_cues(cues, allow_look_edit=True)
        except Exception:
            preview.destroy()
            raise
        self._finish_look_edit(preview=preview)
        self._look_preview_cue_id = cues[selected - 1]["id"]
        self.ownerComp.store("imagefx_saved_preview_session", {"owner": self.ownerComp.id,
                                                               "cue": self._look_preview_cue_id})
        self.ownerComp.storeStartupValue("imagefx_saved_preview_session", None)
        self.SelectCue(selected)
        self._status(("New cue created disabled; enable it in Cue Editor. " if as_new else
                      "Cue look updated; media and timing unchanged. ") + "Save Show writes it to disk")

    def UpdateLook(self):
        self._commit_look()

    def SaveLookAsNew(self):
        self._commit_look(as_new=True)

    def CancelLook(self):
        if self.IsRunningLookEdit():
            if self._look_edit.get("deck") is not None:
                self._restore_running_values(self.RunningLookDeck(), self._look_edit["original"])
            self._finish_running_look()
            self._status("Running look changes discarded. Playback continues without rewinding; saved cue unchanged.")
            return
        self._guard_edit(allow_look_edit=True)
        if self._look_edit is None:
            raise ValueError("No look draft to cancel")
        self._finish_look_edit()
        self.SelectCue()
        self._status("Look changes discarded; saved cues and the main demo are unchanged")

    @staticmethod
    def _safe_parameter(parameter):
        return parameter is not None and parameter.name not in {'Amodule','Bmodule'} and not parameter.readOnly and not parameter.isPulse and (
            parameter.isNumber or parameter.isToggle or parameter.isMenu
        )

    def _validate_assignment(self, component, name, value):
        parameter = getattr(component.par, name, None)
        # Par equality evaluates values (including unrelated expressions), not
        # parameter identity. Check names instead, without cooking status fields.
        if not self._safe_parameter(parameter) or name not in {p.name for p in component.customPars}:
            raise ValueError("Unsafe or unknown parameter: " + name)
        if parameter.isMenu:
            if value not in parameter.menuNames:
                raise ValueError("Invalid menu value: " + name)
        elif parameter.isToggle:
            if not isinstance(value, bool):
                raise ValueError("Toggle requires true/false: " + name)
        else:
            self.model.number(value, name, float(parameter.min), float(parameter.max))
        return parameter

    def _assign(self, component, name, value):
        parameter = self._validate_assignment(component, name, value)
        parameter.val = value

    def _apply_look(self, deck, look, template=None, active=True):
        # Look Editor is off-air; playback consumes the same operations over
        # successive frames via _service_preloads instead of blocking GO.
        for _ in self._apply_look_steps(deck, look, template, active):
            pass

    def _apply_look_steps(self, deck, look, template=None, active=True, media_source=None):
        branch=bool(deck.fetch("imagefx_branch",False))
        self.model.validate_look_media(look,Path(self._p("Showfile")).resolve().parent,active=active,branch=branch)
        if set(look) - {"toggles", "modules", "rack", "layer_files", "order", "composition_files", "branches", "animation", "puppet_files", "force_files"}:
            raise ValueError("Unknown look fields")
        # Pre-feature cues have no motion media block. Seed passive local files
        # from the matching designer workflow, not from a previously used deck.
        # Do not change the saved cue, enable an effect, or launch a worker.
        # Explicit media (even blank) and all existing controls remain decisive.
        media_source = media_source or self.ownerComp.parent()
        force_defaults = {}
        for name in self.model.FLOW_MODULES:
            source = media_source.op(name)
            if source is not None and source.par['Dancecache'] is not None:
                force_defaults[name] = {key:source.par[key].eval() for key in ('Dancevideo','Dancecache')}
        puppet_source = media_source.op('dance_puppet')
        puppet_defaults = None if puppet_source is None else {
            key:puppet_source.par[key].eval() for key in
            ('Renderfile','Fanrenderfile','Chainrenderfile','Dancevideo','Motioncache','Characterprofile')}
        look = self.model.with_legacy_motion_media(look,
            force_files=self.model.resolve_force_files(force_defaults,project.folder,active=False),
            puppet_files=None if puppet_defaults is None else self.model.resolve_puppet_files(
                puppet_defaults,project.folder,enabled=False))
        animation = copy.deepcopy(look.get("animation", {}))
        deck.store("imagefx_look_animation", animation)
        workflow = deck.op("workflow").module
        order = workflow.validate_order(look.get("order", list(workflow.BRANCH_ORDER if branch else workflow.DEFAULT_ORDER)),branch)
        layer_files = self.model.resolve_layer_files(
            look.get("layer_files", {}), Path(self._p("Showfile")).resolve().parent,
            selections=look.get("modules", {}).get("layer_composite", {}),
            enabled=active and look.get("toggles", {}).get("Layercompositeenabled", False),
        )
        for name in self.model.TOGGLES:
            if deck.par[name] is not None: deck.par[name] = False
        template = template or self.ownerComp.op("deck_template")
        for module_name in self.model.MODULES:
            module = deck.op(module_name)
            if module is None: continue
            for parameter in module.customPars:
                if self._safe_parameter(parameter) and parameter.name not in {"Enabled", "Autotime", "Manualtime"}:
                    parameter.val = template.op(module_name).par[parameter.name].eval()
            # Enabled belongs to the deck's routing, not its saved effect values.
            # Assigning .val here previously replaced the expression with False.
            # Repair it on reused decks too, including decks made by older builds.
            # workflow.apply_order restores every module's two-way binding
            # after the saved parent toggle has been applied below.
            module.par.Enabled.expr = "parent().par.{}".format(self.model.MODULE_TOGGLES[module_name])
            yield
        for name, value in look.get("toggles", {}).items():
            if name not in self.model.TOGGLES or deck.par[name] is None or not isinstance(value, bool):
                raise ValueError("Unknown demo toggle")
            deck.par[name] = value
        for name, value in layer_files.items():
            deck.op("layer_composite").par[name] = value
        force_files = self.model.resolve_force_files(look.get('force_files',{}),Path(self._p('Showfile')).resolve().parent,
            modules=look.get('modules',{}),toggles=look.get('toggles',{}),active=active)
        for module_name, files in force_files.items():
            module = deck.op(module_name)
            if module is not None and module.par['Dancecache'] is not None:
                for name, value in files.items(): module.par[name] = value
        puppet=deck.op('dance_puppet')
        if puppet is not None:
            files=self.model.resolve_puppet_files(look.get('puppet_files',{}),Path(self._p('Showfile')).resolve().parent,
                selections=look.get('modules',{}).get('dance_puppet',{}),enabled=active and look.get('toggles',{}).get('Dancepuppetenabled',False))
            for name,value in files.items(): puppet.par[name]=value
            # Decks are intentionally not cooking while a look is staged.
            # Do not import a DAT module here: that requires cooking the DAT.
            puppet.store('puppet_finish_clock',None)
            puppet.storeStartupValue('puppet_finish_clock',None)
            puppet.op('puppet_history').par.resetpulse.pulse()
        for module_name, parameters in look.get("modules", {}).items():
            if module_name not in self.model.MODULES or deck.op(module_name) is None or not isinstance(parameters, dict):
                raise ValueError("Unknown module in look")
            for name, value in parameters.items():
                if name in {"Enabled", "Time", "Autotime", "Manualtime"}:
                    raise ValueError("Look may not override cue-owned timing/routing")
                self._assign(deck.op(module_name), name, value)
            yield
        deck.op("fx_rack").ImportPreset(look.get("rack", self._default_rack))
        yield
        for module_name in (*self.model.MODULES, "fx_rack"):
            module = deck.op(module_name)
            if module is None: continue
            if getattr(module.par, "Autotime", None) is not None:
                clock = animation.get(module_name, {})
                phase = clock.get("time", 0.0)
                module.par.Autotime = False
                # Main-workflow manual sliders are intentionally bounded; cue
                # copies also need to represent long-running/reverse phases.
                module.par.Manualtime.min, module.par.Manualtime.max = -1.0e9, 1.0e9
                if branch and clock.get("running", True):
                    parent_phase = deck.parent().parent().fetch("imagefx_look_animation", {}, search=False).get("image_composition", {}).get("time", 0.0)
                    module.par.Manualtime.expr = "{} + (parent(2).par.Time - {}) * me.par.Timescale".format(phase, parent_phase)
                else:
                    module.par.Manualtime = phase
                if module_name=='dance_puppet' and module.par['Fadein'] is not None:
                    module.store('puppet_fade_start',float(absTime.seconds) if module.par.Sourcemode=='live' else float(phase))
                    module.storeStartupValue('puppet_fade_start',None)
                if module_name in {"ink_dream_flow", "ink_brush_flow", "ink_radial_flow"}:
                    if module.par['Danceenabled'] is not None:
                        # Cue-local force clock is independent of the saved
                        # procedural pattern phase. GO/export begin at in-point.
                        module.store('dance_force_clock',dict(raw=float(phase),phase=0.,speed=float(module.par.Dancespeed)))
                        module.storeStartupValue('dance_force_clock',None)
                        module.store('dance_force_activation',float(phase))
                        module.storeStartupValue('dance_force_activation',None)
                        module.store('dance_force_gate',None)
                        module.storeStartupValue('dance_force_gate',None)
                        module.store('dance_force_ready',False)
                        module.storeStartupValue('dance_force_ready',None)
                        # Preparing a deck can disable DAT cooking, so reset
                        # GPU material history without importing its runtime.
                        module.store('dance_flow_clock',None)
                        module.storeStartupValue('dance_flow_clock',None)
                        for history_name in ('dance_motion_history','dance_response_history'):
                            force_history=module.op(history_name)
                            if force_history is not None:
                                force_history.par.resetpulse.pulse()
                    renderer_clock = module.op("animation_clock")
                    if renderer_clock is not None:
                        # New looks retain their continuous position. Old looks
                        # used raw time * speed, so reset's legacy default keeps
                        # their appearance, including preloaded/reused decks.
                        # Preparing a deck intentionally disables cooking; do
                        # not compile its DAT module just to restore storage.
                        speed = float(module.par.Animationspeed.eval())
                        module.store(self.model.INK_CLOCK_KEY, dict(raw=float(phase),
                            phase=float(clock.get("render_time", phase * speed)), speed=speed))
                        module.storeStartupValue(self.model.INK_CLOCK_KEY, None)
                        if module.par['Fieldspeed'] is not None:
                            render_phase = float(clock.get('render_time', phase * speed))
                            field_speed = float(module.par.Fieldspeed.eval())
                            module.store(self.model.INK_FIELD_CLOCK_KEY, dict(raw=render_phase,
                                phase=float(clock.get('field_time', render_phase * field_speed)), speed=field_speed))
                            module.storeStartupValue(self.model.INK_FIELD_CLOCK_KEY, None)
                        # Never bring trails from a prior use of this playback deck.
                        module.store('imagefx_flow_feedback_state', None)
                        module.storeStartupValue('imagefx_flow_feedback_state', None)
                        history = module.op('flow_feedback_history')
                        if history is not None:
                            history.par.resetpulse.pulse()
        composition=deck.op("image_composition")
        if composition is not None:
            activity=self.model.composition_activity(look,active)
            enabled=any(activity.values())
            files=self.model.resolve_composition_files(look.get("composition_files",{}),Path(self._p("Showfile")).resolve().parent,selections=look.get("modules",{}).get("image_composition",{}),enabled=enabled,active_prefixes={p for p,on in activity.items() if on})
            for name,value in files.items(): composition.par[name]=value
            for name in ("a_effects","b_effects"):
                yield from self._apply_look_steps(composition.op(name),look.get("branches",{}).get(name,{}),template.op("image_composition/"+name),activity[name[0].upper()],media_source.op("image_composition/"+name))
        deck.op("fx_rack").Reset()
        workflow.apply_order(deck, order)
        yield

    def _media_path(self, cue):
        raw = cue["source"]
        if not raw:
            return ""
        if "://" in raw:
            raise ValueError("Show media must be local files, not network URLs")
        path = Path(raw)
        if not path.is_absolute():
            path = Path(self._p("Showfile")).resolve().parent / path
        if not path.is_file():
            raise ValueError("Missing media: " + path.name)
        return str(path.resolve())

    def _deck(self, track, side):
        name = "deck{}_{}".format(track, side)
        deck = self.ownerComp.op(name)
        if deck is not None:
            return deck
        deck = self._new_deck(name)
        deck.nodeX = 300 + track * 220
        deck.nodeY = -500 - side * 140
        return deck

    def _warm_decks(self):
        if not self.ownerComp.valid or getattr(self.ownerComp.ext, "ShowControlExt", None) is not self:
            return  # A queued callback from an explicitly reinitialized copy.
        if self.tracks or self.prepared:
            return  # Never do startup work over a cue already being prepared.
        for track in (1, 2, 3):
            for side in (0, 1):
                deck = self._deck(track, side)
                # Prime the large procedural ink shaders at a small resolution
                # while startup is off-air. Their first cold compile must not
                # land on the presentation thread during a later cue change.
                width, height = deck.par.Customwidth.eval(), deck.par.Customheight.eval()
                preset = deck.par.Resolutionpreset.eval()
                try:
                    deck.par.Resolutionpreset = "custom"
                    deck.par.Customwidth, deck.par.Customheight = 320, 180
                    deck.allowCooking = True
                    for name in ("ink_dream_flow", "ink_brush_flow", "ink_radial_flow"):
                        shader = deck.op(name + "/effect_glsl_" + name)
                        if shader is not None:
                            shader.cook(force=True)
                finally:
                    deck.allowCooking = False
                    deck.par.Customwidth, deck.par.Customheight = width, height
                    deck.par.Resolutionpreset = preset

    def _new_deck(self, name):
        deck = self.ownerComp.copy(self.ownerComp.op("deck_template"), name=name)
        deck.store("imagefx_show_runtime", True)
        deck.nodeX, deck.nodeY = 1100, -500
        deck.allowCooking = True
        if deck.op("source_media_runtime") is not None:
            deck.op("source_media_runtime").module
            # Cue media/transport are authoritative. Never inherit designer media.
            deck.par.Sourcefile = ""
            deck.par.Sourcemode = "demo"
        deck.op("fx_rack").initializeExtensions()
        # Copied Text DAT modules cannot compile under a cooking-disabled deck.
        # Initialize both independent workflows before putting this standby
        # deck off-line; subsequent cue application is then safe and atomic.
        composition = deck.op("image_composition")
        if composition is not None:
            for name in ("a_effects", "b_effects"):
                branch = composition.op(name)
                branch.op("workflow").module
                branch.op("fx_rack").initializeExtensions()
        deck.allowCooking = False
        deck.op("source_image").name = "test_pattern"
        source = deck.create(switchTOP, "source_image")
        source.par.outputresolution = "custom"
        source.par.resolutionw.expr = "parent().par.Customwidth"
        source.par.resolutionh.expr = "parent().par.Customheight"
        deck.op("test_pattern").outputConnectors[0].connect(source.inputConnectors[0])
        deck.op("workflow").module.apply_order(deck, deck.op("workflow").module.current(deck))
        source.outputConnectors[0].connect(deck.op("fixture_image_b").inputConnectors[0])
        return deck

    def prepare(self, cue):
        self._guard_no_look_edit(allow_running=True)
        if cue["id"] in self.engine.active or any(
            item["cue"]["id"] == cue["id"] for item in self.tracks.values()
        ):
            raise ValueError("Cue is already running or held; stop it before preloading again")
        try:
            self._prepare(cue)
        except self.model.CuePreparationBusy:
            # No resources were changed. In particular, do not disturb the
            # on-air/standby decks while an automatic request waits its turn.
            raise
        except Exception:
            self.stop_cue(cue)
            raise

    def prepare_replay(self, cue):
        """Load a fresh standby while keeping a previously held instance on air."""
        self._guard_no_look_edit(allow_running=True)
        track = self.tracks.get(cue["track"])
        if cue["kind"] == "visual" and track and track.get("fading"):
            raise ValueError("Wait for this track's crossfade to finish before Go Back")
        # An explicitly preloaded target is already a fresh standby.
        if cue["id"] in self.prepared:
            return
        alias = "replay_" + uuid.uuid4().hex
        held = track if track and track["cue"]["id"] == cue["id"] else None
        voice = self.audio.pop(cue["id"], None)
        held_cue = held["cue"] if held else None
        voice_cue = voice["cue"] if voice else None
        if held:
            self._detach_running_look(held)
            held["cue"] = dict(held_cue, id=alias)
        if voice:
            voice["cue"] = dict(voice_cue, id=alias)
            self.audio[alias] = voice
        try:
            self._prepare(cue)
            if voice and cue["kind"] == "audio":
                self.prepared[cue["id"]]["replay_voice"] = alias
        except Exception:
            self.stop_cue(cue)
            if held:
                held["cue"] = held_cue
            if voice:
                self.audio.pop(alias, None)
                voice["cue"] = voice_cue
                self.audio[cue["id"]] = voice
            raise

    def _prepare(self, cue):
        if cue["id"] in self.prepared:
            return
        if cue["kind"] not in {"visual", "audio"}:
            self.prepared[cue["id"]] = {"cue": cue}
            return
        path = self._media_path(cue)
        track = cue["track"]
        if cue["kind"] == "audio":
            if not path:
                raise ValueError("Audio cue needs a media file")
            if len(self.audio) >= 8:
                raise ValueError("Stop an audio cue before loading more (eight voice limit)")
            reader = self.ownerComp.create(audiofileinCHOP, "audio_" + cue["id"])
            reader.store("imagefx_show_runtime", True)
            item = {"cue": cue, "reader": reader, "gain": None, "started": None}
            self.audio[cue["id"]] = item
            reader.par.play = False
            reader.par.file = path
            reader.par.repeat = "on" if cue["loop"] else "off"
            reader.par.cuepoint = cue["media_in"]
            reader.par.cuepointunit = "seconds"
            reader.par.cuepulse.pulse()
            self._connect_audio(item)
            self.prepared[cue["id"]] = item
            return
        state = self.tracks.get(track, {"side": 1})
        if state.get("fading"):
            raise self.model.CuePreparationBusy("Wait for this track's crossfade to finish before loading another cue")
        side = 1 - state["side"]
        for item in self.prepared.values():
            if item.get("track") == track and item.get("side") == side:
                raise self.model.CuePreparationBusy("Track standby is occupied; start or stop its prepared cue first")
        deck = self._deck(track, side)
        # The previous occupant of this standby may still be selected after a
        # completed fade. Keep all partially-applied values off the output graph.
        source_top = self.ownerComp.op("track{}_source{}".format(track, side))
        source_top.lock = False
        source_top.par.top = "black"
        deck.allowCooking = False
        item = {"cue": cue, "deck": deck, "movie": None, "track": track, "side": side,
                "deck_id": deck.id, "loading": True, "error": None}
        self.prepared[cue["id"]] = item
        item["steps"] = self._prepare_visual_steps(item, path)

    def _prepare_visual_steps(self, item, path):
        cue, deck = item["cue"], item["deck"]
        yield from self._apply_look_steps(deck, cue["look"])
        self._set_deck_resolution(deck)
        movie = self._load_deck_media(deck, cue, path)
        item["movie"] = movie
        yield
        deck.allowCooking = True
        for reader in self._look_readers(deck): reader.preload()
        yield
        # Decode and compile before publishing the deck. The old cue remains
        # selected throughout preparation, including shader/media warm-up.
        while not self._media_ready(item):
            yield
        deck.op("out1_image").cook(force=True)
        item["warm_frame"] = absTime.frame
        yield
        while absTime.frame <= item["warm_frame"]:
            yield
        errors = deck.errors(recurse=True)
        if errors:
            raise ValueError("Prepared look has operator errors: " + str(errors)[:300])
        if path and cue["movie_audio"]:
            if len(self.audio) >= 8:
                raise ValueError("Eight audio voices already loaded")
            reader = self.ownerComp.create(audiomovieCHOP, "audio_" + cue["id"])
            reader.store("imagefx_show_runtime", True)
            item = {"cue": cue, "reader": reader, "gain": None, "started": None}
            self.audio[cue["id"]] = item
            reader.par.moviefileintop = movie.path
            reader.par.play = False
            self._connect_audio(item)

    def _service_preloads(self):
        # One shared 4ms CPU budget, not one budget per track. An indivisible
        # decoder/GPU operation can take longer; ready is never advertised early.
        deadline = time.perf_counter() + 0.004
        for item in list(self.prepared.values()):
            if not item.get("loading") or item.get("error"):
                continue
            try:
                while time.perf_counter() < deadline:
                    next(item["steps"])
                    # Warm-up must span actual TD frames, not just generator steps.
                    if item.get("warm_frame") == absTime.frame:
                        break
            except StopIteration:
                item.pop("steps", None)
                item["loading"] = False
                self._status("Ready: " + item["cue"]["name"] + "; GO starts the prepared look")
            except Exception as exc:
                item["error"] = str(exc)
                item["loading"] = False
                item.pop("steps", None)
                self._halt_deck(item)
                self._release_audio(item["cue"]["id"])
                self._status("Preload error: " + str(exc))
            if time.perf_counter() >= deadline:
                break

    def _set_deck_resolution(self, deck):
        deck.par.Resolutionpreset = "custom"
        deck.par.Customwidth.max = 16384
        deck.par.Customwidth.normMax = 16384
        deck.par.Customwidth = int(self._p("Renderwidth") * ((3-2*self._p("Panoramaoverlap")) if self._p("Routingmode") == "panoramic" else 1))
        deck.par.Customheight = int(self._p("Renderheight"))

    def OutputTrack(self, output):
        """Physical delivery does not change which cue track supplies a canvas."""
        if self._p('Routingmode') == 'independent':
            return int(self._p('Output{}track'.format(output)))
        shared = getattr(self.ownerComp.par, 'Sharedtrack', None)
        return int(shared.eval()) if shared is not None else 1

    def _sync_canvas_resolution(self):
        """Resize prepared/live/edit decks without reloading media or cue time."""
        width = int(self._p('Renderwidth') * (
            (3 - 2 * self._p('Panoramaoverlap')) if self._p('Routingmode') == 'panoramic' else 1))
        height = int(self._p('Renderheight'))
        names = ['deck{}_{}'.format(t, s) for t in (1, 2, 3) for s in (0, 1)] + ['look_editor']
        for name in names:
            deck = self.ownerComp.op(name)
            if deck is not None and (deck.par.Resolutionpreset != 'custom'
                    or int(deck.par.Customwidth) != width or int(deck.par.Customheight) != height):
                self._set_deck_resolution(deck)

    def _load_deck_media(self, deck, cue, path):
        movie = deck.op("media")
        if movie is None and path:
            movie = deck.create(moviefileinTOP, "media")
        if movie is not None:
            output_mode = self.ownerComp.op('show_output_mode')
            if output_mode is not None and hasattr(output_mode.module, 'fit_cue_media'):
                output_mode.module.fit_cue_media(self.ownerComp, deck, movie)
            else:
                movie.outputConnectors[0].connect(deck.op("source_image").inputConnectors[1])
        deck.op("source_image").par.index = int(bool(path))
        if movie is not None:
            movie.par.play = False
            if path:
                movie.par.file = path
                movie.par.speed = cue["speed"]
                movie.par.textendright = "cycle" if cue["loop"] else "hold"
                movie.par.cuepoint = cue["media_in"]
                movie.par.cuepointunit = "seconds"
                movie.par.cuepulse.pulse()
                movie.preload()
        return movie if path else None

    def _connect_audio(self, item):
        # Normalize mono/stereo sources before summing. Additional channels are
        # deliberately ignored; this workstation has one stereo headphone bus.
        reader, cue = item["reader"], item["cue"]
        callback = self.ownerComp.create(textDAT, "stereo_code_" + cue["id"])
        callback.store("imagefx_show_runtime", True)
        callback.text = "def onCook(scriptOp):\n    scriptOp.clear()\n    source = scriptOp.inputs[0].numpyArray()\n    if source is None or source.shape[0] == 0: return\n    scriptOp.rate = scriptOp.inputs[0].rate\n    if not scriptOp.par.timeslice: scriptOp.numSamples = source.shape[1]\n    scriptOp.appendChan('left').vals = source[0]\n    scriptOp.appendChan('right').vals = source[min(1,source.shape[0]-1)]\n"
        stereo = self.ownerComp.create(scriptCHOP, "stereo_" + cue["id"])
        stereo.store("imagefx_show_runtime", True)
        item["stereo"], item["callback"] = stereo, callback
        stereo.par.callbacks = callback.path
        stereo.par.timeslice = True
        reader.outputConnectors[0].connect(stereo.inputConnectors[0])
        gain = self.ownerComp.create(mathCHOP, "gain_" + cue["id"])
        gain.store("imagefx_show_runtime", True)
        item["gain"] = gain
        stereo.outputConnectors[0].connect(gain.inputConnectors[0])
        gain.par.gain = 0
        gain.par.timeslice = True
        mixer = self.ownerComp.op("audio_mix")
        gain.outputConnectors[0].connect(mixer.inputConnectors[len(mixer.inputs)])

    def _look_readers(self, deck):
        puppet=deck.op('dance_puppet')
        if puppet is not None and puppet.par.Enabled.eval():
            if puppet.par.Sourcemode.eval()=='recorded': yield puppet.op('recorded_motion')
            else:
                puppet.op('puppet_runtime').module.poll(puppet)
                if not puppet.par.Ready: raise ValueError('Puppet live camera is not ready; Start Camera explicitly before preloading')
        layer=deck.op("layer_composite")
        if layer is not None and layer.par.Enabled.eval():
            for prefix in ("backdrop","top"):
                if layer.op("media_status").module.uses_file(layer,prefix): yield layer.op(prefix+"_file")
        composition=deck.op("image_composition")
        if composition is not None:
            for prefix in ("A","B"):
                if not composition.op('composition_math').module.active(composition,prefix): continue
                if composition.op("composition_math").module.selected(composition,prefix)==2: yield composition.op(prefix.lower()+"_file")
                yield from self._look_readers(composition.op(prefix.lower()+"_effects"))

    def ready(self, cue):
        item = self.prepared[cue["id"]]
        if item.get("error"):
            raise ValueError(item["error"])
        if item.get("loading"):
            return False
        deck = item.get("deck")
        if deck is not None and item.get("deck_id") is not None and deck.id != item["deck_id"]:
            raise ValueError("Prepared deck was replaced; stop and preload this cue again")
        return self._media_ready(item)

    def _media_ready(self, item):
        deck = item.get("deck")
        if deck is not None:
            for image in self._look_readers(deck):
                image.cook(force=True)
                if image.isInvalid:
                    raise ValueError("Layer image could not be decoded: " + image.name)
                if not image.isOpen or not image.isFullyPreRead:
                    return False
        if "reader" in item:
            item["reader"].cook(force=True)
            if item["reader"].errors():
                raise ValueError("Audio could not be decoded")
            return True
        movie = item.get("movie")
        if movie is None:
            return True
        movie.cook(force=True)
        if movie.isInvalid:
            raise ValueError("Video/image could not be decoded")
        return bool(movie.isOpen and movie.isFullyPreRead)

    def _target(self, cue):
        state = self.tracks.get(cue["track"])
        if not state:
            raise ValueError("Parameter cue needs a running visual track")
        node, name = self.model.parse_target(cue["target"])
        component = state["deck"].op(node)
        if component is None:
            raise ValueError("Target effect is not loaded")
        p = getattr(component.par, name, None)
        if not self._safe_parameter(p) or name in {"Autotime", "Manualtime", "Time", "Enabled"}:
            raise ValueError("Target is not an editable effect parameter")
        old = p.eval()
        self._validate_assignment(component, name, cue["value"])
        return p, old

    def start(self, cue, elapsed):
        item = self.prepared[cue["id"]]
        kind = cue["kind"]
        if kind == "visual":
            track = cue["track"]
            old = self.tracks.get(track)
            if old is not None:
                self._detach_running_look(old)
            self.ownerComp.op("track{}_source{}".format(track, item["side"])).par.top = item["deck"].op("out1_image").path
            if float(self._p("Track{}level".format(track))) <= 1e-6:
                # A blackout is a visual boundary. Raising the level while
                # crossfading old->new would reveal the old end frame again.
                # Retire that deck and fade black->new, using only the cue's
                # freshly prepared media in-point and saved animation phase.
                if old is not None:
                    self._release_audio(old["cue"]["id"])
                    self._halt_deck(old)
                    if old.get("old") is not None:
                        self._release_audio(old["old"]["cue"]["id"])
                        self._halt_deck(old["old"])
                old = None
                self._level_fades.pop(track, None)
                self.ownerComp.par["Track{}level".format(track)] = 1
            if old is None:
                previous = self.ownerComp.op("track{}_source{}".format(track, 1-item["side"]))
                previous.lock = False
                previous.par.top = "black"
            item.update(started=elapsed, fading=cue["fade"] > 0, old=old, finished=False)
            self.tracks[track] = item
            self._fade_track_level(track, 1.0, cue, elapsed)
            if item["movie"] is not None:
                item["movie"].par.play = True
            if cue["id"] in self.audio:
                self.audio[cue["id"]]["started"] = elapsed
                self.audio[cue["id"]]["reader"].par.play = True
            # Remove automation ownership when a new visual replaces the track.
            self.automations = {key: value for key, value in self.automations.items() if value["cue"]["track"] != track}
        elif kind == "audio":
            self._release_audio(item.get("replay_voice"))
            item["started"] = elapsed
            item["reader"].par.play = True
        elif kind == "blackout":
            for track in ((1, 2, 3) if cue["blackout_scope"] == "all" else (cue["track"],)):
                self._fade_track_level(track, 0.0, cue, elapsed)
        elif kind == "parameters":
            if self.tracks.get(cue["track"]) is not None:
                self._detach_running_look(self.tracks[cue["track"]])
            parameter, old = self._target(cue)
            self.automations = {key: value for key, value in self.automations.items() if value["parameter"] != parameter}
            self.automations[cue["id"]] = {"cue": cue, "parameter": parameter, "old": old, "started": elapsed}
        elif kind == "stop":
            self._stop_track(cue["track"])
            for pending in list(self.prepared.values()):
                if pending["cue"]["id"] != cue["id"] and pending["cue"]["track"] == cue["track"]:
                    self.stop_cue(pending["cue"])
            for audio in list(self.audio.values()):
                if audio["cue"]["track"] == cue["track"]:
                    self.stop_cue(audio["cue"])
        self.prepared.pop(cue["id"], None)

    def _fade_track_level(self, track, target, cue, elapsed):
        if not hasattr(self, "_level_fades"):
            self._level_fades = {}
        name = "Track{}level".format(track)
        self._level_fades[track] = {"cue": cue, "old": float(self._p(name)),
                                    "target": target, "started": elapsed}
        if cue["fade"] == 0:
            self.ownerComp.par[name] = target
            self._level_fades.pop(track)

    def tick(self, elapsed):
        for track, fade in list(getattr(self, "_level_fades", {}).items()):
            cue = fade["cue"]
            progress = self.model.ease((elapsed - fade["started"]) / cue["fade"], cue["easing"])
            self.ownerComp.par["Track{}level".format(track)] = fade["old"] + (fade["target"] - fade["old"]) * progress
            if progress >= 1:
                self._level_fades.pop(track)
        for track, item in self.tracks.items():
            if item.get("finished"):
                continue
            cue = item["cue"]
            age = max(0, elapsed - item["started"])
            progress = 1.0 if cue["fade"] == 0 else self.model.ease(age / cue["fade"], cue["easing"])
            self.ownerComp.par["Track{}blend".format(track)] = progress if item["side"] else 1.0 - progress
            self.ownerComp.par["Track{}visible".format(track)] = True
            if item.get("old") and progress >= 1:
                self._release_audio(item["old"]["cue"]["id"])
                self._halt_deck(item["old"])
                item["old"] = None
            item["fading"] = progress < 1
            for active in (item, item.get("old")):
                if active:
                    local_time = max(0, elapsed - active["started"])
                    for module in (*self.model.MODULES, "fx_rack"):
                        component = active["deck"].op(module)
                        if getattr(component.par, "Manualtime", None) is not None:
                            scale = getattr(component.par, "Timescale", None)
                            component.par.Manualtime = self.model.animation_time(
                                active["deck"].fetch("imagefx_look_animation", {}, search=False), module,
                                local_time, float(scale.eval()) if scale is not None else 1.0)
        for item in self.audio.values():
            if item["started"] is not None:
                cue = item["cue"]
                age = max(0, elapsed - item["started"])
                envelope = min(1, age / cue["fade"]) if cue["fade"] else 1
                if cue["duration"] and cue["fade"]:
                    envelope = min(envelope, max(0, (cue["duration"] - age) / cue["fade"]))
                track = self.tracks.get(cue["track"])
                if cue["kind"] == "visual" and track and track.get("old") and track["old"]["cue"]["id"] == cue["id"]:
                    fade = track["cue"]["fade"]
                    progress = 1 if fade == 0 else self.model.ease((elapsed-track["started"])/fade, track["cue"]["easing"])
                    envelope *= 1-progress
                item["gain"].par.gain = envelope * cue["gain"]
        for key, item in list(self.automations.items()):
            cue = item["cue"]
            progress = 1 if cue["duration"] == 0 else self.model.ease((elapsed - item["started"]) / cue["duration"], cue["easing"])
            old, new = item["old"], cue["value"]
            if not item["parameter"].isMenu and not item["parameter"].isToggle:
                item["parameter"].val = float(old) + (float(new) - float(old)) * progress
            elif progress >= 1:
                item["parameter"].val = new
            if progress >= 1:
                self.automations.pop(key)

    def _halt_deck(self, item):
        self._detach_running_look(item)
        if item.get("movie") is not None:
            item["movie"].par.play = False
        item["deck"].allowCooking = False

    def finish(self, cue):
        if cue["kind"] == "visual":
            self._release_audio(cue["id"])
        if cue["kind"] == "visual":
            item = self.tracks.get(cue["track"])
            if item and item["cue"]["id"] == cue["id"]:
                self._detach_running_look(item)
                if cue["hold"]:
                    # A disabled COMP can invalidate textures selected outside
                    # it. Cache the live image before halting its network.
                    source_top = self.ownerComp.op("track{}_source{}".format(cue["track"], item["side"]))
                    source_top.cook(force=True)
                    source_top.lock = True
                    self._halt_deck(item)
                    if item.get("old"):
                        self._release_audio(item["old"]["cue"]["id"])
                        self._halt_deck(item["old"])
                    item["old"] = None
                    item["fading"] = False
                    self.ownerComp.par["Track{}blend".format(cue["track"])] = item["side"]
                    item["finished"] = True
                else:
                    self._stop_track(cue["track"])
        elif cue["kind"] == "audio":
            self.stop_cue(cue)
        elif cue["kind"] == "blackout":
            # Duration may be shorter than Fade; finish at black, but never
            # override a newer visual cue that has already taken ownership.
            for track, fade in list(getattr(self, "_level_fades", {}).items()):
                if fade["cue"]["id"] == cue["id"]:
                    self.ownerComp.par["Track{}level".format(track)] = 0
                    self._level_fades.pop(track)

    def _stop_track(self, track):
        item = self.tracks.get(track)
        if item:
            self._detach_running_look(item)
        self.tracks.pop(track, None)
        if item:
            self._release_audio(item["cue"]["id"])
            self._halt_deck(item)
            if item.get("old"):
                self._release_audio(item["old"]["cue"]["id"])
                self._halt_deck(item["old"])
        self.ownerComp.par["Track{}visible".format(track)] = False
        self.ownerComp.par["Track{}level".format(track)] = 1
        getattr(self, "_level_fades", {}).pop(track, None)
        # Otherwise the next fade can expose an old deck after STOP ALL.
        for side in (0, 1):
            source_top = self.ownerComp.op("track{}_source{}".format(track, side))
            source_top.lock = False
            source_top.par.top = "black"
        self.automations = {key: value for key, value in self.automations.items() if value["cue"]["track"] != track}

    def stop_cue(self, cue):
        prepared = self.prepared.pop(cue["id"], None)
        if prepared and prepared.get("deck"):
            self._halt_deck(prepared)
        self._release_audio(cue["id"])
        track = self.tracks.get(cue["track"])
        if track and track["cue"]["id"] == cue["id"]:
            self._stop_track(cue["track"])
        elif track and track.get("old") and track["old"]["cue"]["id"] == cue["id"]:
            old = track["old"]
            self._halt_deck(old)
            source_top = self.ownerComp.op("track{}_source{}".format(cue["track"], old["side"]))
            source_top.lock = False
            source_top.par.top = "black"
            track["old"] = None
        self.automations.pop(cue["id"], None)
        for track, fade in list(getattr(self, "_level_fades", {}).items()):
            if fade["cue"]["id"] == cue["id"]:
                self._level_fades.pop(track)  # Freeze level; stopping blackout must not reveal content.

    def _release_audio(self, cue_id):
        item = self.audio.pop(cue_id, None)
        if item:
            for key in ("gain", "stereo", "callback", "reader"):
                if item.get(key) is not None:
                    item[key].destroy()

    def stop_all(self):
        self.StopLiveLook()
        for item in list(self.audio.values()):
            self.stop_cue(item["cue"])
        for track in (1, 2, 3):
            self._stop_track(track)
        for item in self.prepared.values():
            if item.get("deck"):
                self._halt_deck(item)
        self.prepared.clear()
        self.automations.clear()

    def pause(self, paused):
        for item in self.tracks.values():
            for active in (item, item.get("old")):
                if active and not active.get("finished"):
                    source_top = self.ownerComp.op("track{}_source{}".format(active["cue"]["track"], active["side"]))
                    if paused:
                        active["pause_source_lock"] = bool(source_top.lock)
                        source_top.cook(force=True)
                        source_top.lock = True
                    active["deck"].allowCooking = not paused
                    if not paused:
                        source_top.lock = active.pop("pause_source_lock", False)
                    if active.get("movie") is not None:
                        active["movie"].par.play = not paused
        for item in self.audio.values():
            item["reader"].par.play = not paused and item["started"] is not None

    def Go(self):
        self._guard_no_look_edit(allow_running=True)
        queued = self.engine.go(int(self._p("Selectedcue")) - 1)
        self.SelectCue(min(len(self.document["cues"]), self.engine.selected + 1))
        self._status("GO queued; waiting for pre-wait and media readiness" if queued else "No cue queued (disabled or end of list)")
        self.Refresh()

    def Pause(self):
        self.engine.pause()
        self.Refresh()

    def GoBack(self):
        self._guard_no_look_edit(allow_running=True)
        queued = self.engine.go_back()
        if queued:
            self.SelectCue(min(len(self.document["cues"]), self.engine.selected + 1))
        self._status("Go Back queued; previous cue restarts after preload/pre-wait" if queued else "No previous enabled cue")
        self.Refresh()

    def Resume(self):
        self._guard_no_look_edit(allow_running=True)
        self.engine.resume()
        self.Refresh()

    def Stopall(self):
        self.engine.stop()
        self._status("Stopped; all tracks and audio voices cleared")
        self.Refresh()

    def Stopcue(self):
        self.engine.stop_cue(int(self._p("Selectedcue")) - 1)
        self.Refresh()

    def Preload(self):
        index = int(self._p("Selectedcue")) - 1
        if 0 <= index < len(self.document["cues"]):
            self.prepare(self.document["cues"][index])
            self._status("Preparing selected cue off-air; GO waits until the look and media are ready")

    def Preflight(self):
        problems = []
        for index, cue in enumerate(self.document["cues"]):
            try:
                if cue["kind"] in {"visual", "audio"}:
                    self.model.validate_look_media(cue["look"],Path(self._p("Showfile")).resolve().parent)
                    self.model.resolve_layer_files(
                        cue["look"].get("layer_files", {}), Path(self._p("Showfile")).resolve().parent,
                        selections=cue["look"].get("modules", {}).get("layer_composite", {}),
                        enabled=cue["look"].get("toggles", {}).get("Layercompositeenabled", False),
                    )
                    workflow = self.ownerComp.op("deck_template/workflow").module
                    workflow.validate_order(cue["look"].get("order", list(workflow.DEFAULT_ORDER)))
                    path = self._media_path(cue)
                    if cue["kind"] == "audio" and not path:
                        raise ValueError("Audio cue needs a media file")
            except Exception as exc:
                problems.append("{}: {}".format(index + 1, exc))
        self._status("Preflight: " + ("; ".join(problems) if problems else "all referenced media files exist"))
        return problems

    def SaveShow(self):
        self._guard_no_look_edit()
        from tdimagefx.jsonutil import atomic_write_json, load_json
        path = Path(self._p("Showfile"))
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
            raise ValueError("Show destination may not traverse symbolic links")
        path = path.resolve()
        if path.suffix.lower() != ".json":
            raise ValueError("Show file must end in .json")
        mapping = {
            p.name: p.eval() for p in self.ownerComp.customPars
            if self._mapping_parameter(p)
        }
        for name, value in mapping.items():
            self._validate_mapping_assignment(name, value)
        self._mapping_matrices(mapping)
        document = self.model.validate_show(dict(self.document, mapping=mapping))
        if len(json.dumps(document, ensure_ascii=False, allow_nan=False).encode("utf-8")) > self.model.MAX_SHOW_BYTES:
            raise ValueError("Show exceeds 8 MiB")
        if path.is_file():
            if path.stat().st_size > self.model.MAX_SHOW_BYTES:
                raise ValueError("Existing show file is unexpectedly large")
            previous = load_json(path)
            self.model.validate_show(previous)
            atomic_write_json(path.with_name(path.stem + ".backup-" + self.model.new_cue()["id"] + ".json"), previous)
        atomic_write_json(path, document)
        self.document = document
        self._save_document_dat()
        self._status("Show saved with all 3 projector mappings and cues; media/mask images stay in their original local files")

    def LoadShow(self):
        self._guard_edit()
        from tdimagefx.jsonutil import load_json
        path = Path(self._p("Showfile")).resolve()
        if path.stat().st_size > self.model.MAX_SHOW_BYTES:
            raise ValueError("Show file exceeds 8 MiB")
        document = self.model.validate_show(load_json(path))
        parameters = {p.name:p for p in self.ownerComp.customPars if self._mapping_parameter(p)}
        if set(document["mapping"]) - set(parameters):
            raise ValueError("Show contains unknown mapping controls")
        # Loading is a complete calibration restore, not a patch over the last
        # show. Resolve missing legacy controls to defaults before validation.
        mapping = {name:document["mapping"].get(name,p.default) for name,p in parameters.items()}
        for name, value in mapping.items():
            self._validate_mapping_assignment(name, value)
        self._mapping_matrices(mapping)
        self._replace_cues(document["cues"])
        self.ownerComp.par.Masterblackout = True
        self.ownerComp.par.Audioenabled = False
        for name, value in mapping.items():
            parameters[name].val = value
        self.UpdateMapping()
        polygon = self.ownerComp.op('projection_polygon')
        editor = self.ownerComp.op('polygon_editor')
        if polygon is not None and editor is not None:
            polygon.module.open_editor(self.ownerComp,polygon.module.state_for(editor)['target'],open_window=False)
        self.document = document
        self._save_document_dat()
        self.SelectCue(1)
        self._status("Show loaded safely: blackout on, audio off")

    def Openoutputs(self):
        controller = self.ownerComp.op("show_output_mode")
        if controller is None:
            raise ValueError("Install Output Mode before opening physical outputs")
        controller.module.on_pulse(self.ownerComp, "Openoutput")

    def Closeoutputs(self):
        controller = self.ownerComp.op("show_output_mode")
        if controller is not None:
            controller.module.on_pulse(self.ownerComp, "Closealloutputs")
        else:
            self.ownerComp.op("audience_window").par.winclose.pulse()

    def Edit(self):
        ui.openCOMPEditor(self.ownerComp)

    def Tick(self):
        try:
            selected_before = self.engine.selected
            self._service_preloads()
            self.engine.tick()
            if self.engine.selected != selected_before:
                self.SelectCue(self.engine.selected + 1)
            self.UpdateMapping()
            if self.engine.errors:
                self._status("Cue error: " + next(reversed(self.engine.errors.values())))
            if time.monotonic() - self._ui_time >= 0.2:
                self.Refresh()
                self._ui_time = time.monotonic()
        except Exception as exc:
            self._status("Show error: " + str(exc))
            self.engine.state = "paused"
            self.pause(True)

    def _mapping_parameter(self, parameter):
        if parameter.page.name not in {'Routing', 'Output 1', 'Output 2', 'Output 3'}:
            return False
        return self._safe_parameter(parameter) or parameter.name in {
            'Output1maskfile', 'Output2maskfile', 'Output3maskfile',
            'Output1maskpolygon', 'Output2maskpolygon', 'Output3maskpolygon'}

    def _validate_mapping_assignment(self, name, value):
        if name in {'Output1maskpolygon', 'Output2maskpolygon', 'Output3maskpolygon'}:
            runtime = self.ownerComp.op('projection_polygon')
            if runtime is None or not isinstance(value,str):
                raise ValueError('Polygon mapping requires a valid coordinate list')
            runtime.module.decode_polygon(value)
            return self.ownerComp.par[name]
        if name in {'Output1maskfile', 'Output2maskfile', 'Output3maskfile'}:
            runtime = self.ownerComp.op('projection_mapping')
            if runtime is None:
                raise ValueError('Install Projection Mapping before loading image masks')
            runtime.module.mask_file_value(value)
            return self.ownerComp.par[name]
        return self._validate_assignment(self.ownerComp, name, value)

    def UpdateMapping(self):
        values = tuple((p.name, p.eval()) for p in self.ownerComp.customPars if self._mapping_parameter(p))
        if values == self._mapping_key:
            self.ownerComp.par.Mappingstatus = "Mapping valid"
            return
        try:
            matrices = self._mapping_matrices()
        except ValueError as exc:
            self.ownerComp.par.Mappingstatus = str(exc)
            return
        for output, matrix in enumerate(matrices, 1):
            shader = self.ownerComp.op("mapped{}".format(output))
            for row in range(3):
                for col, axis in enumerate("xyz"):
                    shader.par["vec{}value{}".format(row, axis)] = matrix[row * 3 + col]
            prefix = "Output{}".format(output)
            data = self.ownerComp.op('projection_crop_data')
            for column, (axis, edge) in enumerate(zip("xyzw", ("left", "bottom", "right", "top"))):
                crop = self._p(prefix + "crop" + edge)
                if data is not None:
                    data[output-1, column] = crop
                if edge in {"left", "right"} and self._p("Routingmode") == "panoramic":
                    overlap = self._p("Panoramaoverlap")
                    crop = ((output - 1) * (1 - overlap) + crop) / (3 - 2 * overlap)
                shader.par["vec3value" + axis] = crop
        self._sync_canvas_resolution()
        self._mapping_key = values
        self.ownerComp.par.Mappingstatus = "Mapping valid"

    def _mapping_matrices(self, overrides=None):
        overrides = overrides or {}
        def value(name):
            return overrides.get(name, self._p(name))
        result = []
        for output in (1, 2, 3):
            prefix = "Output{}".format(output)
            if value(prefix + "cropleft") >= value(prefix + "cropright") or value(prefix + "cropbottom") >= value(prefix + "croptop"):
                raise ValueError("Output {} crop must have positive width and height".format(output))
            corners = [(value(prefix + corner + "x"), value(prefix + corner + "y")) for corner in ("bl", "br", "tr", "tl")]
            result.append(self.model.inverse_quad(corners))
        return result

    def Refresh(self):
        table = self.ownerComp.op("cue_list")
        table.clear()
        table.appendRow(["#", "Cue", "Type", "Track", "At", "Duration", "State"])
        lines = [" #   CUE                              TYPE        TRACK    AT        STATE"]
        for index, cue in enumerate(self.document["cues"]):
            state = "error" if cue["id"] in self.engine.errors else "running" if cue["id"] in self.engine.active else "waiting" if cue["id"] in self.engine.pending else "loaded" if cue["id"] in self.prepared else "disabled" if not cue["enabled"] else "ready"
            at = "GO" if cue["at"] is None else "{:.2f}".format(cue["at"])
            table.appendRow([index + 1, cue["name"], cue["kind"], cue["track"], at, cue["duration"], state])
            marker = ">" if index + 1 == int(self._p("Selectedcue")) else " "
            lines.append("{}{:3d}  {:32.32s} {:10s}    {}    {:8s}  {}".format(marker, index + 1, cue["name"], cue["kind"], cue["track"], at, state))
        self.ownerComp.op("cue_text").text = "\n".join(lines)
        self.ownerComp.par.Showtime = self.engine.elapsed
        self.ownerComp.par.Transport = self.engine.state
        for row in range(12):
            button = self.ownerComp.op("cue_row_{}".format(row))
            notes = self.ownerComp.op("cue_notes_{}".format(row))
            if button is not None:
                button.par.label = self.CueLabel(row, compact=notes is not None)
            if notes is not None:
                notes.par.label = self.CueRowNotes(row)

    def Action(self, name):
        try:
            actions = {
                "Gocue": self.Go, "Goback": self.GoBack, "Pause": self.Pause, "Resume": self.Resume,
                "Stopall": self.Stopall, "Stopcue": self.Stopcue, "Preload": self.Preload,
                "Addcue": self.AddCue, "Addblackout": self.AddBlackout, "Duplicatecue": self.DuplicateCue,
                "Removecue": self.RemoveCue, "Applycue": self.ApplyCue,
                "Capturelook": self.CaptureLook, "Saveshow": self.SaveShow,
                "Recalllook": self.RecallLook, "Updatelook": self.UpdateLook,
                "Editrunninglook": self.EditRunningLook,
                "Savelookasnew": self.SaveLookAsNew, "Cancellook": self.CancelLook,
                "Loadshow": self.LoadShow, "Preflight": self.Preflight,
                "Openoutputs": self.Openoutputs, "Closeoutputs": self.Closeoutputs,
                "Cueup": lambda: self.MoveCue(-1), "Cuedown": lambda: self.MoveCue(1),
                "Selectcue": self.SelectCue,
                "Showlooklive": self.ShowLiveLook, "Stoplooklive": self.StopLiveLook,
                "Savecuenotes": self.SaveCueNotes, "Opencuenotes": self.OpenCueNotes,
            }
            if name not in actions:
                raise ValueError("Unknown action")
            actions[name]()
        except Exception as exc:
            self._status(str(exc))
