"""Portable cue scheduling and planar mapping math (no TouchDesigner imports)."""

from __future__ import annotations

import copy
import math
import re
import time
import uuid
from pathlib import Path


SHOW_KIND = "tdimagefx.show"
MAX_CUES = 1000
MAX_SHOW_BYTES = 8 * 1024 * 1024
MODULES = (
    "reference_particle_field", "calligraphic_shadow", "ink_orbit_canvas",
    "ink_flow", "particle_random_move", "glitch_fusion", "color_adjustment",
    "motion_studio", "ink_dream_flow", "ink_brush_flow", "ink_radial_flow", "layer_composite", "final_crop", "color_switch", "image_composition", "dance_puppet",
)
TOGGLES = (
    "Referenceparticlefieldenabled", "Calligraphicshadowenabled", "Inkorbitenabled",
    "Inkflowenabled", "Particlesenabled", "Glitchenabled", "Coloradjustmentenabled",
    "Motionenabled", "Applyvideofx", "Inkdreamenabled", "Inkbrushenabled", "Inkradialenabled", "Layercompositeenabled", "Finalcropenabled", "Colorswitchenabled", "Imagecompositionenabled", "Dancepuppetenabled",
)
MODULE_TOGGLES = {
    "reference_particle_field": "Referenceparticlefieldenabled",
    "calligraphic_shadow": "Calligraphicshadowenabled",
    "ink_orbit_canvas": "Inkorbitenabled",
    "ink_flow": "Inkflowenabled",
    "particle_random_move": "Particlesenabled",
    "glitch_fusion": "Glitchenabled",
    "color_adjustment": "Coloradjustmentenabled",
    "motion_studio": "Motionenabled",
    "ink_dream_flow": "Inkdreamenabled",
    "ink_brush_flow": "Inkbrushenabled",
    "ink_radial_flow": "Inkradialenabled",
    "layer_composite": "Layercompositeenabled",
    "final_crop": "Finalcropenabled",
    "color_switch": "Colorswitchenabled",
    "image_composition": "Imagecompositionenabled",
    "dance_puppet": "Dancepuppetenabled",
}


FLOW_MODULES = ('ink_dream_flow', 'ink_brush_flow', 'ink_radial_flow')


def with_legacy_motion_media(look, *, force_files=None, puppet_files=None):
    """Seed absent, pre-feature media from the local designer, never cue values.

    Only the runtime/draft is expanded. Existing files (including explicit blank
    paths) are authoritative. A cue that already has motion controls but lost its
    media is not a legacy cue and must still fail normal media validation.
    """
    result = copy.deepcopy(look)
    modules = result.get('modules', {})
    for name in FLOW_MODULES:
        if (name not in result.get('force_files', {})
                and 'Danceenabled' not in modules.get(name, {})
                and name in (force_files or {})):
            result.setdefault('force_files', {})[name] = copy.deepcopy(force_files[name])
    if ('puppet_files' not in result and 'dance_puppet' not in modules
            and not result.get('toggles', {}).get('Dancepuppetenabled', False)
            and puppet_files is not None):
        result['puppet_files'] = copy.deepcopy(puppet_files)
    return result


def resolve_force_files(values, base_dir, *, modules=None, toggles=None, active=True):
    """Passive local force caches only. A show cannot start inference/capture."""
    if not isinstance(values, dict) or set(values)-set(FLOW_MODULES):
        raise ValueError('Unknown Dance Forces module')
    result = {}
    for module in FLOW_MODULES:
        files = values.get(module, {})
        if not isinstance(files, dict) or set(files)-{'Dancevideo','Dancecache'}:
            raise ValueError('Unknown Dance Forces media fields')
        controls = (modules or {}).get(module,{})
        mode = controls.get('Dancesource','recorded')
        if mode not in {'recorded','live'}: raise ValueError('Invalid Dance Forces source')
        needed = active and (toggles or {}).get(MODULE_TOGGLES[module],False) and controls.get('Danceenabled',False) and mode=='recorded'
        result[module] = {}
        for name in ('Dancevideo','Dancecache'):
            raw = files.get(name,'')
            if not isinstance(raw,str) or len(raw)>4096 or '://' in raw or '\x00' in raw:
                raise ValueError('Dance Forces media must be local file paths')
            if not raw.strip():
                if needed and name=='Dancecache': raise ValueError('Analyze dancers video before capturing Dance Forces')
                result[module][name] = ''; continue
            path = Path(raw)
            if not path.is_absolute(): path = Path(base_dir)/path
            if needed and name=='Dancecache' and not path.is_file():
                raise ValueError('Missing prepared Dance Forces cache: '+path.name)
            result[module][name] = str(path.resolve())
    return result


def resolve_puppet_files(values, base_dir, *, selections=None, enabled=True):
    """Passive puppet asset paths only. Shows cannot launch code or cameras."""
    names={'Renderfile','Fanrenderfile','Chainrenderfile','Dancevideo','Motioncache','Characterprofile'}
    if not isinstance(values,dict) or set(values)-names:
        raise ValueError('Unknown puppet media fields')
    mode=(selections or {}).get('Sourcemode','recorded')
    if mode not in {'recorded','live'}: raise ValueError('Invalid puppet source mode')
    characters=(selections or {}).get('Characters','both')
    if characters not in {'both','fan','chain'}: raise ValueError('Invalid puppet character mode')
    required={'both':'Renderfile','fan':'Fanrenderfile','chain':'Chainrenderfile'}[characters]
    result={}
    for name in names:
        raw=values.get(name,'')
        if not isinstance(raw,str) or len(raw)>4096 or '://' in raw or '\x00' in raw:
            raise ValueError('Puppet media must be local file paths')
        if not raw.strip():
            if enabled and mode=='recorded' and name==required: raise ValueError('Puppet cue needs a prepared '+characters+' RGBA movie (rebuild motion)')
            result[name]=''; continue
        path=Path(raw)
        if not path.is_absolute(): path=Path(base_dir)/path
        if enabled and mode=='recorded' and name==required and not path.is_file():
            raise ValueError('Missing prepared puppet movie: '+path.name)
        result[name]=str(path.resolve())
    return result


def composition_activity(look, active=True, branch=False):
    """A/B may be consumed by the layout or directly by Layer Composite."""
    modules=look.get('modules',{}); toggles=look.get('toggles',{})
    selected=modules.get('image_composition',{})
    requested=set()
    if active and toggles.get('Layercompositeenabled',False):
        layer=modules.get('layer_composite',{})
        requested={value[-1].upper() for value in (layer.get('Backdropsource'),layer.get('Topsource')) if value in {'effects_a','effects_b'}}
    if requested:
        if branch: raise ValueError('Independent A/B effects cannot recursively reference their own composition')
        order=look.get('order',[])
        if 'image_composition' in order and 'layer_composite' in order and order.index('image_composition')>order.index('layer_composite'):
            raise ValueError('Two-Image Composition must precede Layer Composite for independent A/B sources')
    return {p:bool(active and selected.get(p+'visible',True) and (toggles.get('Imagecompositionenabled',False) or p in requested)) for p in ('A','B')}


def resolve_composition_files(values, base_dir, *, selections=None, enabled=True, active_prefixes=None):
    """Resolve only passive A/B media; never allow executable operator paths."""
    if not isinstance(values,dict) or set(values)-{'Afile','Bfile'}:
        raise ValueError('Unknown Two-Image Composition media fields')
    selections=selections or {}; result={}
    for prefix in ('A','B'):
        name=prefix+'file'; raw=values.get(name,'')
        if not isinstance(raw,str) or len(raw)>4096 or '://' in raw or '\x00' in raw:
            raise ValueError('Composition media must be local file paths')
        selection=selections.get(prefix+'source','auto')
        if selection not in {'auto','file','input','transparent'}: raise ValueError('Invalid composition source')
        if not raw.strip(): result[name]=''; continue
        path=Path(raw)
        if not path.is_absolute(): path=Path(base_dir)/path
        needed=enabled and selections.get(prefix+'visible',True) and (active_prefixes is None or prefix in active_prefixes)
        if needed and selection in {'auto','file'} and not path.is_file():
            raise ValueError('Missing composition media: '+path.name)
        result[name]=str(path.resolve())
    return result


def validate_look_media(look, base_dir, *, active=True, branch=False):
    """Preflight nested local sources even when the main cue source is blank."""
    if not isinstance(look,dict): raise ValueError('Look must be an object')
    validate_look_animation(look, branch=branch)
    modules=look.get('modules',{}); toggles=look.get('toggles',{})
    resolve_force_files(look.get('force_files',{}),base_dir,modules=modules,toggles=toggles,active=active)
    resolve_puppet_files(look.get('puppet_files',{}),base_dir,selections=modules.get('dance_puppet',{}),enabled=active and toggles.get('Dancepuppetenabled',False))
    resolve_layer_files(look.get('layer_files',{}),base_dir,selections=modules.get('layer_composite',{}),enabled=active and toggles.get('Layercompositeenabled',False))
    branches=look.get('branches',{})
    if not isinstance(branches,dict) or set(branches)-{'a_effects','b_effects'}: raise ValueError('Unknown composition branch')
    if branch and (branches or 'composition_files' in look or 'image_composition' in modules):
        raise ValueError('Recursive image composition is not allowed')
    activity=composition_activity(look,active,branch)
    enabled=any(activity.values())
    selection=modules.get('image_composition',{})
    resolve_composition_files(look.get('composition_files',{}),base_dir,selections=selection,enabled=enabled,active_prefixes={p for p,on in activity.items() if on})
    for name,child in branches.items():
        validate_look_media(child,base_dir,active=activity[name[0].upper()],branch=True)


def resolve_layer_files(values, base_dir, *, selections=None, enabled=True):
    """Whitelist the two passive media paths in a captured layer look."""
    names = ("Backdropfile", "Topfile")
    if not isinstance(values, dict) or set(values) - set(names):
        raise ValueError("Unknown Layer Composite media fields")
    result = {}
    selections = selections or {}
    for name in names:
        selection = selections.get(name.replace("file", "source"), "auto")
        if selection not in {"auto", "file", "effects", "second", "transparent", "effects_a", "effects_b"}:
            raise ValueError("Invalid layer source selection")
        raw = values.get(name, "")
        if not isinstance(raw, str) or len(raw) > 4096 or "://" in raw or "\x00" in raw:
            raise ValueError("Layer media must be local file paths")
        if not raw.strip():
            result[name] = ""
            continue
        path = Path(raw)
        if not path.is_absolute():
            path = Path(base_dir) / path
        if enabled and selection in {"auto", "file"} and not path.is_file():
            raise ValueError("Missing layer media: " + path.name)
        result[name] = str(path.resolve())
    return result


def number(value, label, minimum=0.0, maximum=86400.0):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ValueError(f"{label} must be finite and between {minimum} and {maximum}")
    return result


def validate_look_animation(look, *, branch=False):
    """Optional procedural starting phases; old shows still start at zero."""
    if not isinstance(look, dict):
        raise ValueError("Look must be an object")
    animation = look.get("animation", {})
    if not isinstance(animation, dict) or set(animation) - {*MODULES, "fx_rack"}:
        raise ValueError("Unknown look animation module")
    for name, clock in animation.items():
        if (not isinstance(clock, dict) or not {"time", "running"} <= set(clock)
                or set(clock) - {"time", "running", "render_time", "field_time"}):
            raise ValueError("Look animation needs time and running")
        number(clock["time"], name + " animation time", -1.0e9, 1.0e9)
        if not isinstance(clock["running"], bool):
            raise ValueError("Look animation running must be boolean")
        for phase_name in ("render_time", "field_time"):
            if phase_name not in clock:
                continue
            if name not in {"ink_dream_flow", "ink_brush_flow", "ink_radial_flow"}:
                raise ValueError("Continuous render time is only supported by ink flow modules")
            number(clock[phase_name], name + " " + phase_name, -1.0e12, 1.0e12)
    branches = look.get("branches", {})
    if not isinstance(branches, dict) or set(branches) - {"a_effects", "b_effects"}:
        raise ValueError("Unknown composition branch")
    if branch and branches:
        raise ValueError("Recursive image composition is not allowed")
    for child in branches.values():
        validate_look_animation(child, branch=True)


def animation_time(animation, name, elapsed, scale=1.0):
    """Evaluate a previously validated look clock for playback or export."""
    clock = animation.get(name, {})
    return clock.get("time", 0.0) + (elapsed * scale if clock.get("running", True) else 0.0)


INK_CLOCK_KEY = "imagefx_ink_animation_clock"
INK_FIELD_CLOCK_KEY = "imagefx_ink_field_clock"


def ink_render_time(raw, speed, anchor=None):
    """Read an ink phase without cooking an inactive TouchDesigner module."""
    return raw * speed if anchor is None else anchor['phase'] + (raw - anchor['raw']) * anchor['speed']


def timestamp(value):
    """Parse seconds or HH:MM:SS.mmm; blank means manual GO."""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        pieces = value.strip().split(":")
        if not 1 <= len(pieces) <= 3:
            raise ValueError("Use seconds or HH:MM:SS.mmm")
        try:
            values = [float(piece) for piece in pieces]
        except ValueError as exc:
            raise ValueError("Invalid timestamp") from exc
        if any(not math.isfinite(v) or v < 0 for v in values):
            raise ValueError("Timestamp must be nonnegative and finite")
        if len(values) > 1 and any(v >= 60 for v in values[1:]):
            raise ValueError("Timestamp minutes/seconds must be below 60")
        value = sum(v * 60 ** i for i, v in enumerate(reversed(values)))
    return number(value, "Timestamp")


def new_cue():
    return {
        "id": uuid.uuid4().hex, "name": "New cue", "kind": "visual", "enabled": True,
        "source": "", "track": 1, "at": None, "prewait": 0.0, "duration": 10.0,
        "fade": 1.0, "follow": "manual", "postwait": 0.0, "loop": False,
        "media_in": 0.0, "speed": 1.0, "gain": 0.7, "hold": True, "movie_audio": False,
        "target": "calligraphic_shadow/Particleamount", "value": 1.0,
        "easing": "smooth", "look": {}, "notes": "", "blackout_scope": "all",
    }


def parse_target(value):
    parts=value.split('/')
    allowed=(*MODULES,'fx_rack',*[f'slot{i}' for i in range(1,9)])
    if len(parts)==2 and parts[0] in allowed:
        path='fx_rack/'+parts[0] if parts[0].startswith('slot') else parts[0]
    elif len(parts)==4 and parts[0]=='image_composition' and parts[1] in {'a_effects','b_effects'} and parts[2] in allowed and parts[2]!='image_composition':
        path='/'.join(parts[:2])+('/fx_rack/' if parts[2].startswith('slot') else '/')+parts[2]
    else: raise ValueError('Target must be module/Parameter, slot1..8/Parameter, or image_composition/a_effects|b_effects/module/Parameter')
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9]{0,79}',parts[-1]): raise ValueError('Invalid target parameter')
    return path,parts[-1]


def validate_cue(value):
    if not isinstance(value, dict):
        raise ValueError("Cue must be an object")
    result = new_cue()
    if set(value) - set(result):
        raise ValueError("Unknown cue fields: " + ", ".join(sorted(set(value) - set(result))))
    result.update(copy.deepcopy(value))
    if not isinstance(result["id"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", result["id"]):
        raise ValueError("Invalid cue id")
    for field, limit in (("name", 160), ("source", 4096), ("notes", 4000), ("target", 120)):
        if not isinstance(result[field], str) or len(result[field]) > limit or "\x00" in result[field]:
            raise ValueError(f"Invalid {field}")
    for field, choices in (
        ("kind", {"visual", "audio", "parameters", "stop", "wait", "blackout"}),
        ("blackout_scope", {"all", "track"}),
        ("follow", {"manual", "continue", "follow"}),
        ("easing", {"linear", "smooth"}),
    ):
        if not isinstance(result[field], str) or result[field] not in choices:
            raise ValueError(f"Invalid {field}")
    for field in ("enabled", "loop", "hold", "movie_audio"):
        if not isinstance(result[field], bool):
            raise ValueError(f"{field} must be boolean")
    if type(result["track"]) is not int or result["track"] not in (1, 2, 3):
        raise ValueError("Track must be 1, 2, or 3")
    result["at"] = timestamp(result["at"])
    for field in ("prewait", "duration", "fade", "postwait", "media_in"):
        result[field] = number(result[field], field)
    result["speed"] = number(result["speed"], "Speed", 0.1, 4.0)
    result["gain"] = number(result["gain"], "Gain", 0.0, 1.0)
    if result["follow"] == "follow" and result["duration"] == 0:
        raise ValueError("Auto-follow requires a duration; zero means indefinite")
    if not isinstance(result["look"], dict):
        raise ValueError("Look must be an object")
    validate_look_animation(result["look"])
    parse_target(result["target"])
    if not isinstance(result["value"], (str, int, float, bool)):
        raise ValueError("Target value must be a scalar")
    if isinstance(result["value"], (int, float)) and not isinstance(result["value"], bool):
        number(result["value"], "Target value", -1.0e9, 1.0e9)
    return result


def validate_show(value):
    if not isinstance(value, dict) or value.get("kind") != SHOW_KIND or value.get("schema_version") != 1:
        raise ValueError("Not a supported ImageFX show file")
    if set(value) - {"kind", "schema_version", "cues", "mapping"}:
        raise ValueError("Unknown show fields")
    cues = value.get("cues")
    if not isinstance(cues, list) or len(cues) > MAX_CUES:
        raise ValueError("Show must contain at most 1000 cues")
    result = [validate_cue(cue) for cue in cues]
    if len({cue["id"] for cue in result}) != len(result):
        raise ValueError("Cue ids must be unique")
    mapping = value.get("mapping", {})
    if not isinstance(mapping, dict):
        raise ValueError("Mapping must be an object")
    return {"kind": SHOW_KIND, "schema_version": 1, "cues": result, "mapping": copy.deepcopy(mapping)}


def ease(value, mode="smooth"):
    value = min(1.0, max(0.0, value))
    return value * value * (3.0 - 2.0 * value) if mode == "smooth" else value


def inverse_quad(corners):
    """Map destination BL, BR, TR, TL corners back into the unit source square."""
    if len(corners) != 4:
        raise ValueError("Four mapping corners required")
    points = [(number(x, "Corner X", -1, 2), number(y, "Corner Y", -1, 2)) for x, y in corners]
    crosses = []
    for i in range(4):
        a, b, c = points[i], points[(i + 1) % 4], points[(i + 2) % 4]
        crosses.append((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]))
    if min(crosses) <= 1.0e-5:
        raise ValueError("Mapping corners must form a nondegenerate, uncrossed quad")
    matrix = []
    for (x, y), (u, v) in zip(points, ((0, 0), (1, 0), (1, 1), (0, 1))):
        matrix.append([x, y, 1, 0, 0, 0, -u*x, -u*y, u])
        matrix.append([0, 0, 0, x, y, 1, -v*x, -v*y, v])
    for col in range(8):
        pivot = max(range(col, 8), key=lambda row: abs(matrix[row][col]))
        matrix[col], matrix[pivot] = matrix[pivot], matrix[col]
        scale = matrix[col][col]
        if abs(scale) < 1.0e-10:
            raise ValueError("Degenerate mapping")
        matrix[col] = [v / scale for v in matrix[col]]
        for row in range(8):
            if row != col:
                scale = matrix[row][col]
                matrix[row] = [a - scale*b for a, b in zip(matrix[row], matrix[col])]
    return tuple(matrix[i][8] for i in range(8)) + (1.0,)


class CuePreparationBusy(ValueError):
    """A temporary track/deck reservation, not a broken cue or media file."""


class CueEngine:
    """Pause-aware show clock; backend owns loading, playback, and rendering."""

    def __init__(self, cues, backend, clock=time.monotonic):
        self.cues = validate_show({"kind": SHOW_KIND, "schema_version": 1, "cues": cues})["cues"]
        self.backend = backend
        self.clock = clock
        self.elapsed = 0.0
        self.state = "stopped"
        self.selected = 0
        self.triggered = set()
        self.pending = {}
        self._waiting_preparation = {}
        self.active = {}
        self.follows = []
        self.errors = {}
        self.navigation_index = None
        self._suppress_follows = set()
        self._last = clock()

    def go(self, index=None, *, replay=False, wait_for_resources=False):
        if self.state == "paused":
            raise ValueError("Resume before GO")
        index = self.selected if index is None else index
        if not 0 <= index < len(self.cues):
            return False
        cue = self.cues[index]
        if not cue["enabled"]:
            self.selected = min(index + 1, len(self.cues))
            return False
        # Forward GO after Go Back may revisit a superseded but logically
        # active cue. Give it a fresh standby rather than rejecting the row.
        replay = replay or (cue["id"] in self._suppress_follows and cue["id"] in self.active)
        if not replay and (cue["id"] in self.pending or cue["id"] in self.active):
            raise ValueError("Cue is already pending or running")
        try:
            if replay:
                self.backend.prepare_replay(cue)
            else:
                self.backend.prepare(cue)
        except CuePreparationBusy:
            if not wait_for_resources:
                raise
            # Auto-continue/follow/timestamps are one-shot triggers. Reserve
            # the request as WAIT and retry only this explicit temporary state.
            self._waiting_preparation[cue["id"]] = replay
        else:
            self._waiting_preparation.pop(cue["id"], None)
        if replay:
            self.active.pop(cue["id"], None)
        self.errors.pop(cue["id"], None)
        if self.state == "stopped":
            self.state = "running"
            self._last = self.clock()
        self.triggered.add(cue["id"])
        self.pending[cue["id"]] = (index, self.elapsed + cue["prewait"], self.elapsed)
        self.selected = min(index + 1, len(self.cues))
        self.navigation_index = index
        self._suppress_follows.discard(cue["id"])
        return True

    def go_back(self):
        """Replay the preceding enabled row without stopping the current output.

        This is cue navigation, not a rewind of the show clock or other tracks.
        Pending forward cues and follows are disarmed to avoid bouncing forward.
        """
        if self.state == "paused":
            raise ValueError("Resume before Go Back")
        anchor = self.selected if self.navigation_index is None else self.navigation_index
        index = anchor - 1
        while index >= 0 and not self.cues[index]["enabled"]:
            index -= 1
        if index < 0:
            return False
        for cue_id, (pending_index, _due, _queued) in list(self.pending.items()):
            if pending_index != index:
                self.stop_cue(pending_index)
        self.follows.clear()
        self._suppress_follows.update(self.active)
        return self.go(index, replay=True)

    def pause(self):
        if self.state == "running":
            self.tick()
            self.state = "paused"
            self.backend.pause(True)

    def resume(self):
        if self.state == "paused":
            self._last = self.clock()
            self.state = "running"
            self.backend.pause(False)

    def stop(self):
        self.backend.stop_all()
        self.elapsed = 0.0
        self.state = "stopped"
        self.triggered.clear()
        self.pending.clear()
        self._waiting_preparation.clear()
        self.active.clear()
        self.follows.clear()
        self.errors.clear()
        self.navigation_index = None
        self._suppress_follows.clear()
        self._last = self.clock()

    def stop_cue(self, index):
        if not 0 <= index < len(self.cues):
            return
        cue = self.cues[index]
        # Stop also disarms an as-yet-unfired timestamp/follow for this run.
        self.triggered.add(cue["id"])
        self.backend.stop_cue(cue)
        self.pending.pop(cue["id"], None)
        self._waiting_preparation.pop(cue["id"], None)
        self.active.pop(cue["id"], None)
        self.follows = [entry for entry in self.follows if entry[2] != cue["id"]]

    def tick(self):
        now = self.clock()
        if self.state != "running":
            self._last = now
            return
        self.elapsed += max(0.0, now - self._last)
        self._last = now
        due_follows = [entry for entry in self.follows if entry[0] <= self.elapsed]
        self.follows = [entry for entry in self.follows if entry[0] > self.elapsed]
        for _when, index, _parent in due_follows:
            self._auto_go(index)
        for index, cue in enumerate(self.cues):
            if cue["enabled"] and cue["at"] is not None and cue["at"] <= self.elapsed and cue["id"] not in self.triggered:
                self._auto_go(index)
        for cue_id, (index, due, queued) in list(self.pending.items()):
            if cue_id not in self.pending:
                continue  # A preceding Stop cue cancelled this pending cue.
            cue = self.cues[index]
            try:
                if cue_id in self._waiting_preparation:
                    try:
                        if self._waiting_preparation[cue_id]:
                            self.backend.prepare_replay(cue)
                        else:
                            self.backend.prepare(cue)
                    except CuePreparationBusy:
                        continue
                    self._waiting_preparation.pop(cue_id)
                    # Resource waiting is not media decoding. A legitimate
                    # long crossfade must not consume the 30s readiness timeout.
                    queued = self.elapsed
                    self.pending[cue_id] = (index, due, queued)
                if self.elapsed < due:
                    continue
                if not self.backend.ready(cue):
                    if self.elapsed - max(due, queued) > 30:
                        raise ValueError("Media was not ready within 30 seconds; previous output retained")
                    continue
                if cue["kind"] == "stop":
                    for other_index, other in enumerate(self.cues):
                        if other["id"] != cue_id and other["track"] == cue["track"] and (
                            other["id"] in self.pending or other["id"] in self.active
                            or any(entry[2] == other["id"] for entry in self.follows)
                        ):
                            self.stop_cue(other_index)
                self.backend.start(cue, self.elapsed)
                self.pending.pop(cue_id)
                self.active[cue_id] = (index, self.elapsed)
                if cue["follow"] == "continue" and cue_id not in self._suppress_follows:
                    self.follows.append((self.elapsed + cue["postwait"], index + 1, cue_id))
            except Exception as exc:
                self.errors[cue_id] = str(exc)
                self.pending.pop(cue_id, None)
                self._waiting_preparation.pop(cue_id, None)
                self.backend.stop_cue(cue)
        self.backend.tick(self.elapsed)
        for cue_id, (index, started) in list(self.active.items()):
            cue = self.cues[index]
            if (cue["duration"] > 0 and self.elapsed - started >= cue["duration"]) or (cue["duration"] == 0 and cue["kind"] in {"parameters", "stop"}):
                self.backend.finish(cue)
                self.active.pop(cue_id)
                if cue["follow"] == "follow" and cue_id not in self._suppress_follows:
                    self.follows.append((self.elapsed + cue["postwait"], index + 1, cue_id))

    def _auto_go(self, index):
        # Disabled rows are skipped in an automatic chain, not a dead end.
        while 0 <= index < len(self.cues) and not self.cues[index]["enabled"]:
            index += 1
        if 0 <= index < len(self.cues) and self.cues[index]["id"] not in self.triggered:
            try:
                self.go(index, wait_for_resources=True)
            except Exception as exc:
                cue_id = self.cues[index]["id"]
                self.triggered.add(cue_id)
                self.errors[cue_id] = str(exc)
