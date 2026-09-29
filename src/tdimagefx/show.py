"""Portable cue scheduling and planar mapping math (no TouchDesigner imports)."""

from __future__ import annotations

import copy
import math
import re
import time
import uuid


SHOW_KIND = "tdimagefx.show"
MAX_CUES = 1000
MAX_SHOW_BYTES = 8 * 1024 * 1024
MODULES = (
    "reference_particle_field", "calligraphic_shadow", "ink_orbit_canvas",
    "ink_flow", "particle_random_move", "glitch_fusion", "color_adjustment",
    "motion_studio", "ink_dream_flow",
)
TOGGLES = (
    "Referenceparticlefieldenabled", "Calligraphicshadowenabled", "Inkorbitenabled",
    "Inkflowenabled", "Particlesenabled", "Glitchenabled", "Coloradjustmentenabled",
    "Motionenabled", "Applyvideofx", "Inkdreamenabled",
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
}


def number(value, label, minimum=0.0, maximum=86400.0):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ValueError(f"{label} must be finite and between {minimum} and {maximum}")
    return result


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
        "easing": "smooth", "look": {}, "notes": "",
    }


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
        ("kind", {"visual", "audio", "parameters", "stop", "wait"}),
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
    target = result["target"].split("/")
    if len(target) != 2 or target[0] not in (*MODULES, "fx_rack", *[f"slot{i}" for i in range(1, 9)]):
        raise ValueError("Target must be module/Parameter or slot1..8/Parameter")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,79}", target[1]):
        raise ValueError("Invalid target parameter")
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
        self.active = {}
        self.follows = []
        self.errors = {}
        self._last = clock()

    def go(self, index=None):
        if self.state == "paused":
            raise ValueError("Resume before GO")
        index = self.selected if index is None else index
        if not 0 <= index < len(self.cues):
            return False
        cue = self.cues[index]
        if not cue["enabled"]:
            self.selected = min(index + 1, len(self.cues))
            return False
        if cue["id"] in self.pending or cue["id"] in self.active:
            raise ValueError("Cue is already pending or running")
        self.backend.prepare(cue)
        if self.state == "stopped":
            self.state = "running"
            self._last = self.clock()
        self.triggered.add(cue["id"])
        self.pending[cue["id"]] = (index, self.elapsed + cue["prewait"], self.elapsed)
        self.selected = min(index + 1, len(self.cues))
        return True

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
        self.active.clear()
        self.follows.clear()
        self.errors.clear()
        self._last = self.clock()

    def stop_cue(self, index):
        if not 0 <= index < len(self.cues):
            return
        cue = self.cues[index]
        # Stop also disarms an as-yet-unfired timestamp/follow for this run.
        self.triggered.add(cue["id"])
        self.backend.stop_cue(cue)
        self.pending.pop(cue["id"], None)
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
                if cue["follow"] == "continue":
                    self.follows.append((self.elapsed + cue["postwait"], index + 1, cue_id))
            except Exception as exc:
                self.errors[cue_id] = str(exc)
                self.pending.pop(cue_id, None)
                self.backend.stop_cue(cue)
        self.backend.tick(self.elapsed)
        for cue_id, (index, started) in list(self.active.items()):
            cue = self.cues[index]
            if (cue["duration"] > 0 and self.elapsed - started >= cue["duration"]) or (cue["duration"] == 0 and cue["kind"] in {"parameters", "stop"}):
                self.backend.finish(cue)
                self.active.pop(cue_id)
                if cue["follow"] == "follow":
                    self.follows.append((self.elapsed + cue["postwait"], index + 1, cue_id))

    def _auto_go(self, index):
        # Disabled rows are skipped in an automatic chain, not a dead end.
        while 0 <= index < len(self.cues) and not self.cues[index]["enabled"]:
            index += 1
        if 0 <= index < len(self.cues) and self.cues[index]["id"] not in self.triggered:
            try:
                self.go(index)
            except Exception as exc:
                cue_id = self.cues[index]["id"]
                self.triggered.add(cue_id)
                self.errors[cue_id] = str(exc)
