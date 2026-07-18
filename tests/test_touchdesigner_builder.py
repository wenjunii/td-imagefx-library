from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.helpers import manifest_data


MODULE_PATH = Path(__file__).resolve().parents[1] / "touchdesigner" / "scripts" / "build_project.py"
SPEC = importlib.util.spec_from_file_location("tdimagefx_touchdesigner_builder", MODULE_PATH)
BUILDER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(BUILDER)


def _write_package(
    packages: Path,
    *,
    directory_id: str = "tdimagefx.test.effect",
    version: str = "1.0.0",
) -> Path:
    package_root = packages / directory_id / version
    shader = package_root / "shaders" / "effect.frag"
    shader.parent.mkdir(parents=True)
    shader.write_text("// builder test shader\n", encoding="utf-8", newline="\n")
    manifest = manifest_data(component="tox/effect.tox")
    manifest["version"] = version
    (package_root / "package.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return package_root


class TouchDesignerBuilderPathTests(unittest.TestCase):
    def test_parameter_callbacks_use_component_relative_target_after_relocation(self) -> None:
        class CallbackParameters:
            op = None
            pars = None
            valuechange = False
            onpulse = False
            custom = False
            builtin = True

        class Callback:
            def __init__(self, owner) -> None:
                self.owner = owner
                self.par = CallbackParameters()
                self.text = ""

            def relativePath(self, target) -> str:
                if target is not self.owner:
                    raise AssertionError("callback target must be its owner component")
                return ".."

        class Owner:
            def __init__(self) -> None:
                self.path = "/project1/td_imagefx/core/fx_rack"
                self.callback = Callback(self)

            def create(self, operator_type, name):
                if operator_type is not BUILDER.parameterexecuteDAT:
                    raise AssertionError("unexpected operator type")
                if name != "parameter_callbacks":
                    raise AssertionError("unexpected callback name")
                return self.callback

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "callbacks.py"
            source.write_text(
                "def onValueChange(par, prev):\n    return\n",
                encoding="utf-8",
            )
            owner = Owner()
            original_type = getattr(BUILDER, "parameterexecuteDAT", None)
            BUILDER.parameterexecuteDAT = object()
            try:
                callback = BUILDER.configure_parameter_callbacks(owner, source, "Slot*")
            finally:
                if original_type is None:
                    del BUILDER.parameterexecuteDAT
                else:
                    BUILDER.parameterexecuteDAT = original_type

        self.assertEqual(callback.par.op, "..")
        self.assertEqual(callback.par.pars, "Slot*")
        self.assertTrue(callback.par.valuechange)
        self.assertTrue(callback.par.onpulse)
        self.assertTrue(callback.par.custom)
        self.assertFalse(callback.par.builtin)

        owner.path = "/project1/imagefx_demo/fx_rack"
        self.assertEqual(callback.par.op, "..")

    def test_feedback_targets_are_repaired_relative_to_loaded_state(self) -> None:
        class Target:
            pass

        class Parameter:
            def __init__(self, owner) -> None:
                self.owner = owner
                self.val = "/project1/build_network/effect/state_target"

            def eval(self):
                return self.owner.target if self.val == "state_target" else None

        class Parent:
            def __init__(self) -> None:
                self.children = []
                self.target = Target()

            def op(self, name):
                return self.target if name == "state_target" else None

        class Feedback:
            name = "history_feedback"
            path = "/project1/rack/slot1/history_feedback"
            children = []

            def __init__(self, parent) -> None:
                self._parent = parent
                self.target = parent.target
                self.parameter = Parameter(self)
                self.par = {"top": self.parameter}

            def parent(self):
                return self._parent

            def relativePath(self, target):
                if target is not self.target:
                    raise AssertionError("unexpected Feedback TOP target")
                return "state_target"

        root = Parent()
        feedback = Feedback(root)
        root.children.append(feedback)

        self.assertEqual(BUILDER._repair_effect_state_paths(root), 1)
        self.assertEqual(feedback.parameter.val, "state_target")
        self.assertIs(feedback.parameter.eval(), root.target)

    def test_random_move_particle_shader_has_bounded_deterministic_controls(self) -> None:
        shader = BUILDER.PARTICLE_RANDOM_MOVE_SHADER
        uniform_names = {
            definition["uniform"]
            for definition in BUILDER.PARTICLE_PARAMETER_DEFINITIONS
            if definition.get("uniform")
        }
        self.assertEqual(
            uniform_names,
            {
                "uTime",
                "uDensity",
                "uSize",
                "uSpeed",
                "uMoveAmount",
                "uJitter",
                "uDrift",
                "uSeed",
                "uShape",
                "uSourceBlend",
                "uOpacity",
                "uBackground",
            },
        )
        for uniform in uniform_names:
            self.assertIn(uniform, shader)
        density = next(
            definition
            for definition in BUILDER.PARTICLE_PARAMETER_DEFINITIONS
            if definition["name"] == "Density"
        )
        self.assertEqual(density["max"], 500)
        self.assertIn("textureSize(sTD2DInputs[0], 0)", shader)
        self.assertIn("particleHash", shader)
        self.assertIn("for (int offsetY = -2; offsetY <= 2; ++offsetY)", shader)
        self.assertIn("for (int offsetX = -2; offsetX <= 2; ++offsetX)", shader)
        self.assertNotIn("feedback", shader.lower())

    def test_native_project_rejects_foreign_top_level_nodes(self) -> None:
        project_comp = SimpleNamespace(
            children=[
                SimpleNamespace(name="td_imagefx"),
                SimpleNamespace(name="imagefx_demo"),
                SimpleNamespace(name="geo1", type="geo"),
                SimpleNamespace(name="out1", type="out"),
                SimpleNamespace(name="noise1", type="noise"),
                SimpleNamespace(name="chopto1", type="chopto"),
                SimpleNamespace(name="displace1", type="displace"),
                SimpleNamespace(name="moviefilein1", type="moviefilein"),
                SimpleNamespace(name="private_show_control"),
            ]
        )
        self.assertEqual(
            BUILDER._foreign_project_node_names(project_comp),
            ["private_show_control"],
        )
        self.assertEqual(
            [node.name for node in BUILDER._default_template_nodes(project_comp)],
            ["geo1", "out1", "noise1", "chopto1", "displace1", "moviefilein1"],
        )

    def test_native_project_save_is_atomic_and_rolls_back(self) -> None:
        class Saver:
            def __init__(self, payload: bytes, *, fail: bool = False) -> None:
                self.payload = payload
                self.fail = fail

            def save(self, path: str, **_kwargs: object) -> bool:
                Path(path).write_bytes(self.payload)
                if self.fail:
                    raise RuntimeError("save failed")
                return True

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "library.toe"
            build_root = root / "build"
            destination.write_bytes(b"old")
            BUILDER._save_project_atomically(destination, build_root, Saver(b"new"))
            self.assertEqual(destination.read_bytes(), b"new")
            self.assertFalse((build_root / ".library.toe.previous").exists())

            class NumberedSaver:
                def save(self, path: str, **_kwargs: object) -> bool:
                    requested = Path(path)
                    requested.with_name(requested.stem + ".1" + requested.suffix).write_bytes(b"wrong")
                    return True

            with self.assertRaisesRegex(RuntimeError, "requested native project"):
                BUILDER._save_project_atomically(destination, build_root, NumberedSaver())
            self.assertEqual(destination.read_bytes(), b"new")
            self.assertFalse((build_root / ".library.toe.previous").exists())
            self.assertFalse((root / "library.1.toe").exists())

            class MirroringSaver:
                def save(self, path: str, **_kwargs: object) -> bool:
                    requested = Path(path)
                    requested.write_bytes(b"mirrored")
                    requested.with_name(requested.stem + ".1" + requested.suffix).write_bytes(
                        b"mirrored"
                    )
                    return True

            BUILDER._save_project_atomically(destination, build_root, MirroringSaver())
            self.assertEqual(destination.read_bytes(), b"mirrored")
            self.assertFalse((root / "library.1.toe").exists())
            self.assertEqual(BUILDER._numbered_project_siblings(destination), set())

            with self.assertRaisesRegex(RuntimeError, "save failed"):
                BUILDER._save_project_atomically(destination, build_root, Saver(b"partial", fail=True))
            self.assertEqual(destination.read_bytes(), b"mirrored")
            self.assertFalse((build_root / ".library.toe.previous").exists())

    def test_versioned_tox_save_preserves_tracked_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "effect.tox"
            path.write_bytes(b"published")
            effect = mock.Mock()
            with mock.patch.object(BUILDER, "_git_tracks_path", return_value=True):
                action = BUILDER._save_versioned_tox(effect, path)
            self.assertEqual(action, "preserved_published")
            self.assertEqual(path.read_bytes(), b"published")
            effect.save.assert_not_called()

    def test_versioned_tox_save_rebuilds_untracked_prepublication_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "effect.tox"
            path.write_bytes(b"draft")
            effect = mock.Mock()
            with mock.patch.object(BUILDER, "_git_tracks_path", return_value=False):
                action = BUILDER._save_versioned_tox(effect, path)
            self.assertEqual(action, "rebuilt_unpublished")
            effect.save.assert_called_once_with(str(path), createFolders=True)

    def test_parameter_metadata_honors_normal_ranges_clamps_help_and_animation(self) -> None:
        parameter = SimpleNamespace(
            default=None,
            val=None,
            min=None,
            max=None,
            normMin=None,
            normMax=None,
            clampMin=None,
            clampMax=None,
        )
        definition = {
            "id": "gain",
            "name": "Gain",
            "label": "Output Gain",
            "page": "Finishing",
            "type": "float",
            "default": 1.0,
            "min": 0.0,
            "max": 8.0,
            "norm_min": 0.25,
            "norm_max": 2.0,
            "clamp_min": False,
            "clamp_max": True,
            "unit": "stops",
            "description": "Controls final intensity.",
            "animatable": False,
        }
        BUILDER._set_par_defaults(parameter, definition)
        self.assertEqual((parameter.normMin, parameter.normMax), (0.25, 2.0))
        self.assertEqual((parameter.clampMin, parameter.clampMax), (False, True))
        help_text = BUILDER._parameter_help(definition)
        self.assertIn("Unit: stops", help_text)
        self.assertIn("animation is not supported", help_text)
        metadata = BUILDER._parameter_metadata(definition)
        self.assertEqual(metadata["page"], "Finishing")
        self.assertFalse(metadata["animatable"])
        self.assertEqual(metadata["normal_maximum"], 2.0)

    def test_catalog_row_exposes_inputs_parameters_image_contract_and_confidence(self) -> None:
        manifest = manifest_data(component="tox/effect.tox")
        manifest["inputs"].append(
            {"id": "depth_map", "family": "TOP", "required": True, "semantic": "depth"}
        )
        manifest["parameters"][0].update(
            {"label": "Effect Mix", "unit": "ratio", "description": "Wet/dry amount."}
        )
        manifest["processing"] = {
            "model": "multi_pass",
            "gpu_cost": "medium",
            "capabilities": ["multi_pass", "depth_aware"],
            "passes": ["shaders/effect.frag", "shaders/effect.frag"],
            "quality_tiers": [
                {"id": "full", "label": "Full", "pass_scale": 1.0, "iterations": 1, "default": True}
            ],
        }
        manifest["image_contract"] = {
            "color": {
                "input_space": "source",
                "working_space": "linear",
                "output_space": "source",
                "reference": "scene_referred",
            },
            "alpha": {"input": "straight", "working": "straight", "output": "straight"},
            "pixel_format": {"policy": "inherit"},
            "sampling": {"filter": "linear", "edge": "clamp", "mipmaps": False},
        }
        row = BUILDER._manifest_catalog_row(manifest, "runtime verified")
        self.assertEqual(row["input_count"], "2")
        self.assertEqual(row["input_roles"], "image, depth")
        self.assertEqual(row["input_readiness"], "Needs depth")
        self.assertIn("Effect Mix (float, ratio)", row["parameters"])
        self.assertIn("color source>linear>source", row["image_contract"])
        self.assertEqual(row["compatibility_confidence"], "runtime verified")
        self.assertEqual(row["quality"], "curated stable (Full)")

    def test_maps_declared_auxiliary_inputs_to_semantic_rack_buses(self) -> None:
        cases = (
            ({"id": "image_b"}, "image_b"),
            ({"id": "alternate", "role": "transition_image"}, "image_b"),
            ({"id": "clean_plate", "semantic": "reference"}, "image_b"),
            ({"id": "map", "semantic": "displacement_map"}, "displacement"),
            ({"id": "map", "semantic": "depth"}, "depth"),
            ({"id": "map", "semantic": "normal-map"}, "normal"),
            ({"id": "vectors", "semantic": "optical-flow"}, "flow"),
            ({"id": "matte"}, "mask"),
        )
        for definition, expected in cases:
            with self.subTest(definition=definition):
                self.assertEqual(BUILDER._rack_input_role(definition, 1), expected)
        self.assertEqual(BUILDER._rack_input_role({"id": "image"}, 0), "image")
        with self.assertRaisesRegex(RuntimeError, "Unsupported auxiliary"):
            BUILDER._rack_input_role({"id": "mystery", "semantic": "unknown"}, 1)

    def test_history_frame_count_is_explicit_and_bounded(self) -> None:
        self.assertEqual(
            BUILDER._history_frame_count({"model": "temporal", "history_frames": 12}),
            12,
        )
        self.assertEqual(
            BUILDER._history_frame_count({"model": "single_pass", "history_frames": 0}),
            0,
        )
        for value in (True, -1, 65, "2"):
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                BUILDER._history_frame_count({"model": "temporal", "history_frames": value})
        with self.assertRaisesRegex(RuntimeError, "at least one"):
            BUILDER._history_frame_count({"model": "simulation", "history_frames": 0})
        self.assertEqual(
            BUILDER._preview_state_iterations(
                {"model": "single_pass", "history_frames": 0}, {}
            ),
            1,
        )
        self.assertEqual(
            BUILDER._preview_state_iterations(
                {"model": "temporal", "history_frames": 12}, {"warmup_frames": 2}
            ),
            12,
        )
        self.assertEqual(
            BUILDER._preview_state_iterations(
                {"model": "simulation", "history_frames": 1}, {"warmup_frames": 32}
            ),
            32,
        )
        self.assertEqual(
            BUILDER._preview_state_iterations(
                {"model": "simulation", "history_frames": 1}, {"warmup_frames": 200}
            ),
            64,
        )
        with self.assertRaisesRegex(RuntimeError, "non-negative integer"):
            BUILDER._preview_state_iterations(
                {"model": "temporal", "history_frames": 1}, {"warmup_frames": -1}
            )

    def test_preview_parameter_suffixes_match_touchdesigner_names(self) -> None:
        cases = {
            "float": ("",),
            "rgb": ("r", "g", "b"),
            "rgba": ("r", "g", "b", "a"),
            "xy": ("x", "y"),
            "xyz": ("x", "y", "z"),
            "uv": ("u", "v"),
        }
        for parameter_type, expected in cases.items():
            with self.subTest(parameter_type=parameter_type):
                self.assertEqual(
                    BUILDER._parameter_suffixes({"type": parameter_type}), expected
                )

    def test_explicit_state_and_render_passes_are_ordered(self) -> None:
        processing = {
            "model": "simulation",
            "state_pass": "shaders/state.frag",
            "render_pass": "shaders/render.frag",
        }
        passes = ["shaders/state.frag", "shaders/render.frag"]
        self.assertEqual(
            BUILDER._state_render_passes(processing, passes),
            ("shaders/state.frag", "shaders/render.frag"),
        )
        with self.assertRaisesRegex(RuntimeError, "precede"):
            BUILDER._state_render_passes(processing, list(reversed(passes)))
        with self.assertRaisesRegex(RuntimeError, "declared together"):
            BUILDER._state_render_passes(
                {"model": "simulation", "state_pass": "shaders/state.frag"},
                passes,
            )

    def test_stateful_reset_defaults_to_pulse_and_accepts_toggle(self) -> None:
        compile(BUILDER.RESET_CALLBACK_SOURCE, "<reset_callbacks>", "exec")
        self.assertEqual(BUILDER._reset_parameter_type({"parameters": []}), "pulse")
        self.assertEqual(
            BUILDER._reset_parameter_type(
                {"parameters": [{"name": "Reset", "type": "toggle"}]}
            ),
            "toggle",
        )
        with self.assertRaisesRegex(RuntimeError, "pulse or toggle"):
            BUILDER._reset_parameter_type(
                {"parameters": [{"name": "Reset", "type": "float"}]}
            )

    def test_loads_validated_layout_and_allows_bounded_new_tox_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            packages = Path(temporary) / "packages"
            package_root = _write_package(packages)
            with mock.patch.object(BUILDER, "PACKAGE_ROOT", packages):
                manifests = BUILDER.load_manifests()

            self.assertEqual(len(manifests), 1)
            output = BUILDER._manifest_asset(
                manifests[0],
                manifests[0]["entrypoints"]["touchdesigner_component"],
                "$.entrypoints.touchdesigner_component",
                must_exist=False,
            )
            self.assertEqual(output, package_root.resolve() / "tox" / "effect.tox")

    def test_validates_history_but_selects_only_the_latest_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            packages = Path(temporary) / "packages"
            _write_package(packages, version="1.0.0")
            latest_root = _write_package(packages, version="1.1.0")
            with mock.patch.object(BUILDER, "PACKAGE_ROOT", packages):
                manifests = BUILDER.load_manifests()

            self.assertEqual(len(manifests), 1)
            self.assertEqual(manifests[0]["version"], "1.1.0")
            self.assertEqual(manifests[0]["_path"], latest_root.resolve() / "package.json")

    def test_rejects_manifest_directory_identity_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            packages = Path(temporary) / "packages"
            _write_package(packages, directory_id="tdimagefx.test.wrong-directory")
            with mock.patch.object(BUILDER, "PACKAGE_ROOT", packages):
                with self.assertRaisesRegex(RuntimeError, "Manifest layout"):
                    BUILDER.load_manifests()

    def test_rejects_declared_shader_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            packages = root / "packages"
            package_root = _write_package(packages)
            shader = package_root / "shaders" / "effect.frag"
            outside = root / "outside.frag"
            outside.write_text("// outside\n", encoding="utf-8")
            shader.unlink()
            try:
                shader.symlink_to(outside)
            except OSError as exc:
                self.skipTest("symbolic links are unavailable: {}".format(exc))

            with mock.patch.object(BUILDER, "PACKAGE_ROOT", packages):
                with self.assertRaisesRegex(RuntimeError, "symbolic link"):
                    BUILDER.load_manifests()


if __name__ == "__main__":
    unittest.main()
