from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "touchdesigner" / "extensions" / "ImageFXLibraryExt.py"
SPEC = importlib.util.spec_from_file_location("tdimagefx_touchdesigner_library", MODULE_PATH)
LIBRARY_MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(LIBRARY_MODULE)


class FakeParameter:
    def __init__(self, value):
        self.value = value

    def eval(self):
        return self.value


class FakeParameters:
    def __init__(self, root):
        self.Rootfolder = FakeParameter(str(root))
        self.Status = FakeParameter("")

    def __getitem__(self, name):
        return getattr(self, name, None)


class FakeOwner:
    def __init__(self, root, catalog=None):
        self.par = FakeParameters(root)
        self.catalog = catalog

    def op(self, name):
        return self.catalog if name == "catalog" else None


class FakeTable:
    def __init__(self, rows=()):
        self.data = [list(row) for row in rows]

    def rows(self):
        return [list(row) for row in self.data]

    def setSize(self, _rows, _columns):
        self.data = []

    def appendRow(self, values):
        self.data.append([str(value) for value in values])


def _write_manifest(root: Path, package_id: str, version: str) -> None:
    package_root = root / "packages" / package_id / version
    package_root.mkdir(parents=True)
    payload = {
        "id": package_id,
        "name": "Versioned Effect",
        "version": version,
        "entrypoints": {"touchdesigner_component": "tox/effect.tox"},
    }
    (package_root / "package.json").write_text(
        json.dumps(payload), encoding="utf-8", newline="\n"
    )


def _write_rich_manifest(root: Path, package_id: str, version: str) -> None:
    package_root = root / "packages" / package_id / version
    package_root.mkdir(parents=True)
    payload = {
        "id": package_id,
        "name": "Depth Aware Blur",
        "version": version,
        "kind": "effect",
        "category": "blur",
        "channel": "experimental",
        "description": "Depth-guided blur.",
        "stateful": False,
        "tags": ["blur", "depth"],
        "entrypoints": {"touchdesigner_component": "tox/effect.tox"},
        "inputs": [
            {"id": "image", "semantic": "source"},
            {"id": "depth", "role": "depth"},
        ],
        "parameters": [
            {"id": "radius", "name": "Radius", "label": "Radius", "type": "float", "unit": "pixels"},
        ],
        "processing": {
            "model": "single_pass",
            "gpu_cost": "high",
            "capabilities": ["second_input", "depth"],
            "quality_tiers": [{"id": "production", "label": "Production"}],
        },
        "compatibility": {
            "touchdesigner_min_build": 2025.3,
            "os": ["windows", "macos"],
            "architectures": ["x86_64", "arm64"],
        },
        "alpha_policy": "process",
        "resolution_policy": "first_input",
        "image_contract": {
            "color": {
                "input_space": "source",
                "working_space": "linear",
                "output_space": "source",
                "reference": "display_referred",
            },
            "alpha": {"input": "any", "working": "any", "output": "any"},
            "pixel_format": {"policy": "inherit"},
            "sampling": {"filter": "linear", "edge": "clamp", "mipmaps": False},
        },
    }
    (package_root / "package.json").write_text(
        json.dumps(payload), encoding="utf-8", newline="\n"
    )


class ImageFXLibraryVersionTests(unittest.TestCase):
    def test_catalog_input_roles_match_rack_bus_aliases(self):
        self.assertEqual(
            LIBRARY_MODULE._manifest_input_roles({
                "inputs": [
                    {"id": "image", "role": "source_image"},
                    {"id": "lut", "role": "auxiliary_image", "semantic": "lut"},
                    {"id": "matte", "semantic": "matte"},
                ]
            }),
            ("image", "image_b", "mask"),
        )

    def test_catalog_defaults_to_latest_and_exact_history_remains_addressable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package_id = "tdimagefx.test.versioned"
            _write_manifest(root, package_id, "1.0.0")
            _write_manifest(root, package_id, "1.1.0")
            library = LIBRARY_MODULE.ImageFXLibraryExt(FakeOwner(root))

            self.assertEqual(library.PackageIds, [package_id])
            self.assertEqual(library.PackageInfo(package_id)["version"], "1.1.0")
            self.assertEqual(library.PackageInfo(package_id, "1.0.0")["version"], "1.0.0")

    def test_refresh_rebuilds_rich_schema_without_losing_native_confidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package_id = "tdimagefx.blur.depth-aware-blur"
            version = "1.0.0"
            _write_rich_manifest(root, package_id, version)
            previous = {column: "" for column in LIBRARY_MODULE.CATALOG_COLUMNS}
            previous.update({
                "id": package_id,
                "version": version,
                "compatibility_confidence": "native build verified: TD 2025.32820 / windows / x86_64",
            })
            catalog = FakeTable((
                LIBRARY_MODULE.CATALOG_COLUMNS,
                tuple(previous[column] for column in LIBRARY_MODULE.CATALOG_COLUMNS),
            ))
            owner = FakeOwner(root, catalog)
            library = LIBRARY_MODULE.ImageFXLibraryExt(owner)

            self.assertEqual(library.RefreshCatalog(), 1)

            self.assertEqual(tuple(catalog.data[0]), LIBRARY_MODULE.CATALOG_COLUMNS)
            row = dict(zip(catalog.data[0], catalog.data[1]))
            self.assertEqual(row["input_count"], "2")
            self.assertEqual(row["input_roles"], "image, depth")
            self.assertEqual(row["input_readiness"], "Needs depth")
            self.assertEqual(row["parameter_count"], "1")
            self.assertIn("Radius (float, pixels)", row["parameters"])
            self.assertIn("color source>linear>source", row["image_contract"])
            self.assertEqual(row["quality"], "experimental (Production)")
            self.assertEqual(
                row["compatibility_confidence"],
                "native build verified: TD 2025.32820 / windows / x86_64",
            )


if __name__ == "__main__":
    unittest.main()
