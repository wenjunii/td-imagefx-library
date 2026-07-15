from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
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
