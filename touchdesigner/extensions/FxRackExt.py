"""TouchDesigner extension for the eight-slot ImageFX rack."""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
from pathlib import Path


SLOT_COUNT = 8
PRESET_SCHEMA_VERSION = 1
PRESET_KIND = "tdimagefx.rack-preset"
MAX_PRESET_BYTES = 256 * 1024
MAX_MANIFEST_BYTES = 256 * 1024
MAX_MODULATION_RATE = 60.0
PACKAGE_ID_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
VERSION_RE = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
PARAMETER_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,79}$")
MODULATION_STATES = ("off", "sine", "triangle", "saw")
RACK_AUXILIARY_INPUTS = (
    "image_b",
    "displacement",
    "depth",
    "normal",
    "flow",
    "mask",
)
_AUXILIARY_ROLE_ALIASES = {
    "image_b": "image_b",
    "second_image": "image_b",
    "second_input": "image_b",
    "auxiliary_image": "image_b",
    "transition_image": "image_b",
    "transition": "image_b",
    "displacement": "displacement",
    "displacement_map": "displacement",
    "depth": "depth",
    "depth_map": "depth",
    "normal": "normal",
    "normal_map": "normal",
    "normals": "normal",
    "flow": "flow",
    "optical_flow": "flow",
    "motion": "flow",
    "motion_vectors": "flow",
    "mask": "mask",
    "matte": "mask",
}
SYSTEM_PARAMETER_NAMES = {
    "Enable",
    "Mix",
    "Time",
    "Timescale",
    "Packageid",
    "Packageversion",
    "Fxapi",
    "Processingmodel",
    "Historyframes",
    "Gpucost",
    "Capabilities",
    "Status",
    "Reset",
}


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key: {}".format(key))
        result[key] = value
    return result


def _repair_effect_shader_paths(root_comp):
    """Repair legacy absolute GLSL Pixel Shader paths in a loaded package."""

    repaired = 0
    pending = list(getattr(root_comp, "children", ()) or ())
    while pending:
        operator = pending.pop()
        pending.extend(list(getattr(operator, "children", ()) or ()))
        name = str(getattr(operator, "name", ""))
        if str(getattr(operator, "type", "")) != "glsl" or not name.startswith(
            "effect_glsl_"
        ):
            continue
        shader_name = "pixel_shader_" + name[len("effect_glsl_"):]
        shader_dat = operator.parent().op(shader_name)
        parameter = operator.par["pixeldat"]
        if shader_dat is None or parameter is None:
            raise RuntimeError(
                "{} is missing its portable Pixel Shader DAT".format(operator.path)
            )
        parameter.val = operator.relativePath(shader_dat)
        if parameter.eval() != shader_dat:
            raise RuntimeError(
                "{} Pixel Shader reference did not resolve".format(operator.path)
            )
        repaired += 1
    return repaired


def _repair_effect_callback_paths(root_comp):
    """Repair legacy absolute reset callback targets in a loaded package."""

    repaired = 0
    pending = list(getattr(root_comp, "children", ()) or ())
    while pending:
        operator = pending.pop()
        pending.extend(list(getattr(operator, "children", ()) or ()))
        if str(getattr(operator, "name", "")) != "reset_callbacks":
            continue
        parameter = operator.par["op"]
        target = operator.parent()
        if parameter is None or target is None:
            raise RuntimeError(
                "{} is missing its portable reset callback target".format(operator.path)
            )
        parameter.val = operator.relativePath(target)
        if parameter.eval() != target:
            raise RuntimeError(
                "{} reset callback target did not resolve".format(operator.path)
            )
        repaired += 1
    return repaired


class FxRackExt:
    SLOT_COUNT = SLOT_COUNT

    def __init__(self, ownerComp):
        self.ownerComp = ownerComp
        self._callback_depth = 0

    @property
    def CallbacksSuspended(self):
        """Whether a bulk operation is changing parameters programmatically."""
        return self._callback_depth > 0

    @staticmethod
    def _slot_index(index):
        if isinstance(index, bool):
            raise ValueError("Slot index must be an integer between 1 and {}".format(SLOT_COUNT))
        try:
            numeric = float(index)
        except (TypeError, ValueError) as exc:
            raise ValueError("Slot index must be an integer between 1 and {}".format(SLOT_COUNT)) from exc
        if not math.isfinite(numeric) or not numeric.is_integer():
            raise ValueError("Slot index must be an integer between 1 and {}".format(SLOT_COUNT))
        result = int(numeric)
        if result < 1 or result > SLOT_COUNT:
            raise ValueError("Slot index must be between 1 and {}".format(SLOT_COUNT))
        return result

    @staticmethod
    def _finite_float(value, label, minimum=None, maximum=None):
        if isinstance(value, bool):
            raise ValueError("{} must be a finite number".format(label))
        try:
            result = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("{} must be a finite number".format(label)) from exc
        if not math.isfinite(result):
            raise ValueError("{} must be a finite number".format(label))
        if minimum is not None and result < minimum:
            raise ValueError("{} must be at least {}".format(label, minimum))
        if maximum is not None and result > maximum:
            raise ValueError("{} must be at most {}".format(label, maximum))
        return result

    @staticmethod
    def _boolean(value, label="Value"):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)) and value in (0, 1):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in ("1", "true", "yes", "on", "enabled"):
                return True
            if normalized in ("0", "false", "no", "off", "disabled"):
                return False
        raise ValueError("{} must be a boolean".format(label))

    @staticmethod
    def _modulation_state(value):
        if isinstance(value, bool):
            return "sine" if value else "off"
        if isinstance(value, (int, float)) and value in (0, 1):
            return "sine" if value else "off"
        if isinstance(value, str):
            normalized = value.strip().lower()
            aliases = {
                "none": "off",
                "disabled": "off",
                "on": "sine",
                "enabled": "sine",
                "tri": "triangle",
                "ramp": "saw",
                "sawtooth": "saw",
            }
            normalized = aliases.get(normalized, normalized)
            if normalized in MODULATION_STATES:
                return normalized
        raise ValueError("Modulation state must be one of: {}".format(", ".join(MODULATION_STATES)))

    @staticmethod
    def _package(package):
        if package is None:
            return None
        if not isinstance(package, dict):
            raise ValueError("Slot package must be an object or null")
        unknown = set(package) - {"id", "version"}
        if unknown:
            raise ValueError("Unknown slot package fields: {}".format(", ".join(sorted(unknown))))
        package_id = package.get("id")
        version = package.get("version")
        if not isinstance(package_id, str) or not PACKAGE_ID_RE.fullmatch(package_id):
            raise ValueError("Invalid package id")
        if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
            raise ValueError("Invalid package version")
        return {"id": package_id, "version": version}

    @staticmethod
    def _normalized_input_role(value):
        return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")

    @classmethod
    def _input_role(cls, input_definition, input_index):
        if input_index == 0:
            return "image"
        if not isinstance(input_definition, dict):
            raise RuntimeError("Effect input definitions must be objects")
        for candidate in (
            input_definition.get("role"),
            input_definition.get("semantic"),
            input_definition.get("id"),
        ):
            role = _AUXILIARY_ROLE_ALIASES.get(cls._normalized_input_role(candidate))
            if role is not None:
                return role
        raise RuntimeError(
            "Unsupported auxiliary TOP input {!r}; use one of: {}".format(
                input_definition.get("semantic") or input_definition.get("id"),
                ", ".join(RACK_AUXILIARY_INPUTS),
            )
        )

    @classmethod
    def _input_routes(cls, manifest):
        inputs = manifest.get("inputs") if isinstance(manifest, dict) else None
        if not isinstance(inputs, list) or not inputs:
            raise RuntimeError("Package must declare at least one TOP input")
        routes = {0: "image"}
        for input_index, input_definition in enumerate(inputs[1:], start=1):
            routes[input_index] = cls._input_role(input_definition, input_index)
        return routes

    @staticmethod
    def _rack_input_name(role):
        roles = ("image", *RACK_AUXILIARY_INPUTS)
        try:
            index = roles.index(role) + 1
        except ValueError as exc:
            raise RuntimeError("Unknown rack input role: {}".format(role)) from exc
        return "in{}_{}".format(index, role)

    def _parameter(self, name):
        try:
            return self.ownerComp.par[name]
        except (AttributeError, KeyError, TypeError):
            return None

    @staticmethod
    def _eval(parameter, default=None):
        if parameter is None:
            return default
        try:
            evaluator = getattr(parameter, "eval", None)
            return evaluator() if callable(evaluator) else parameter
        except Exception:
            return default

    def _parameter_value(self, name, default=None):
        return self._eval(self._parameter(name), default)

    def _parameter_boolean(self, name, default):
        try:
            return self._boolean(self._parameter_value(name, default), name)
        except ValueError:
            return bool(default)

    def _set_parameter(self, name, value):
        parameter = self._parameter(name)
        if parameter is None:
            return False
        try:
            parameter.val = value
        except Exception:
            try:
                setattr(self.ownerComp.par, name, value)
            except Exception:
                return False
        return True

    @staticmethod
    def _component_parameter(component, name):
        if component is None:
            return None
        try:
            return component.par[name]
        except (AttributeError, KeyError, TypeError):
            return None

    @classmethod
    def _set_component_parameter(cls, component, name, value):
        parameter = cls._component_parameter(component, name)
        if parameter is None:
            return False
        try:
            parameter.val = value
        except Exception:
            return False
        return True

    def _root(self) -> Path:
        value = str(self._parameter_value("Rootfolder", "") or "").strip()
        if value:
            return Path(value).expanduser().resolve()
        project_object = globals().get("project")
        project_folder = getattr(project_object, "folder", None)
        return Path(project_folder or Path.cwd()).resolve()

    @staticmethod
    def _version_key(version):
        core = version.split("+", 1)[0]
        release, separator, prerelease = core.partition("-")
        release_key = tuple(int(part) for part in release.split("."))
        if not separator:
            return release_key, 1, ()
        prerelease_key = tuple(
            (0, int(part)) if part.isdigit() else (1, part.lower())
            for part in prerelease.split(".")
        )
        return release_key, 0, prerelease_key

    def _find_manifest(self, package_id, version=None):
        if not isinstance(package_id, str) or not PACKAGE_ID_RE.fullmatch(package_id):
            raise ValueError("Invalid package id")
        if version is not None and (not isinstance(version, str) or not VERSION_RE.fullmatch(version)):
            raise ValueError("Invalid package version")

        package_root = (self._root() / "packages" / package_id).resolve()
        matches = []
        for path in package_root.glob("*/package.json"):
            try:
                resolved_path = path.resolve()
                resolved_path.relative_to(package_root)
                if resolved_path.stat().st_size > MAX_MANIFEST_BYTES:
                    continue
                manifest = json.loads(
                    resolved_path.read_text(encoding="utf-8"),
                    object_pairs_hook=_reject_duplicate_keys,
                )
            except (OSError, ValueError, TypeError):
                continue
            manifest_version = manifest.get("version")
            if manifest.get("id") != package_id or not isinstance(manifest_version, str):
                continue
            if not VERSION_RE.fullmatch(manifest_version):
                continue
            if version is None or manifest_version == version:
                matches.append((manifest, resolved_path))
        if not matches:
            raise KeyError("Package is not installed: {} {}".format(package_id, version or ""))
        matches.sort(key=lambda pair: self._version_key(pair[0]["version"]), reverse=True)
        return matches[0]

    @staticmethod
    def _component_path(manifest, manifest_path):
        relative = manifest.get("entrypoints", {}).get("touchdesigner_component")
        if not isinstance(relative, str) or not relative:
            raise RuntimeError("Package has no TouchDesigner component")
        package_root = manifest_path.parent.resolve()
        tox_path = (package_root / relative).resolve()
        try:
            tox_path.relative_to(package_root)
        except ValueError as exc:
            raise RuntimeError("TouchDesigner component escapes its package") from exc
        if not tox_path.is_file():
            raise FileNotFoundError(str(tox_path))
        return tox_path

    def _slot_source(self, index):
        for previous_index in range(index - 1, 0, -1):
            source = self.ownerComp.op("slot{}".format(previous_index))
            if source is not None:
                return source
        return self.ownerComp.op("in1_image")

    def _next_slot_target(self, index):
        for next_index in range(index + 1, SLOT_COUNT + 1):
            target = self.ownerComp.op("slot{}".format(next_index))
            if target is not None:
                return target
        return self.ownerComp.op("out1_image")

    @staticmethod
    def _connect(source_connector, target_connector):
        if source_connector is None or target_connector is None:
            raise RuntimeError("Rack connector is unavailable")
        try:
            target_connector.disconnect()
        except Exception:
            pass
        source_connector.connect(target_connector)

    def _connect_slot(self, index, slot, routes, store_routes=True):
        source = self._slot_source(index)
        if source is None:
            raise RuntimeError("Rack input is unavailable")
        self._connect(source.outputConnectors[0], slot.inputConnectors[0])
        for input_index in range(1, len(slot.inputConnectors)):
            role = routes.get(input_index)
            if role is None:
                raise RuntimeError("Loaded component exposes an undeclared input at index {}".format(input_index))
            rack_input = self.ownerComp.op(self._rack_input_name(role))
            if rack_input is None:
                raise RuntimeError("Rack {} input is unavailable".format(role))
            self._connect(rack_input.outputConnectors[0], slot.inputConnectors[input_index])
        next_target = self._next_slot_target(index)
        if next_target is not None:
            self._connect(slot.outputConnectors[0], next_target.inputConnectors[0])
        if store_routes:
            self.ownerComp.store(
                "slot{}_input_routes".format(index),
                {str(input_index): role for input_index, role in sorted(routes.items())},
            )

    def _bind_slot(self, index, slot):
        enable_parameter = self._component_parameter(slot, "Enable")
        mix_parameter = self._component_parameter(slot, "Mix")
        time_parameter = self._component_parameter(slot, "Time")
        if enable_parameter is not None:
            enable_parameter.expr = "parent().par.Slot{}enable".format(index)
        if mix_parameter is not None:
            mix_parameter.expr = "parent().ModulatedMix({})".format(index)
        if time_parameter is not None:
            time_parameter.expr = "parent().par.Time"

    def _unique_operator_name(self, base_name):
        candidate = base_name
        suffix = 2
        while self.ownerComp.op(candidate) is not None:
            candidate = "{}_{}".format(base_name, suffix)
            suffix += 1
        return candidate

    @staticmethod
    def _rename_exact(operator, name):
        operator.name = name
        if str(getattr(operator, "name", "")) != name:
            raise RuntimeError("Unable to reserve rack operator name {}".format(name))

    def _connect_without_slot(self, index):
        source = self._slot_source(index)
        target = self._next_slot_target(index)
        if source is None:
            raise RuntimeError("Rack input is unavailable")
        if target is not None:
            self._connect(source.outputConnectors[0], target.inputConnectors[0])

    def _restore_failed_load(self, index, candidate, old_slot, old_routes):
        try:
            candidate.destroy()
        except Exception:
            pass
        if old_slot is None:
            self._connect_without_slot(index)
            return
        self._rename_exact(old_slot, "slot{}".format(index))
        self._connect_slot(index, old_slot, old_routes, store_routes=False)

    def LoadSlot(self, index, package_id=None, version=None):
        """Transactionally replace one rack slot with an immutable package."""
        index = self._slot_index(index)
        menu_parameter = self._parameter("Slot{}effect".format(index))
        package_id = package_id or self._eval(menu_parameter, None)
        manifest, manifest_path = self._find_manifest(package_id, version)
        tox_path = self._component_path(manifest, manifest_path)
        routes = self._input_routes(manifest)
        for role in set(routes.values()) - {"image"}:
            if self.ownerComp.op(self._rack_input_name(role)) is None:
                raise RuntimeError("Rack {} input is unavailable".format(role))

        old_slot = self.ownerComp.op("slot{}".format(index))
        before_ids = {child.id for child in self.ownerComp.children}
        self.ownerComp.loadTox(str(tox_path))
        created = [child for child in self.ownerComp.children if child.id not in before_ids]
        if len(created) != 1:
            for child in created:
                try:
                    child.destroy()
                except Exception:
                    pass
            raise RuntimeError("Expected one top-level component in {}".format(tox_path))
        slot = created[0]
        if len(slot.inputConnectors) != len(routes):
            try:
                slot.destroy()
            except Exception:
                pass
            raise RuntimeError(
                "Package declares {} inputs but its component exposes {}".format(
                    len(routes), len(slot.inputConnectors)
                )
            )
        if not getattr(slot, "outputConnectors", None):
            try:
                slot.destroy()
            except Exception:
                pass
            raise RuntimeError("Loaded component exposes no TOP output")

        old_routes = self.SlotInputRoutes(index) if old_slot is not None else {"0": "image"}
        try:
            # Bind and wire the candidate while the prior slot is still alive.
            # Nothing persistent changes until the candidate has passed every
            # connector and parameter-binding operation.
            _repair_effect_shader_paths(slot)
            _repair_effect_callback_paths(slot)
            self._bind_slot(index, slot)
            self._connect_slot(index, slot, routes, store_routes=False)
            if old_slot is not None:
                backup_name = self._unique_operator_name(
                    "tdimagefx_slot{}_backup".format(index)
                )
                self._rename_exact(old_slot, backup_name)
            self._rename_exact(slot, "slot{}".format(index))
            if old_slot is not None:
                old_slot.destroy()
        except Exception:
            self._restore_failed_load(index, slot, old_slot, old_routes)
            raise

        package = {"id": package_id, "version": manifest["version"]}
        self.ownerComp.store("slot{}_package".format(index), package)
        self.ownerComp.store(
            "slot{}_input_routes".format(index),
            {str(input_index): role for input_index, role in sorted(routes.items())},
        )
        return slot

    def ClearSlot(self, index):
        """Remove one effect and reconnect the surrounding rack chain."""
        index = self._slot_index(index)
        slot = self.ownerComp.op("slot{}".format(index))
        if slot is not None:
            target = self._next_slot_target(index)
            try:
                self._connect_without_slot(index)
            except Exception:
                if target is not None:
                    try:
                        self._connect(slot.outputConnectors[0], target.inputConnectors[0])
                    except Exception:
                        pass
                raise
            slot.destroy()
        self.ownerComp.store("slot{}_package".format(index), None)
        self.ownerComp.store("slot{}_input_routes".format(index), {"0": "image"})
        return slot is not None

    def ReloadAll(self):
        loaded = []
        for index in range(1, SLOT_COUNT + 1):
            package = self.SlotState(index)["package"]
            if package is not None:
                loaded.append(self.LoadSlot(index, package["id"], package["version"]))
        return loaded

    def ResetSlot(self, index):
        index = self._slot_index(index)
        slot = self.ownerComp.op("slot{}".format(index))
        reset_parameter = self._component_parameter(slot, "Reset")
        if reset_parameter is not None:
            try:
                reset_parameter.pulse()
            except Exception:
                previous_value = self._eval(reset_parameter, False)
                reset_parameter.val = True
                runner = globals().get("run")
                if callable(runner):
                    runner(
                        "args[0].val = args[1]",
                        reset_parameter,
                        previous_value,
                        delayFrames=1,
                    )
                else:
                    reset_parameter.val = previous_value
            return True

        # Compatibility fallback for stateful components built before the
        # adapter began guaranteeing a public Reset pulse.
        try:
            history_nodes = slot.fetch("tdimagefx_history_nodes", []) if slot is not None else []
        except Exception:
            history_nodes = []
        reset_any = False
        for operator_name in history_nodes if isinstance(history_nodes, (list, tuple)) else ():
            try:
                history_operator = slot.op(operator_name)
            except Exception:
                history_operator = None
            reset_pulse = self._component_parameter(history_operator, "resetpulse")
            if reset_pulse is not None:
                reset_pulse.pulse()
                reset_any = True
        return reset_any

    def SlotInputRoutes(self, index):
        """Return the semantic rack bus selected for each slot input."""
        index = self._slot_index(index)
        routes = self.ownerComp.fetch("slot{}_input_routes".format(index), {"0": "image"})
        if not isinstance(routes, dict):
            return {"0": "image"}
        allowed = {"image", *RACK_AUXILIARY_INPUTS}
        result = {}
        for input_index, role in routes.items():
            if str(input_index).isdigit() and role in allowed:
                result[str(input_index)] = role
        return result or {"0": "image"}

    def Reset(self):
        for index in range(1, SLOT_COUNT + 1):
            self.ResetSlot(index)

    def BypassSlot(self, index, bypass=True):
        index = self._slot_index(index)
        should_bypass = self._boolean(bypass, "Bypass")
        self._set_parameter("Slot{}enable".format(index), not should_bypass)
        return not should_bypass

    def ToggleBypass(self, index):
        index = self._slot_index(index)
        enabled = self._boolean(self._parameter_value("Slot{}enable".format(index), True), "Slot enable")
        return self.BypassSlot(index, enabled)

    def BypassAll(self, bypass=True):
        should_bypass = self._boolean(bypass, "Bypass")
        for index in range(1, SLOT_COUNT + 1):
            self.BypassSlot(index, should_bypass)
        return not should_bypass

    def Bypass(self, index=None, bypass=True):
        """Bypass one slot, or all slots when no index is supplied."""
        if index is None:
            return self.BypassAll(bypass)
        return self.BypassSlot(index, bypass)

    def SetModulation(self, index, depth=None, rate=None, state=None, update_parameters=True):
        index = self._slot_index(index)
        current = self.ModulationState(index)
        normalized = {
            "depth": current["depth"] if depth is None else self._finite_float(depth, "Modulation depth", -1.0, 1.0),
            "rate": current["rate"] if rate is None else self._finite_float(rate, "Modulation rate", 0.0, MAX_MODULATION_RATE),
            "state": current["state"] if state is None else self._modulation_state(state),
        }
        self.ownerComp.store("slot{}_modulation".format(index), normalized.copy())
        if update_parameters:
            self._set_parameter("Slot{}moddepth".format(index), normalized["depth"])
            self._set_parameter("Slot{}modrate".format(index), normalized["rate"])
            self._set_parameter("Slot{}modstate".format(index), normalized["state"])
        return normalized

    def ModulationState(self, index):
        index = self._slot_index(index)
        stored = self.ownerComp.fetch(
            "slot{}_modulation".format(index),
            {"depth": 0.0, "rate": 1.0, "state": "off"},
        )
        if not isinstance(stored, dict):
            stored = {"depth": 0.0, "rate": 1.0, "state": "off"}
        depth_value = self._parameter_value("Slot{}moddepth".format(index), stored.get("depth", 0.0))
        rate_value = self._parameter_value("Slot{}modrate".format(index), stored.get("rate", 1.0))
        state_value = self._parameter_value("Slot{}modstate".format(index), stored.get("state", "off"))
        return {
            "depth": self._finite_float(depth_value, "Modulation depth", -1.0, 1.0),
            "rate": self._finite_float(rate_value, "Modulation rate", 0.0, MAX_MODULATION_RATE),
            "state": self._modulation_state(state_value),
        }

    def ModulatedMix(self, index, time_value=None):
        """Return the bounded mix value evaluated for a slot's modulation state."""
        try:
            index = self._slot_index(index)
            base_mix = self._finite_float(
                self._parameter_value("Slot{}mix".format(index), 1.0),
                "Slot mix",
                0.0,
                1.0,
            )
            modulation = self.ModulationState(index)
            if modulation["state"] == "off" or modulation["depth"] == 0.0:
                return base_mix
            time_value = self._finite_float(
                self._parameter_value("Time", 0.0) if time_value is None else time_value,
                "Time",
            )
            cycle = time_value * modulation["rate"]
            if modulation["state"] == "sine":
                wave = math.sin(cycle * math.tau)
            elif modulation["state"] == "triangle":
                wave = 1.0 - 4.0 * abs((cycle % 1.0) - 0.5)
            else:
                wave = 2.0 * (cycle % 1.0) - 1.0
            return max(0.0, min(1.0, base_mix + wave * modulation["depth"]))
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _preset_parameter_value(cls, value):
        if value is None or isinstance(value, (bool, int, str)):
            if isinstance(value, str) and len(value) > 1024:
                raise ValueError("Preset parameter string is too long")
            return value
        if isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError("Preset parameter values must be finite")
            return value
        if isinstance(value, (list, tuple)) and len(value) <= 16:
            return [cls._preset_parameter_value(item) for item in value]
        raise ValueError("Preset parameter values must be JSON scalars or short arrays")

    def _effect_parameters(self, slot):
        result = {}
        for parameter in getattr(slot, "customPars", ()) if slot is not None else ():
            name = getattr(parameter, "name", "")
            if name in SYSTEM_PARAMETER_NAMES or not PARAMETER_NAME_RE.fullmatch(name):
                continue
            value = self._eval(parameter, None)
            try:
                result[name] = self._preset_parameter_value(value)
            except ValueError:
                continue
        return result

    def SlotState(self, index):
        index = self._slot_index(index)
        package = self.ownerComp.fetch("slot{}_package".format(index), None)
        try:
            package = self._package(package)
        except ValueError:
            package = None
        try:
            enabled = self._boolean(self._parameter_value("Slot{}enable".format(index), True), "Slot enable")
        except ValueError:
            enabled = True
        try:
            mix_value = self._finite_float(
                self._parameter_value("Slot{}mix".format(index), 1.0), "Slot mix", 0.0, 1.0
            )
        except ValueError:
            mix_value = 1.0
        try:
            modulation = self.ModulationState(index)
        except ValueError:
            modulation = {"depth": 0.0, "rate": 1.0, "state": "off"}
        slot = self.ownerComp.op("slot{}".format(index))
        return {
            "index": index,
            "package": package,
            "enabled": enabled,
            "mix": mix_value,
            "modulation": modulation,
            "parameters": self._effect_parameters(slot),
        }

    @classmethod
    def _validate_slot_state(cls, state):
        if not isinstance(state, dict):
            raise ValueError("Preset slots must be objects")
        unknown = set(state) - {"index", "package", "enabled", "mix", "modulation", "parameters"}
        if unknown:
            raise ValueError("Unknown slot fields: {}".format(", ".join(sorted(unknown))))
        index = cls._slot_index(state.get("index"))
        package = cls._package(state.get("package"))
        enabled = cls._boolean(state.get("enabled", True), "Slot enable")
        mix_value = cls._finite_float(state.get("mix", 1.0), "Slot mix", 0.0, 1.0)
        modulation = state.get("modulation", {})
        if not isinstance(modulation, dict):
            raise ValueError("Slot modulation must be an object")
        unknown_modulation = set(modulation) - {"depth", "rate", "state"}
        if unknown_modulation:
            raise ValueError(
                "Unknown modulation fields: {}".format(", ".join(sorted(unknown_modulation)))
            )
        normalized_modulation = {
            "depth": cls._finite_float(modulation.get("depth", 0.0), "Modulation depth", -1.0, 1.0),
            "rate": cls._finite_float(modulation.get("rate", 1.0), "Modulation rate", 0.0, MAX_MODULATION_RATE),
            "state": cls._modulation_state(modulation.get("state", "off")),
        }
        parameters = state.get("parameters", {})
        if not isinstance(parameters, dict) or len(parameters) > 256:
            raise ValueError("Slot parameters must be an object with at most 256 entries")
        normalized_parameters = {}
        for name, value in parameters.items():
            if not isinstance(name, str) or not PARAMETER_NAME_RE.fullmatch(name):
                raise ValueError("Invalid effect parameter name")
            if name in SYSTEM_PARAMETER_NAMES:
                continue
            normalized_parameters[name] = cls._preset_parameter_value(value)
        return {
            "index": index,
            "package": package,
            "enabled": enabled,
            "mix": mix_value,
            "modulation": normalized_modulation,
            "parameters": normalized_parameters,
        }

    @classmethod
    def ValidatePreset(cls, preset):
        if not isinstance(preset, dict):
            raise ValueError("Preset must be a JSON object")
        unknown = set(preset) - {
            "schema_version",
            "kind",
            "name",
            "autotime",
            "timescale",
            "time",
            "slots",
        }
        if unknown:
            raise ValueError("Unknown preset fields: {}".format(", ".join(sorted(unknown))))
        if preset.get("schema_version") != PRESET_SCHEMA_VERSION:
            raise ValueError("Unsupported rack preset schema version")
        if preset.get("kind") != PRESET_KIND:
            raise ValueError("Invalid rack preset kind")
        raw_slots = preset.get("slots")
        if not isinstance(raw_slots, list) or not 1 <= len(raw_slots) <= SLOT_COUNT:
            raise ValueError("Preset must contain between 1 and {} slots".format(SLOT_COUNT))
        slots = [cls._validate_slot_state(state) for state in raw_slots]
        indexes = [state["index"] for state in slots]
        if len(set(indexes)) != len(indexes):
            raise ValueError("Preset contains duplicate slot indexes")
        return {
            "schema_version": PRESET_SCHEMA_VERSION,
            "kind": PRESET_KIND,
            "name": str(preset.get("name", ""))[:120],
            "autotime": cls._boolean(preset.get("autotime", True), "Auto time"),
            "timescale": cls._finite_float(preset.get("timescale", 1.0), "Time scale", -100.0, 100.0),
            "time": cls._finite_float(preset.get("time", 0.0), "Time"),
            "slots": slots,
        }

    @staticmethod
    def _complete_preset_slots(slots):
        provided = {state["index"]: state for state in slots}
        return [
            provided.get(index, {
                "index": index,
                "package": None,
                "enabled": False,
                "mix": 1.0,
                "modulation": {"depth": 0.0, "rate": 1.0, "state": "off"},
                "parameters": {},
            })
            for index in range(1, SLOT_COUNT + 1)
        ]

    def PresetData(self, name=""):
        manual_time_parameter = self._parameter("Manualtime")
        manual_time = self._eval(
            manual_time_parameter,
            self._parameter_value("Time", 0.0),
        )
        return {
            "schema_version": PRESET_SCHEMA_VERSION,
            "kind": PRESET_KIND,
            "name": str(name or "")[:120],
            "autotime": self._parameter_boolean("Autotime", True),
            "timescale": self._finite_float(self._parameter_value("Timescale", 1.0), "Time scale"),
            "time": self._finite_float(manual_time, "Manual time"),
            "slots": [self.SlotState(index) for index in range(1, SLOT_COUNT + 1)],
        }

    def ExportPreset(self, name="", indent=2):
        indent_value = int(indent)
        if indent_value < 0 or indent_value > 8:
            raise ValueError("Preset indentation must be between 0 and 8")
        text = json.dumps(
            self.PresetData(name),
            indent=indent_value if indent_value else None,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        if len(text.encode("utf-8")) > MAX_PRESET_BYTES:
            raise ValueError("Rack preset exceeds 256 KiB")
        return text + "\n"

    @staticmethod
    def _parse_preset(payload):
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, bytes):
            if len(payload) > MAX_PRESET_BYTES:
                raise ValueError("Rack preset exceeds 256 KiB")
            payload = payload.decode("utf-8")
        if not isinstance(payload, str):
            raise ValueError("Preset must be JSON text or an object")
        if len(payload.encode("utf-8")) > MAX_PRESET_BYTES:
            raise ValueError("Rack preset exceeds 256 KiB")
        try:
            return json.loads(payload, object_pairs_hook=_reject_duplicate_keys)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("Invalid rack preset JSON") from exc

    def _apply_slot_state(self, state):
        index = state["index"]
        package = state["package"]
        slot = self.ownerComp.op("slot{}".format(index))
        if package is not None:
            slot = self.LoadSlot(index, package["id"], package["version"])
            self._set_parameter("Slot{}effect".format(index), package["id"])
        else:
            self.ClearSlot(index)
            slot = None
        self._set_parameter("Slot{}enable".format(index), state["enabled"])
        self._set_parameter("Slot{}mix".format(index), state["mix"])
        self.SetModulation(index, **state["modulation"])
        for name, value in state["parameters"].items():
            self._set_component_parameter(slot, name, value)
        return slot

    def _apply_states_with_rollback(self, states):
        indexes = [state["index"] for state in states]
        snapshot = [self.SlotState(index) for index in indexes]
        self._callback_depth += 1
        try:
            for state in states:
                self._apply_slot_state(state)
        except Exception:
            for original in snapshot:
                try:
                    self._apply_slot_state(original)
                except Exception:
                    pass
            raise
        finally:
            self._callback_depth -= 1

    def ImportPreset(self, payload):
        preset = self.ValidatePreset(self._parse_preset(payload))
        # Presets are complete rack snapshots. A compact preset may omit empty
        # trailing or intermediate slots; omission means an explicitly empty,
        # bypassed slot rather than "leave whatever happened to be loaded".
        states = self._complete_preset_slots(preset["slots"])
        self._apply_states_with_rollback(states)
        self._callback_depth += 1
        try:
            self._set_parameter("Autotime", preset["autotime"])
            self._set_parameter("Timescale", preset["timescale"])
            if not self._set_parameter("Manualtime", preset["time"]):
                self._set_parameter("Time", preset["time"])
        finally:
            self._callback_depth -= 1
        return self.State()

    def _preset_path(self, path):
        text = str(path or "").strip()
        if not text or "\x00" in text or len(text) > 1024:
            raise ValueError("Preset path is invalid")
        preset_root = (self._root() / "presets").resolve()
        candidate = Path(text).expanduser()
        if not candidate.is_absolute():
            candidate = preset_root / candidate
        if not candidate.suffix:
            candidate = candidate.with_suffix(".json")
        if candidate.suffix.lower() != ".json":
            raise ValueError("Rack presets must use the .json extension")
        candidate = Path(os.path.abspath(candidate))
        # Inspect the unresolved spelling first so a symlink cannot disappear
        # during canonicalization. Canonicalizing afterward makes equivalent
        # filesystem aliases compare consistently on macOS and Windows.
        cursor = candidate
        while True:
            if cursor.is_symlink():
                raise ValueError("Rack preset paths may not contain symbolic links")
            try:
                if cursor.exists() and cursor.samefile(preset_root):
                    break
            except OSError:
                pass
            parent = cursor.parent
            if parent == cursor:
                break
            cursor = parent
        candidate = candidate.resolve(strict=False)
        try:
            relative = candidate.relative_to(preset_root)
        except ValueError as exc:
            raise ValueError("Preset path must stay inside the library presets folder") from exc
        cursor = preset_root
        for part in relative.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise ValueError("Rack preset paths may not contain symbolic links")
        try:
            candidate.resolve().relative_to(preset_root)
        except ValueError as exc:
            raise ValueError("Preset path must stay inside the library presets folder") from exc
        return candidate

    def SavePreset(self, path, name=""):
        destination = self._preset_path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".{}-".format(destination.name),
            suffix=".tmp",
            dir=str(destination.parent),
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                descriptor = None
                handle.write(self.ExportPreset(name or destination.stem))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(str(temporary), str(destination))
        finally:
            if descriptor is not None:
                os.close(descriptor)
            temporary.unlink(missing_ok=True)
        return str(destination)

    def LoadPreset(self, path):
        source = self._preset_path(path)
        size = source.stat().st_size
        if size > MAX_PRESET_BYTES:
            raise ValueError("Rack preset exceeds 256 KiB")
        return self.ImportPreset(source.read_bytes())

    def MoveSlot(self, source_index, destination_index):
        source_index = self._slot_index(source_index)
        destination_index = self._slot_index(destination_index)
        if source_index == destination_index:
            return False
        states = [self.SlotState(index) for index in range(1, SLOT_COUNT + 1)]
        moved = states.pop(source_index - 1)
        states.insert(destination_index - 1, moved)
        normalized = []
        for index, state in enumerate(states, start=1):
            if state["index"] != index:
                state = dict(state)
                state["index"] = index
            normalized.append(self._validate_slot_state(state))
        affected_start = min(source_index, destination_index)
        affected_end = max(source_index, destination_index)
        self._apply_states_with_rollback(normalized[affected_start - 1 : affected_end])
        return True

    def MoveSlotUp(self, index):
        index = self._slot_index(index)
        return False if index == 1 else self.MoveSlot(index, index - 1)

    def MoveSlotDown(self, index):
        index = self._slot_index(index)
        return False if index == SLOT_COUNT else self.MoveSlot(index, index + 1)

    def SwapSlots(self, first_index, second_index):
        first_index = self._slot_index(first_index)
        second_index = self._slot_index(second_index)
        if first_index == second_index:
            return False
        first = self.SlotState(first_index)
        second = self.SlotState(second_index)
        first["index"], second["index"] = second_index, first_index
        self._apply_states_with_rollback(
            [self._validate_slot_state(second), self._validate_slot_state(first)]
        )
        return True

    def State(self):
        """Return the legacy state fields plus full eight-slot rack state."""
        slot_states = [self.SlotState(index) for index in range(1, SLOT_COUNT + 1)]
        manual_time = self._parameter_value(
            "Manualtime", self._parameter_value("Time", 0.0)
        )
        return {
            "slots": [state["package"] for state in slot_states],
            "time": self._finite_float(self._parameter_value("Time", 0.0), "Time"),
            "manual_time": self._finite_float(manual_time, "Manual time"),
            "slot_states": slot_states,
            "input_routes": [self.SlotInputRoutes(index) for index in range(1, SLOT_COUNT + 1)],
            "autotime": self._parameter_boolean("Autotime", True),
            "timescale": self._finite_float(self._parameter_value("Timescale", 1.0), "Time scale"),
        }
