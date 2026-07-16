from __future__ import annotations

import hashlib
import json
import multiprocessing
import stat
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from tdimagefx.archive import StageLimits, stage_package
from tdimagefx.errors import SecurityError, StateError, ValidationError
from tdimagefx.feed import SourcePolicy
from tdimagefx.lockfile import LockPin, Lockfile, resolve_lockfile
from tdimagefx.registry import load_local_registry
from tdimagefx.semver import Version
from tdimagefx.state import activate_package, finalize_pending_activation, load_active_state, rollback_package

from tests.helpers import manifest_data, write_package_zip


def _stage_concurrently(
    archive_path: str,
    store_path: str,
    root_path: str,
    digest: str,
    gate,
    result_queue,
) -> None:
    """Process target that widens the historic stale-registry race."""

    import tdimagefx.archive as archive_module

    original_save = archive_module.save_local_registry

    def delayed_save(path, registry):
        time.sleep(0.75)
        return original_save(path, registry)

    archive_module.save_local_registry = delayed_save
    try:
        gate.wait(timeout=15)
        archive_module.stage_package(
            archive_path,
            store_path,
            expected_sha256=digest,
            policy=SourcePolicy(allow_file=True, file_root=Path(root_path)),
        )
    except BaseException as exc:
        result_queue.put(f"{type(exc).__name__}: {exc}")
    else:
        result_queue.put(None)


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

    def test_rejects_every_missing_manifest_declared_asset(self) -> None:
        manifest = manifest_data()
        manifest["processing"] = {
            "model": "multi_pass",
            "gpu_cost": "medium",
            "capabilities": ["multi_pass"],
            "passes": ["shaders/effect.frag", "shaders/pass2.frag"],
            "history_frames": 0,
        }
        manifest["provenance"] = {
            "origin": "original",
            "source": {"type": "original"},
            "changelog": "CHANGELOG.md",
            "examples": ["examples/demo.toe"],
            "presets": ["presets/demo.json"],
        }
        declared_assets: dict[str, str] = {
            "shaders/effect.frag": "// first pass",
            "shaders/pass2.frag": "// second pass",
            "CHANGELOG.md": "# Changes",
            "examples/demo.toe": "example",
            "presets/demo.json": "{}",
        }
        cases = {
            "shaders/pass2.frag": "processing pass 1",
            "CHANGELOG.md": "provenance changelog",
            "examples/demo.toe": "provenance example 0",
            "presets/demo.json": "provenance preset 0",
        }

        for missing_path, expected_label in cases.items():
            with self.subTest(missing_path=missing_path), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                artifact = root / "missing-declared-asset.zip"
                with zipfile.ZipFile(artifact, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr("package.json", json.dumps(manifest))
                    for relative_path, payload in declared_assets.items():
                        if relative_path != missing_path:
                            archive.writestr(relative_path, payload)
                digest = hashlib.sha256(artifact.read_bytes()).hexdigest()

                with self.assertRaises(ValidationError) as caught:
                    stage_package(
                        artifact,
                        root / "store",
                        expected_sha256=digest,
                        policy=SourcePolicy(allow_file=True, file_root=root),
                    )

                message = str(caught.exception)
                self.assertIn(expected_label, message)
                self.assertIn(missing_path, message)
                self.assertFalse((root / "store" / manifest["id"] / manifest["version"]).exists())

    def test_concurrent_staging_preserves_every_registry_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = root / "packages"
            inputs: list[tuple[Path, str, str]] = []
            for index in range(2):
                package_id = f"tdimagefx.test.concurrent-{index}"
                artifact = root / f"effect-{index}.zip"
                digest, _ = write_package_zip(artifact, package_id=package_id)
                inputs.append((artifact, digest, package_id))

            context = multiprocessing.get_context("spawn")
            gate = context.Barrier(len(inputs))
            result_queue = context.Queue()
            processes = [
                context.Process(
                    target=_stage_concurrently,
                    args=(str(artifact), str(store), str(root), digest, gate, result_queue),
                )
                for artifact, digest, _package_id in inputs
            ]
            try:
                for process in processes:
                    process.start()
                for process in processes:
                    process.join(timeout=30)
                    if process.is_alive():
                        process.terminate()
                        process.join(timeout=5)
                    self.assertEqual(process.exitcode, 0)
                errors = [result_queue.get(timeout=5) for _process in processes]
            finally:
                result_queue.close()
                result_queue.join_thread()

            self.assertEqual(errors, [None, None])
            registry = load_local_registry(store / "registry.json")
            self.assertEqual(set(registry.packages), {item[2] for item in inputs})
            for _artifact, _digest, package_id in inputs:
                self.assertTrue((store / package_id / "1.0.0" / "package.json").is_file())

    def test_registry_write_failure_rolls_back_install_and_releases_lock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "effect.zip"
            digest, _ = write_package_zip(artifact)
            store = root / "packages"
            with mock.patch(
                "tdimagefx.archive.save_local_registry",
                side_effect=OSError("injected registry failure"),
            ):
                with self.assertRaisesRegex(OSError, "injected registry failure"):
                    stage_package(
                        artifact,
                        store,
                        expected_sha256=digest,
                        policy=SourcePolicy(allow_file=True, file_root=root),
                    )
            install = store / "tdimagefx.test.effect" / "1.0.0"
            self.assertFalse(install.exists())
            self.assertFalse((store / "registry.json").exists())

            result = stage_package(
                artifact,
                store,
                expected_sha256=digest,
                policy=SourcePolicy(allow_file=True, file_root=root),
            )
            self.assertEqual(result.install_path, install)


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
