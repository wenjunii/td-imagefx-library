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

    def __getitem__(self, name):
        return getattr(self, name, None)


class FakeOwner:
    def __init__(self, root):
        self.par = FakeParameters(root)


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


class ImageFXLibraryVersionTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
