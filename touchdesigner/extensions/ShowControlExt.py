"""ImageFX cue player. Audience windows/audio are never armed on startup."""

from __future__ import annotations

import copy
import json
import math
import sys
import time
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
        self._mapping_key = None
        self._ui_time = 0.0
        self._busy = False
        # A user may save a working TOE during rehearsal. Never resurrect its
        # dynamic media readers/voices when reopening or reinitializing it.
        ownerComp.par.Audioenabled = False
        ownerComp.par.Masterblackout = True
        for node in list(ownerComp.children):
            if node.fetch("imagefx_show_runtime", False, search=False):
                node.destroy()
        for track in (1, 2, 3):
            ownerComp.par["Track{}visible".format(track)] = False
            ownerComp.par["Track{}blend".format(track)] = 0
            for side in (0, 1):
                ownerComp.op("track{}_source{}".format(track, side)).par.top = "black"
        template = ownerComp.op("deck_template")
        template.allowCooking = True
        template.op("fx_rack").initializeExtensions()
        self._default_rack = json.loads(template.op("fx_rack").ExportPreset())
        template.allowCooking = False
        ownerComp.par.Audioenabled = False
        ownerComp.par.Masterblackout = True
        self.SelectCue(1)
        self.Refresh()

    def _p(self, name):
        return self.ownerComp.par[name].eval()

    def _status(self, message):
        self.ownerComp.par.Status = str(message)[:500]

    def _guard_edit(self):
        if self.engine.state != "stopped":
            raise ValueError("Stop All before editing/loading the show")

    def _save_document_dat(self):
        self.ownerComp.op("show_data").text = json.dumps(self.document, indent=2, allow_nan=False)

    def _replace_cues(self, cues):
        self._guard_edit()
        document = self.model.validate_show(dict(self.document, cues=cues))
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
        self.ownerComp.par.Selectedcue = index
        cue = self.document["cues"][index - 1]
        names = {
            "Cuename": "name", "Cuekind": "kind", "Mediafile": "source", "Track": "track",
            "Prewait": "prewait", "Duration": "duration", "Fade": "fade", "Follow": "follow",
            "Postwait": "postwait", "Loop": "loop", "Mediain": "media_in", "Speed": "speed",
            "Gain": "gain", "Hold": "hold", "Target": "target", "Easing": "easing",
            "Cueenabled": "enabled", "Notes": "notes", "Movieaudio": "movie_audio",
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

    def CueLabel(self, row):
        index = (int(self._p("Cuepage")) - 1) * 12 + row
        if index >= len(self.document["cues"]):
            return ""
        cue = self.document["cues"][index]
        state = "ERROR" if cue["id"] in self.engine.errors else "PLAY" if cue["id"] in self.engine.active else "WAIT" if cue["id"] in self.engine.pending else "disabled" if not cue["enabled"] else "ready"
        return "{} {:03d}   {}   | {} / track {} | {}".format(">" if int(self._p("Selectedcue")) == index + 1 else "", index + 1, cue["name"][:48], cue["kind"], cue["track"], state)

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

    def AddCue(self):
        cues = copy.deepcopy(self.document["cues"])
        cues.append(self.model.new_cue())
        self._replace_cues(cues)
        self.SelectCue(len(cues))

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
        demo = self.ownerComp.parent()
        look = {"toggles": {name: bool(demo.par[name]) for name in self.model.TOGGLES}, "modules": {}}
        for name in self.model.MODULES:
            module = demo.op(name)
            look["modules"][name] = {
                p.name: p.eval() for p in module.customPars
                if self._safe_parameter(p) and p.name not in {"Enabled", "Autotime", "Manualtime"}
            }
        look["rack"] = json.loads(demo.op("fx_rack").ExportPreset())
        look["order"] = demo.op("workflow").module.current(demo)
        layer = demo.op("layer_composite")
        look["layer_files"] = self.model.resolve_layer_files(
            {name: layer.par[name].eval() for name in ("Backdropfile", "Topfile")},
            project.folder,
            selections=look["modules"]["layer_composite"],
            enabled=look["toggles"]["Layercompositeenabled"],
        )
        cues = copy.deepcopy(self.document["cues"])
        cues[index]["look"] = look
        self._replace_cues(cues)
        self.SelectCue(index + 1)
        self._status("Captured the demo modules and eight-slot rack into this cue")

    @staticmethod
    def _safe_parameter(parameter):
        return parameter is not None and not parameter.readOnly and not parameter.isPulse and (
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

    def _apply_look(self, deck, look):
        if set(look) - {"toggles", "modules", "rack", "layer_files", "order"}:
            raise ValueError("Unknown look fields")
        workflow = deck.op("workflow").module
        order = workflow.validate_order(look.get("order", list(workflow.DEFAULT_ORDER)))
        layer_files = self.model.resolve_layer_files(
            look.get("layer_files", {}), Path(self._p("Showfile")).resolve().parent,
            selections=look.get("modules", {}).get("layer_composite", {}),
            enabled=look.get("toggles", {}).get("Layercompositeenabled", False),
        )
        for name in self.model.TOGGLES:
            deck.par[name] = False
        template = self.ownerComp.op("deck_template")
        for module_name in self.model.MODULES:
            module = deck.op(module_name)
            for parameter in module.customPars:
                if self._safe_parameter(parameter) and parameter.name not in {"Enabled", "Autotime", "Manualtime"}:
                    parameter.val = template.op(module_name).par[parameter.name].eval()
            # Enabled belongs to the deck's routing, not its saved effect values.
            # Assigning .val here previously replaced the expression with False.
            # Repair it on reused decks too, including decks made by older builds.
            module.par.Enabled.expr = "parent().par.{}".format(self.model.MODULE_TOGGLES[module_name])
        for name, value in look.get("toggles", {}).items():
            if name not in self.model.TOGGLES or not isinstance(value, bool):
                raise ValueError("Unknown demo toggle")
            deck.par[name] = value
        for name, value in layer_files.items():
            deck.op("layer_composite").par[name] = value
        for module_name, parameters in look.get("modules", {}).items():
            if module_name not in self.model.MODULES or not isinstance(parameters, dict):
                raise ValueError("Unknown module in look")
            for name, value in parameters.items():
                if name in {"Enabled", "Time", "Autotime", "Manualtime"}:
                    raise ValueError("Look may not override cue-owned timing/routing")
                self._assign(deck.op(module_name), name, value)
        deck.op("fx_rack").ImportPreset(look.get("rack", self._default_rack))
        for module_name in (*self.model.MODULES, "fx_rack"):
            module = deck.op(module_name)
            if getattr(module.par, "Autotime", None) is not None:
                module.par.Autotime = False
                module.par.Manualtime = 0
        deck.op("fx_rack").Reset()
        workflow.apply_order(deck, order)

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
        deck = self.ownerComp.copy(self.ownerComp.op("deck_template"), name=name)
        deck.store("imagefx_show_runtime", True)
        deck.nodeX = 300 + track * 220
        deck.nodeY = -500 - side * 140
        deck.allowCooking = True
        deck.op("fx_rack").initializeExtensions()
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
        if cue["id"] in self.engine.active or any(
            item["cue"]["id"] == cue["id"] for item in self.tracks.values()
        ):
            raise ValueError("Cue is already running or held; stop it before preloading again")
        try:
            self._prepare(cue)
        except Exception:
            self.stop_cue(cue)
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
            raise ValueError("Wait for this track's crossfade to finish before loading another cue")
        side = 1 - state["side"]
        for item in self.prepared.values():
            if item.get("track") == track and item.get("side") == side:
                raise ValueError("Track standby is occupied; Stop All before replacing its prepared cue")
        deck = self._deck(track, side)
        deck.allowCooking = False
        self.prepared[cue["id"]] = {"cue": cue, "deck": deck, "movie": None, "track": track, "side": side}
        self._apply_look(deck, cue["look"])
        deck.par.Resolutionpreset = "custom"
        deck.par.Customwidth.max = 16384
        deck.par.Customwidth.normMax = 16384
        deck.par.Customwidth = int(self._p("Renderwidth") * ((3-2*self._p("Panoramaoverlap")) if self._p("Routingmode") == "panoramic" else 1))
        deck.par.Customheight = int(self._p("Renderheight"))
        movie = deck.op("media")
        if movie is None and path:
            movie = deck.create(moviefileinTOP, "media")
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
        deck.allowCooking = True
        layer = deck.op("layer_composite")
        if layer.par.Enabled.eval():
            for field, node_name in (("Backdropfile", "backdrop_file"), ("Topfile", "top_file")):
                if layer.op("media_status").module.uses_file(layer, node_name.removesuffix("_file")):
                    layer.op(node_name).preload()
        deck.op("out1_image").cook(force=True)
        self.ownerComp.op("track{}_source{}".format(track, side)).par.top = deck.op("out1_image").path
        self.prepared[cue["id"]] = {"cue": cue, "deck": deck, "movie": movie if path else None, "track": track, "side": side}
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

    def ready(self, cue):
        item = self.prepared[cue["id"]]
        deck = item.get("deck")
        if deck is not None and deck.op("layer_composite").par.Enabled.eval():
            layer = deck.op("layer_composite")
            for field, node_name in (("Backdropfile", "backdrop_file"), ("Topfile", "top_file")):
                if not layer.op("media_status").module.uses_file(layer, node_name.removesuffix("_file")):
                    continue
                image = layer.op(node_name)
                image.cook(force=True)
                if image.isInvalid:
                    raise ValueError("Layer image could not be decoded: " + field)
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
        node, name = cue["target"].split("/")
        component = state["deck"].op("fx_rack/" + node if node.startswith("slot") else node)
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
            self.ownerComp.op("track{}_source{}".format(track, item["side"])).par.top = item["deck"].op("out1_image").path
            if old is None:
                self.ownerComp.op("track{}_source{}".format(track, 1-item["side"])).par.top = "black"
            item.update(started=elapsed, fading=cue["fade"] > 0, old=old, finished=False)
            self.tracks[track] = item
            if item["movie"] is not None:
                item["movie"].par.play = True
            if cue["id"] in self.audio:
                self.audio[cue["id"]]["started"] = elapsed
                self.audio[cue["id"]]["reader"].par.play = True
            # Remove automation ownership when a new visual replaces the track.
            self.automations = {key: value for key, value in self.automations.items() if value["cue"]["track"] != track}
        elif kind == "audio":
            item["started"] = elapsed
            item["reader"].par.play = True
        elif kind == "parameters":
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

    def tick(self, elapsed):
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
                            component.par.Manualtime = local_time
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
        if item.get("movie") is not None:
            item["movie"].par.play = False
        item["deck"].allowCooking = False

    def finish(self, cue):
        if cue["kind"] == "visual":
            self._release_audio(cue["id"])
        if cue["kind"] == "visual":
            item = self.tracks.get(cue["track"])
            if item and item["cue"]["id"] == cue["id"]:
                if cue["hold"]:
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

    def _stop_track(self, track):
        item = self.tracks.pop(track, None)
        if item:
            self._release_audio(item["cue"]["id"])
            self._halt_deck(item)
            if item.get("old"):
                self._release_audio(item["old"]["cue"]["id"])
                self._halt_deck(item["old"])
        self.ownerComp.par["Track{}visible".format(track)] = False
        # Otherwise the next fade can expose an old deck after STOP ALL.
        for side in (0, 1):
            self.ownerComp.op("track{}_source{}".format(track, side)).par.top = "black"
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
            self.ownerComp.op("track{}_source{}".format(cue["track"], old["side"])).par.top = "black"
            track["old"] = None
        self.automations.pop(cue["id"], None)

    def _release_audio(self, cue_id):
        item = self.audio.pop(cue_id, None)
        if item:
            for key in ("gain", "stereo", "callback", "reader"):
                if item.get(key) is not None:
                    item[key].destroy()

    def stop_all(self):
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
                    active["deck"].allowCooking = not paused
                    if active.get("movie") is not None:
                        active["movie"].par.play = not paused
        for item in self.audio.values():
            item["reader"].par.play = not paused and item["started"] is not None

    def Go(self):
        queued = self.engine.go(int(self._p("Selectedcue")) - 1)
        self.SelectCue(min(len(self.document["cues"]), self.engine.selected + 1))
        self._status("GO queued; waiting for pre-wait and media readiness" if queued else "No cue queued (disabled or end of list)")
        self.Refresh()

    def Pause(self):
        self.engine.pause()
        self.Refresh()

    def Resume(self):
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
            self._status("Prepared selected cue; GO waits for media readiness")

    def Preflight(self):
        problems = []
        for index, cue in enumerate(self.document["cues"]):
            try:
                if cue["kind"] in {"visual", "audio"}:
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
        self._guard_edit()
        from tdimagefx.jsonutil import atomic_write_json, load_json
        path = Path(self._p("Showfile"))
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
            raise ValueError("Show destination may not traverse symbolic links")
        path = path.resolve()
        if path.suffix.lower() != ".json":
            raise ValueError("Show file must end in .json")
        mapping = {
            p.name: p.eval() for p in self.ownerComp.customPars
            if p.page.name in {"Routing", "Output 1", "Output 2", "Output 3"} and self._safe_parameter(p)
        }
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
        self._status("Show saved; media stays in its original local files")

    def LoadShow(self):
        self._guard_edit()
        from tdimagefx.jsonutil import load_json
        path = Path(self._p("Showfile")).resolve()
        if path.stat().st_size > self.model.MAX_SHOW_BYTES:
            raise ValueError("Show file exceeds 8 MiB")
        document = self.model.validate_show(load_json(path))
        allowed = {p.name for p in self.ownerComp.customPars if p.page.name in {"Routing", "Output 1", "Output 2", "Output 3"} and self._safe_parameter(p)}
        if set(document["mapping"]) - allowed:
            raise ValueError("Show contains unknown mapping controls")
        for name, value in document["mapping"].items():
            self._validate_assignment(self.ownerComp, name, value)
        self._mapping_matrices(document["mapping"])
        self._replace_cues(document["cues"])
        for name, value in document["mapping"].items():
            self._assign(self.ownerComp, name, value)
        self.document = document
        self.ownerComp.par.Masterblackout = True
        self.ownerComp.par.Audioenabled = False
        self._save_document_dat()
        self.SelectCue(1)
        self._status("Show loaded safely: blackout on, audio off")

    def Openoutputs(self):
        self.ownerComp.op("audience_window").par.winopen.pulse()

    def Closeoutputs(self):
        self.ownerComp.op("audience_window").par.winclose.pulse()

    def Edit(self):
        ui.openCOMPEditor(self.ownerComp)

    def Tick(self):
        try:
            selected_before = self.engine.selected
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

    def UpdateMapping(self):
        values = tuple((p.name, p.eval()) for p in self.ownerComp.customPars if p.page.name in {"Routing", "Output 1", "Output 2", "Output 3"} and self._safe_parameter(p))
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
            for axis, edge in zip("xyzw", ("left", "bottom", "right", "top")):
                crop = self._p(prefix + "crop" + edge)
                if edge in {"left", "right"} and self._p("Routingmode") == "panoramic":
                    overlap = self._p("Panoramaoverlap")
                    crop = ((output - 1) * (1 - overlap) + crop) / (3 - 2 * overlap)
                shader.par["vec3value" + axis] = crop
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
            if button is not None:
                button.par.label = self.CueLabel(row)

    def Action(self, name):
        try:
            actions = {
                "Gocue": self.Go, "Pause": self.Pause, "Resume": self.Resume,
                "Stopall": self.Stopall, "Stopcue": self.Stopcue, "Preload": self.Preload,
                "Addcue": self.AddCue, "Duplicatecue": self.DuplicateCue,
                "Removecue": self.RemoveCue, "Applycue": self.ApplyCue,
                "Capturelook": self.CaptureLook, "Saveshow": self.SaveShow,
                "Loadshow": self.LoadShow, "Preflight": self.Preflight,
                "Openoutputs": self.Openoutputs, "Closeoutputs": self.Closeoutputs,
                "Cueup": lambda: self.MoveCue(-1), "Cuedown": lambda: self.MoveCue(1),
                "Selectcue": self.SelectCue,
            }
            if name not in actions:
                raise ValueError("Unknown action")
            actions[name]()
        except Exception as exc:
            self._status(str(exc))
