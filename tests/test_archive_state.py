from __future__ import annotations

import hashlib
import json
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path

from tdimagefx.archive import StageLimits, stage_package
from tdimagefx.errors import SecurityError, StateError
from tdimagefx.feed import SourcePolicy
from tdimagefx.lockfile import LockPin, Lockfile, resolve_lockfile
from tdimagefx.registry import load_local_registry
from tdimagefx.semver import Version
from tdimagefx.state import activate_package, finalize_pending_activation, load_active_state, rollback_package

from tests.helpers import write_package_zip


class ArchiveTests(unittest.TestCase):
    def test_valid_package_is_staged_immutably_and_registered(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "effect.zip"
            digest, _ = write_package_zip(archive)
            store = root / "packages"
            result = stage_package(
                archive,
                store,
                expected_sha256=digest,
                expected_id="tdimagefx.test.effect",
                expected_version="1.0.0",
                policy=SourcePolicy(allow_file=True, file_root=root),
            )
            self.assertTrue(result.manifest_path.is_file())
            registry = load_local_registry(store / "registry.json")
            self.assertEqual(str(registry.packages[result.package_id][0].version), "1.0.0")
            lockfile = Lockfile.create(
                fx_api="1.0",
                touchdesigner_build=2023.1,
                packages=(
                    LockPin(
                        id=result.package_id,
                        version=Version.parse("1.0.0"),
                        kind="effect",
                        channel="stable",
                        source_feed=None,
                        manifest_sha256=result.manifest_sha256,
                        artifact_sha256=result.artifact_sha256,
                        requested=True,
                    ),
                ),
            )
            self.assertIn(result.package_id, resolve_lockfile(lockfile, registry))
            with self.assertRaises(StateError):
                stage_package(
                    archive,
                    store,
                    expected_sha256=digest,
                    policy=SourcePolicy(allow_file=True, file_root=root),
                )

    def test_rejects_traversal_case_collision_and_symlink(self) -> None:
        builders = []

        def traversal(path: Path) -> None:
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("../escape", "bad")

        builders.append(traversal)

        def collision(path: Path) -> None:
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("File.txt", "one")
                archive.writestr("file.txt", "two")

        builders.append(collision)

        def ancestor_collision(path: Path) -> None:
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("Folder", "file")
                archive.writestr("folder/child.txt", "child")

        builders.append(ancestor_collision)

        def symlink(path: Path) -> None:
            info = zipfile.ZipInfo("link")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(info, "target")

        builders.append(symlink)

        for builder in builders:
            with self.subTest(builder=builder.__name__), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                artifact = root / "bad.zip"
                builder(artifact)
                digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
                with self.assertRaises(SecurityError):
                    stage_package(
                        artifact,
                        root / "store",
                        expected_sha256=digest,
                        policy=SourcePolicy(allow_file=True),
                    )
                self.assertFalse((root / "escape").exists())

    def test_rejects_zip_bomb_ratio_and_entrypoint_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "compressed.zip"
            digest, _ = write_package_zip(artifact, extra_entries={"huge.bin": b"0" * (2 * 1024 * 1024)})
            with self.assertRaises(SecurityError):
                stage_package(
                    artifact,
                    root / "store",
                    expected_sha256=digest,
                    policy=SourcePolicy(allow_file=True),
                    limits=StageLimits(max_compression_ratio=10.0),
                )

            missing = root / "missing.zip"
            manifest = {
                "package.json": json.dumps(__import__("tests.helpers", fromlist=["manifest_data"]).manifest_data())
            }
            with zipfile.ZipFile(missing, "w") as archive:
                for name, payload in manifest.items():
                    archive.writestr(name, payload)
            missing_digest = hashlib.sha256(missing.read_bytes()).hexdigest()
            with self.assertRaises(Exception) as caught:
                stage_package(
                    missing,
                    root / "other-store",
                    expected_sha256=missing_digest,
                    policy=SourcePolicy(allow_file=True),
                )
            self.assertIn("entrypoint", str(caught.exception))


class StateTests(unittest.TestCase):
    def _stage(self, root: Path, version: str) -> tuple[Path, str]:
        artifact = root / f"effect-{version}.zip"
        digest, _ = write_package_zip(artifact, version=version)
        store = root / "packages"
        stage_package(
            artifact,
            store,
            expected_sha256=digest,
            policy=SourcePolicy(allow_file=True, file_root=root),
        )
        return store, digest

    def test_activate_upgrade_and_rollback_exact_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, first_hash = self._stage(root, "1.0.0")
            _, second_hash = self._stage(root, "2.0.0")
            state_path = root / "active-state.json"
            first = activate_package(state_path, store, "tdimagefx.test.effect", "1.0.0", expected_artifact_sha256=first_hash)
            self.assertEqual(first.revision, 1)
            second = activate_package(state_path, store, "tdimagefx.test.effect", "2.0.0", expected_artifact_sha256=second_hash)
            self.assertEqual(str(second.active("tdimagefx.test.effect").previous_version), "1.0.0")
            rolled_back = rollback_package(state_path, store, "tdimagefx.test.effect")
            self.assertEqual(str(rolled_back.active("tdimagefx.test.effect").version), "1.0.0")
            self.assertEqual(str(rolled_back.active("tdimagefx.test.effect").previous_version), "2.0.0")

    def test_restart_activation_stays_pending_until_finalized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, digest = self._stage(root, "1.0.0")
            state_path = root / "active-state.json"
            state = activate_package(
                state_path,
                store,
                "tdimagefx.test.effect",
                "1.0.0",
                expected_artifact_sha256=digest,
                requires_restart=True,
            )
            self.assertEqual(state.active("tdimagefx.test.effect").status, "pending_restart")
            self.assertEqual(state.pending("tdimagefx.test.effect").status, "awaiting_restart")
            finalized = finalize_pending_activation(state_path, "tdimagefx.test.effect")
            self.assertEqual(finalized.active("tdimagefx.test.effect").status, "active")
            self.assertIsNone(finalized.pending("tdimagefx.test.effect"))

    def test_manifest_tampering_is_detected_before_activation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, digest = self._stage(root, "1.0.0")
            manifest = store / "tdimagefx.test.effect" / "1.0.0" / "package.json"
            manifest.write_text(manifest.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaises(StateError):
                activate_package(
                    root / "state.json",
                    store,
                    "tdimagefx.test.effect",
                    "1.0.0",
                    expected_artifact_sha256=digest,
                )

    def test_entrypoint_tampering_is_detected_before_activation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store, digest = self._stage(root, "1.0.0")
            shader = store / "tdimagefx.test.effect" / "1.0.0" / "shaders" / "effect.frag"
            shader.write_text("// replaced", encoding="utf-8")
            with self.assertRaises(StateError):
                activate_package(
                    root / "state.json",
                    store,
                    "tdimagefx.test.effect",
                    "1.0.0",
                    expected_artifact_sha256=digest,
                )


if __name__ == "__main__":
    unittest.main()
