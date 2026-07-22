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


class FakeConnector:
    def __init__(self, owner):
        self.owner = owner
        self.source = None

    def connect(self, target):
        target.source = self

    def disconnect(self):
        self.source = None


class FakeTOP:
    def __init__(self, name, input_count=1):
        self.name = name
        self.inputConnectors = [FakeConnector(self) for _index in range(input_count)]
        self.outputConnectors = [FakeConnector(self)]


class FakeSlot:
    _next_id = 100

    def __init__(self, name, gain=0.5, input_count=1):
        self.id = FakeSlot._next_id
        FakeSlot._next_id += 1
        self.name = name
        self.owner = None
        self.destroyed = False
        self.par = FakePars()
        self.par.add("Enable", True)
        self.par.add("Mix", 1.0)
        self.par.add("Time", 0.0)
        self.par.add("Timescale", 1.0)
        self.par.add("Reset", False)
        self.par.add("Gain", gain)
        self.customPars = [self.par["Gain"]]
        self.inputConnectors = [FakeConnector(self) for _index in range(input_count)]
        self.outputConnectors = [FakeConnector(self)]

    def destroy(self):
        self.destroyed = True
        owner = self.owner
        if owner is not None and hasattr(owner, "remove_child"):
            owner.remove_child(self)
        elif owner is not None and getattr(owner, "operators", {}).get(self.name) is self:
            owner.operators.pop(self.name, None)


class FakeHistorySlot:
    def __init__(self):
        self.name = "slot1"
        self.par = FakePars()
        self.history = FakeSlot("history_feedback")
        self.history.par.values.pop("Reset")
        self.history.par.add("resetpulse", False)

    def fetch(self, key, default=None):
        if key == "tdimagefx_history_nodes":
            return ["history_feedback"]
        return default

    def op(self, name):
        return self.history if name == "history_feedback" else None


class FakeOwner:
    def __init__(self, root):
        self.par = FakePars()
        self.par.add("Rootfolder", str(root))
        self.par.add("Autotime", True)
        self.par.add("Timescale", 1.0)
        self.par.add("Manualtime", 0.0)
        self.par.add("Time", 0.0)
        self.par.add("Presetname", "")
        self.par.add("Presetpath", "")
        self.par.add("Presetjson", "")
        self.storage = {}
        self.operators = {
            "in1_image": FakeTOP("in1_image", input_count=0),
            "in2_image_b": FakeTOP("in2_image_b", input_count=0),
            "in3_displacement": FakeTOP("in3_displacement", input_count=0),
            "in4_depth": FakeTOP("in4_depth", input_count=0),
            "in5_normal": FakeTOP("in5_normal", input_count=0),
            "in6_flow": FakeTOP("in6_flow", input_count=0),
            "in7_mask": FakeTOP("in7_mask", input_count=0),
            "out1_image": FakeTOP("out1_image"),
        }
        for index in range(1, RACK_MODULE.SLOT_COUNT + 1):
            package_id = "tdimagefx.test.effect{}".format(index)
            self.par.add("Slot{}effect".format(index), package_id)
            self.par.add("Slot{}enable".format(index), True)
            self.par.add("Slot{}mix".format(index), index / 10.0)
            self.par.add("Slot{}moddepth".format(index), 0.0)
            self.par.add("Slot{}modrate".format(index), 1.0)
            self.par.add("Slot{}modstate".format(index), "off")
            self.storage["slot{}_package".format(index)] = {"id": package_id, "version": "1.0.0"}
            slot = FakeSlot("slot{}".format(index), index / 10.0)
            slot.owner = self
            self.operators[slot.name] = slot

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
        slot.owner = self.ownerComp
        self.ownerComp.operators[slot.name] = slot
        self.ownerComp.store(
            "slot{}_package".format(index),
            {"id": package_id, "version": version},
        )
        self._bind_slot(index, slot)
        return slot


class TransactionalOwner:
    def __init__(self, root):
        self.par = FakePars()
        self.par.add("Rootfolder", str(root))
        self.par.add("Slot1effect", "tdimagefx.test.old")
        self.par.add("Slot1enable", True)
        self.par.add("Slot1mix", 1.0)
        self.par.add("Slot1moddepth", 0.0)
        self.par.add("Slot1modrate", 1.0)
        self.par.add("Slot1modstate", "off")
        self.storage = {
            "slot1_package": {"id": "tdimagefx.test.old", "version": "1.0.0"},
            "slot1_input_routes": {"0": "image"},
        }
        self.fixed = {
            "in1_image": FakeTOP("in1_image", input_count=0),
            "out1_image": FakeTOP("out1_image"),
        }
        self.old_slot = FakeSlot("slot1")
        self.old_slot.owner = self
        self._children = [self.old_slot]
        self.loaded_candidate = None
        self.fixed["in1_image"].outputConnectors[0].connect(self.old_slot.inputConnectors[0])
        self.old_slot.outputConnectors[0].connect(self.fixed["out1_image"].inputConnectors[0])

    @property
    def children(self):
        return list(self._children)

    def op(self, name):
        if name in self.fixed:
            return self.fixed[name]
        return next(
            (child for child in self._children if not child.destroyed and child.name == name),
            None,
        )

    def loadTox(self, _path):
        candidate = FakeSlot("loaded_effect")
        candidate.owner = self
        self._children.append(candidate)
        self.loaded_candidate = candidate

    def remove_child(self, child):
        if child in self._children:
            self._children.remove(child)

    def store(self, key, value):
        self.storage[key] = value

    def fetch(self, key, default=None):
        return self.storage.get(key, default)


class TransactionalRack(RACK_MODULE.FxRackExt):
    def _find_manifest(self, package_id, version=None):
        return (
            {
                "id": package_id,
                "version": version or "2.0.0",
                "inputs": [{"id": "image", "family": "TOP"}],
                "entrypoints": {"touchdesigner_component": "tox/effect.tox"},
            },
            Path("package.json"),
        )

    @staticmethod
    def _component_path(_manifest, _manifest_path):
        return Path("effect.tox")


class RenameFailingRack(TransactionalRack):
    def _rename_exact(self, operator, name):
        if operator is self.ownerComp.loaded_candidate and name == "slot1":
            raise RuntimeError("simulated commit failure")
        return super()._rename_exact(operator, name)


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

    def test_auxiliary_inputs_route_by_each_manifest_semantic(self):
        manifest = {
            "inputs": [
                {"id": "image", "semantic": "source"},
                {"id": "vectors", "role": "flow", "semantic": "optical-flow"},
                {"id": "matte", "role": "mask", "semantic": "matte"},
                {"id": "clean_plate", "semantic": "reference"},
            ]
        }
        self.assertEqual(
            self.rack._input_routes(manifest),
            {0: "image", 1: "flow", 2: "mask", 3: "image_b"},
        )
        self.assertEqual(self.rack._rack_input_name("flow"), "in6_flow")
        with self.assertRaisesRegex(RuntimeError, "Unsupported auxiliary"):
            self.rack._input_routes(
                {"inputs": [{"id": "image"}, {"id": "unknown"}]}
            )

        slot = FakeSlot("replacement", input_count=4)
        self.rack._connect_slot(
            1,
            slot,
            {0: "image", 1: "flow", 2: "mask", 3: "image_b"},
        )
        self.assertEqual(slot.inputConnectors[0].source.owner.name, "in1_image")
        self.assertEqual(slot.inputConnectors[1].source.owner.name, "in6_flow")
        self.assertEqual(slot.inputConnectors[2].source.owner.name, "in7_mask")
        self.assertEqual(slot.inputConnectors[3].source.owner.name, "in2_image_b")
        self.assertEqual(
            self.rack.SlotInputRoutes(1),
            {"0": "image", "1": "flow", "2": "mask", "3": "image_b"},
        )

    def test_every_published_auxiliary_input_maps_to_a_rack_bus(self):
        checked = 0
        for manifest_path in sorted((ROOT / "packages").glob("*/*/package.json")):
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            with self.subTest(package=manifest["id"], version=manifest["version"]):
                routes = self.rack._input_routes(manifest)
                self.assertEqual(len(routes), len(manifest["inputs"]))
            checked += 1
        self.assertEqual(checked, 124)

    def test_default_slot_binding_uses_modulation_and_manual_time_is_preset(self):
        slot = self.owner.op("slot1")
        self.rack._bind_slot(1, slot)
        self.assertEqual(slot.par["Mix"].expr, "parent().ModulatedMix(1)")
        self.assertEqual(
            slot.par["Time"].expr,
            "parent().par.Time * me.par.Timescale",
        )
        self.assertTrue(slot.par["Enable"].readOnly)
        self.assertTrue(slot.par["Mix"].readOnly)
        self.assertTrue(slot.par["Time"].readOnly)
        self.assertFalse(hasattr(slot.par["Timescale"], "readOnly"))

        self.owner.par["Manualtime"].val = 4.25
        self.owner.par["Time"].val = 99.0
        preset = self.rack.PresetData()
        self.assertEqual(preset["time"], 4.25)
        preset["time"] = -3.5
        self.rack.ImportPreset(preset)
        self.assertEqual(self.owner.par["Manualtime"].eval(), -3.5)
        self.assertEqual(self.rack.State()["manual_time"], -3.5)

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

    def test_compact_preset_clears_every_unspecified_slot(self):
        preset = self.rack.PresetData("Compact")
        preset["slots"] = [preset["slots"][0], preset["slots"][2]]

        state = self.rack.ImportPreset(preset)

        self.assertIsNotNone(self.owner.op("slot1"))
        self.assertIsNone(self.owner.op("slot2"))
        self.assertIsNotNone(self.owner.op("slot3"))
        for index in range(4, RACK_MODULE.SLOT_COUNT + 1):
            self.assertIsNone(self.owner.op("slot{}".format(index)))
        for index in (2, 4, 5, 6, 7, 8):
            self.assertIsNone(self.owner.fetch("slot{}_package".format(index)))
            self.assertFalse(self.owner.par["Slot{}enable".format(index)].eval())
            self.assertEqual(state["slot_states"][index - 1]["package"], None)

        # Reloading uses installed slot state, so empty slots remain empty even
        # though their menu parameters still have a default package selection.
        self.rack.ReloadAll()
        self.assertIsNone(self.owner.op("slot2"))
        self.assertIsNone(self.owner.op("slot8"))

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

    def test_reset_falls_back_to_private_history_nodes_for_legacy_components(self):
        legacy = FakeHistorySlot()
        self.owner.operators["slot1"] = legacy
        self.assertTrue(self.rack.ResetSlot(1))
        self.assertEqual(legacy.history.par["resetpulse"].pulse_count, 1)

    def test_save_and_load_stay_inside_the_preset_folder(self):
        self.owner.par["Slot3mix"].val = 0.36
        destination = Path(self.rack.SavePreset("looks/demo", "Demo"))
        expected = Path(self.temporary.name) / "presets" / "looks" / "demo.json"
        self.assertEqual(destination, expected.resolve())
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


class FxRackTransactionalLoadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)

    def test_successful_load_commits_new_slot_only_after_wiring(self):
        owner = TransactionalOwner(self.temporary.name)
        old_slot = owner.old_slot
        rack = TransactionalRack(owner)

        replacement = rack.LoadSlot(1, "tdimagefx.test.new", "2.0.0")

        self.assertTrue(old_slot.destroyed)
        self.assertIs(owner.op("slot1"), replacement)
        self.assertEqual(owner.fetch("slot1_package"), {
            "id": "tdimagefx.test.new",
            "version": "2.0.0",
        })
        self.assertIs(owner.fixed["out1_image"].inputConnectors[0].source.owner, replacement)

    def test_failed_commit_restores_prior_slot_and_connections(self):
        owner = TransactionalOwner(self.temporary.name)
        old_slot = owner.old_slot
        rack = RenameFailingRack(owner)

        with self.assertRaisesRegex(RuntimeError, "simulated commit failure"):
            rack.LoadSlot(1, "tdimagefx.test.new", "2.0.0")

        self.assertFalse(old_slot.destroyed)
        self.assertIs(owner.op("slot1"), old_slot)
        self.assertEqual(owner.fetch("slot1_package"), {
            "id": "tdimagefx.test.old",
            "version": "1.0.0",
        })
        self.assertIs(owner.fixed["out1_image"].inputConnectors[0].source.owner, old_slot)
        self.assertNotIn(owner.loaded_candidate, owner.children)


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
