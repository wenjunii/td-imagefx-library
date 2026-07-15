from __future__ import annotations

import importlib.util
import json
import math
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXTENSION_PATH = ROOT / "touchdesigner" / "extensions" / "FxRackExt.py"
CALLBACK_PATH = ROOT / "touchdesigner" / "callbacks" / "rack_parameter_callbacks.py"


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


RACK_MODULE = _load_module("tdimagefx_touchdesigner_rack", EXTENSION_PATH)
CALLBACK_MODULE = _load_module("tdimagefx_touchdesigner_rack_callbacks", CALLBACK_PATH)


class FakePar:
    def __init__(self, name, value=None):
        self.name = name
        self.val = value
        self.expr = ""
        self.pulse_count = 0

    def eval(self):
        return self.val

    def pulse(self):
        self.pulse_count += 1


class FakePars:
    def __init__(self):
        object.__setattr__(self, "values", {})

    def add(self, name, value=None):
        parameter = FakePar(name, value)
        self.values[name] = parameter
        return parameter

    def __getitem__(self, name):
        return self.values.get(name)

    def __getattr__(self, name):
        return self.values.get(name)

    def __setattr__(self, name, value):
        if name == "values":
            object.__setattr__(self, name, value)
            return
        parameter = self.values.get(name)
        if parameter is None:
            parameter = self.add(name)
        parameter.val = value


class FakeSlot:
    def __init__(self, name, gain=0.5):
        self.name = name
        self.par = FakePars()
        self.par.add("Enable", True)
        self.par.add("Mix", 1.0)
        self.par.add("Time", 0.0)
        self.par.add("Reset", False)
        self.par.add("Gain", gain)
        self.customPars = [self.par["Gain"]]


class FakeOwner:
    def __init__(self, root):
        self.par = FakePars()
        self.par.add("Rootfolder", str(root))
        self.par.add("Autotime", True)
        self.par.add("Timescale", 1.0)
        self.par.add("Time", 0.0)
        self.par.add("Presetname", "")
        self.par.add("Presetpath", "")
        self.par.add("Presetjson", "")
        self.storage = {}
        self.operators = {}
        for index in range(1, RACK_MODULE.SLOT_COUNT + 1):
            package_id = "tdimagefx.test.effect{}".format(index)
            self.par.add("Slot{}effect".format(index), package_id)
            self.par.add("Slot{}enable".format(index), True)
            self.par.add("Slot{}mix".format(index), index / 10.0)
            self.par.add("Slot{}moddepth".format(index), 0.0)
            self.par.add("Slot{}modrate".format(index), 1.0)
            self.par.add("Slot{}modstate".format(index), "off")
            self.storage["slot{}_package".format(index)] = {"id": package_id, "version": "1.0.0"}
            self.operators["slot{}".format(index)] = FakeSlot("slot{}".format(index), index / 10.0)

    def op(self, name):
        return self.operators.get(name)

    def store(self, key, value):
        self.storage[key] = value

    def fetch(self, key, default=None):
        return self.storage.get(key, default)


class InMemoryRack(RACK_MODULE.FxRackExt):
    def LoadSlot(self, index, package_id=None, version=None):
        index = self._slot_index(index)
        package_id = package_id or self._parameter_value("Slot{}effect".format(index))
        version = version or "1.0.0"
        slot = FakeSlot("slot{}".format(index))
        self.ownerComp.operators[slot.name] = slot
        self.ownerComp.store(
            "slot{}_package".format(index),
            {"id": package_id, "version": version},
        )
        self._bind_slot(index, slot)
        return slot


class FxRackExtensionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.owner = FakeOwner(self.temporary.name)
        self.rack = InMemoryRack(self.owner)

    def test_slot_index_supports_eight_slots_and_rejects_ambiguous_values(self):
        self.assertEqual(self.rack._slot_index("8"), 8)
        for value in (0, 9, True, 1.5, "bad"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.rack._slot_index(value)

    def test_modulation_evaluates_bounded_waveforms_and_validates_fields(self):
        self.owner.par["Slot1mix"].val = 0.5
        self.rack.SetModulation(1, depth=0.2, rate=1.0, state="sine")
        self.assertAlmostEqual(self.rack.ModulatedMix(1, time_value=0.25), 0.7)

        self.rack.SetModulation(1, depth=0.8, rate=1.0, state="triangle")
        self.assertEqual(self.rack.ModulatedMix(1, time_value=0.5), 1.0)
        self.rack.SetModulation(1, state="off")
        self.assertEqual(self.rack.ModulatedMix(1, time_value=0.5), 0.5)

        for arguments in (
            {"depth": 1.01},
            {"rate": 61.0},
            {"rate": math.nan},
            {"state": "random"},
        ):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                self.rack.SetModulation(1, **arguments)

    def test_state_preserves_legacy_fields_and_exposes_full_slot_state(self):
        state = self.rack.State()
        self.assertEqual(len(state["slots"]), 8)
        self.assertEqual(len(state["slot_states"]), 8)
        self.assertEqual(state["slots"][7]["id"], "tdimagefx.test.effect8")
        self.assertIn("modulation", state["slot_states"][0])

    def test_json_preset_round_trip_restores_package_controls_and_effect_values(self):
        self.owner.par["Slot1mix"].val = 0.23
        self.owner.op("slot1").par["Gain"].val = 0.77
        self.rack.SetModulation(1, depth=-0.4, rate=2.5, state="saw")
        preset_text = self.rack.ExportPreset("Round Trip")
        preset = json.loads(preset_text)
        self.assertEqual(preset["schema_version"], 1)
        self.assertEqual(len(preset["slots"]), 8)

        self.owner.par["Slot1mix"].val = 0.9
        self.owner.op("slot1").par["Gain"].val = 0.1
        self.rack.LoadSlot(1, "tdimagefx.test.replacement", "2.0.0")
        self.rack.ImportPreset(preset_text)

        self.assertEqual(self.owner.fetch("slot1_package")["id"], "tdimagefx.test.effect1")
        self.assertAlmostEqual(self.owner.par["Slot1mix"].eval(), 0.23)
        self.assertAlmostEqual(self.owner.op("slot1").par["Gain"].eval(), 0.77)
        self.assertEqual(
            self.rack.ModulationState(1),
            {"depth": -0.4, "rate": 2.5, "state": "saw"},
        )

    def test_move_slot_down_preserves_each_effects_controls(self):
        self.owner.par["Slot1mix"].val = 0.11
        self.owner.par["Slot2mix"].val = 0.82
        self.owner.op("slot1").par["Gain"].val = 0.31
        self.owner.op("slot2").par["Gain"].val = 0.92

        self.assertTrue(self.rack.MoveSlotDown(1))
        self.assertEqual(self.owner.fetch("slot1_package")["id"], "tdimagefx.test.effect2")
        self.assertEqual(self.owner.fetch("slot2_package")["id"], "tdimagefx.test.effect1")
        self.assertAlmostEqual(self.owner.par["Slot1mix"].eval(), 0.82)
        self.assertAlmostEqual(self.owner.par["Slot2mix"].eval(), 0.11)
        self.assertAlmostEqual(self.owner.op("slot1").par["Gain"].eval(), 0.92)
        self.assertAlmostEqual(self.owner.op("slot2").par["Gain"].eval(), 0.31)
        self.assertFalse(self.rack.MoveSlotUp(1))
        self.assertFalse(self.rack.MoveSlotDown(8))

    def test_bypass_and_reset_are_available_per_slot_and_globally(self):
        self.assertFalse(self.rack.BypassSlot(1, True))
        self.assertFalse(self.owner.par["Slot1enable"].eval())
        self.assertTrue(self.rack.ToggleBypass(1))
        self.assertTrue(self.owner.par["Slot1enable"].eval())
        self.assertTrue(self.rack.ResetSlot(1))
        self.assertEqual(self.owner.op("slot1").par["Reset"].pulse_count, 1)

        self.rack.BypassAll(True)
        self.assertTrue(all(not self.owner.par["Slot{}enable".format(i)].eval() for i in range(1, 9)))
        self.rack.Reset()
        self.assertTrue(all(self.owner.op("slot{}".format(i)).par["Reset"].pulse_count for i in range(1, 9)))

    def test_save_and_load_stay_inside_the_preset_folder(self):
        self.owner.par["Slot3mix"].val = 0.36
        destination = Path(self.rack.SavePreset("looks/demo", "Demo"))
        self.assertEqual(destination, Path(self.temporary.name) / "presets" / "looks" / "demo.json")
        self.assertTrue(destination.is_file())

        self.owner.par["Slot3mix"].val = 0.99
        self.rack.LoadPreset("looks/demo.json")
        self.assertAlmostEqual(self.owner.par["Slot3mix"].eval(), 0.36)
        with self.assertRaisesRegex(ValueError, "inside the library presets"):
            self.rack.SavePreset("../outside.json")

    def test_save_does_not_follow_a_preplanted_temporary_symlink(self):
        preset_root = Path(self.temporary.name) / "presets"
        preset_root.mkdir()
        outside = Path(self.temporary.name) / "outside.txt"
        outside.write_text("unchanged", encoding="utf-8")
        legacy_temporary = preset_root / "safe.json.tmp"
        try:
            legacy_temporary.symlink_to(outside)
        except OSError as exc:
            self.skipTest("symbolic links are unavailable: {}".format(exc))

        destination = Path(self.rack.SavePreset("safe.json", "Safe"))
        self.assertTrue(destination.is_file())
        self.assertEqual(outside.read_text(encoding="utf-8"), "unchanged")
        self.assertTrue(legacy_temporary.is_symlink())

    def test_preset_validation_rejects_duplicates_and_non_finite_values(self):
        with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
            self.rack.ImportPreset('{"schema_version":1,"schema_version":1}')

        preset = self.rack.PresetData()
        preset["slots"][1]["index"] = 1
        with self.assertRaisesRegex(ValueError, "duplicate slot"):
            self.rack.ValidatePreset(preset)

        preset = self.rack.PresetData()
        preset["slots"][0]["modulation"]["depth"] = math.inf
        with self.assertRaisesRegex(ValueError, "finite"):
            self.rack.ValidatePreset(preset)


class CallbackRack:
    def __init__(self):
        self.CallbacksSuspended = False
        self.par = FakePars()
        self.par.add("Presetname", "My Preset")
        self.par.add("Presetpath", "my-preset.json")
        self.par.add("Presetjson", "{}")
        self.calls = []

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            if name == "ExportPreset":
                return '{"preset": true}\n'
            return True

        return record


class FxRackCallbackTests(unittest.TestCase):
    def setUp(self):
        self.rack = CallbackRack()
        self.original_parent = getattr(CALLBACK_MODULE, "parent", None)
        CALLBACK_MODULE.parent = lambda: self.rack

    def tearDown(self):
        if self.original_parent is None:
            del CALLBACK_MODULE.parent
        else:
            CALLBACK_MODULE.parent = self.original_parent

    def test_value_callbacks_dispatch_effect_modulation_and_bypass(self):
        CALLBACK_MODULE.onValueChange(FakePar("Slot8effect", "tdimagefx.test.eight"), None)
        CALLBACK_MODULE.onValueChange(FakePar("Slot3moddepth", 0.4), None)
        CALLBACK_MODULE.onValueChange(FakePar("Slot2bypass", True), None)
        self.assertEqual(self.rack.calls[0], ("LoadSlot", (8, "tdimagefx.test.eight"), {}))
        self.assertEqual(
            self.rack.calls[1],
            ("SetModulation", (3,), {"depth": 0.4, "update_parameters": False}),
        )
        self.assertEqual(self.rack.calls[2], ("BypassSlot", (2, True), {}))

    def test_pulse_callbacks_dispatch_reorder_and_preset_actions(self):
        CALLBACK_MODULE.onPulse(FakePar("Slot4up"))
        CALLBACK_MODULE.onPulse(FakePar("Exportpreset"))
        self.assertEqual(self.rack.calls[0], ("MoveSlotUp", (4,), {}))
        self.assertEqual(self.rack.par["Presetjson"].eval(), '{"preset": true}\n')

        self.rack.CallbacksSuspended = True
        CALLBACK_MODULE.onPulse(FakePar("Reset"))
        self.assertEqual(len(self.rack.calls), 2)


if __name__ == "__main__":
    unittest.main()
