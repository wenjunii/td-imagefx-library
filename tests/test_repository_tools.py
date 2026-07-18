from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from tdimagefx.registry import UpdateFeed
from tools import build_gallery, new_effect, package_release, verify_repository


def _effect_args(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "slug": "soft-focus",
        "name": "Soft Focus",
        "category": "blur",
        "version": "1.0.0",
        "model": "single_pass",
        "gpu_cost": "low",
        "capability": [],
        "history_frames": 0,
        "inputs": 1,
        "description": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _write_tool_manifest(
    root: Path,
    package_id: str,
    *,
    name: str,
    category: str,
    version: str = "1.0.0",
    channel: str = "stable",
    processing: dict[str, object] | None = None,
) -> Path:
    package_root = root / "packages" / package_id / version
    package_root.mkdir(parents=True)
    (root / "LICENSE").write_text("Test MIT license\n", encoding="utf-8", newline="\n")
    (root / "THIRD_PARTY_NOTICES.md").write_text(
        "# Test notices\n", encoding="utf-8", newline="\n"
    )
    manifest = {
        "schema_version": 1,
        "id": package_id,
        "name": name,
        "version": version,
        "fx_api": "1.0",
        "kind": "effect",
        "category": category,
        "channel": channel,
        "description": f"{name} description.",
        "publisher": "Tests",
        "license": "MIT",
        "entrypoints": {
            "shader": "shaders/effect.frag",
            "touchdesigner_component": "tox/effect.tox",
        },
        "inputs": [{"id": "image", "family": "TOP", "required": True}],
        "outputs": [{"id": "image", "family": "TOP"}],
        "parameters": [
            {"id": "enable", "name": "Enable", "type": "toggle", "default": True},
            {
                "id": "mix",
                "name": "Mix",
                "label": "Wet Mix",
                "type": "float",
                "default": 1.0,
                "min": 0.0,
                "max": 1.0,
            },
        ],
        "compatibility": {
            "touchdesigner_min_build": 2022.2,
            "touchdesigner_max_build": None,
            "os": ["windows", "macos"],
            "architectures": ["x86_64", "arm64"],
        },
        "permissions": {
            "python": False,
            "filesystem": False,
            "network": False,
            "subprocess": False,
        },
        "dependencies": [],
        "alpha_policy": "preserve",
        "resolution_policy": "input",
        "stateful": False,
        "tags": list(dict.fromkeys((category, "test"))),
    }
    if processing is not None:
        manifest["processing"] = processing
    (package_root / "package.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    shader = package_root / "shaders" / "effect.frag"
    shader.parent.mkdir()
    shader.write_text("// test shader\n", encoding="utf-8", newline="\n")
    component = package_root / "tox" / "effect.tox"
    component.parent.mkdir()
    component.write_bytes(b"test-tox")
    return package_root


class NewEffectToolTests(unittest.TestCase):
    def test_scaffold_multi_pass_writes_contract_and_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            packages = Path(temporary) / "packages"
            args = _effect_args(
                model="multi_pass",
                gpu_cost="medium",
                capability=["multi_pass", "multi_pass"],
                inputs=2,
                description="A deterministic test scaffold.",
            )
            with mock.patch.object(new_effect, "PACKAGES", packages):
                package_root = new_effect.scaffold(args)
                with self.assertRaisesRegex(SystemExit, "refusing to overwrite"):
                    new_effect.scaffold(args)

            manifest = json.loads((package_root / "package.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["id"], "tdimagefx.blur.soft-focus")
            self.assertEqual(manifest["processing"]["model"], "multi_pass")
            self.assertEqual(manifest["processing"]["passes"], [
                "shaders/soft_focus.frag",
                "shaders/pass2.frag",
            ])
            self.assertEqual(manifest["processing"]["capabilities"], ["multi_pass", "second_input"])
            self.assertEqual(len(manifest["inputs"]), 2)
            self.assertTrue((package_root / "shaders" / "soft_focus.frag").is_file())
            second_pass = (package_root / "shaders" / "pass2.frag").read_text(encoding="utf-8")
            self.assertIn("sTD2DInputs[1]", second_pass)

    def test_scaffold_rejects_unsafe_slug_and_missing_temporal_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            packages = Path(temporary) / "packages"
            with mock.patch.object(new_effect, "PACKAGES", packages):
                with self.assertRaisesRegex(SystemExit, "slug must contain"):
                    new_effect.scaffold(_effect_args(slug="../escape"))
                for invalid_version in ("../../escape", "1.0", "01.0.0", "1.0.0-01", "C:\\outside"):
                    with self.subTest(version=invalid_version):
                        with self.assertRaisesRegex(SystemExit, "valid SemVer"):
                            new_effect.scaffold(_effect_args(version=invalid_version))
                with self.assertRaisesRegex(SystemExit, "require --history-frames"):
                    new_effect.scaffold(_effect_args(model="temporal", history_frames=0))
                with self.assertRaisesRegex(SystemExit, "history capability requires"):
                    new_effect.scaffold(_effect_args(capability=["history"], history_frames=0))
            self.assertFalse(packages.exists())


class PackageReleaseToolTests(unittest.TestCase):
    def test_package_zip_is_byte_deterministic_and_normalizes_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package_root = _write_tool_manifest(
                root,
                "tdimagefx.test.deterministic",
                name="Deterministic",
                category="test",
                processing={
                    "model": "multi_pass",
                    "gpu_cost": "medium",
                    "capabilities": ["multi_pass"],
                    "passes": ["shaders/effect.frag", "shaders/pass2.frag"],
                    "history_frames": 0,
                },
            )
            (package_root / "shaders" / "pass2.frag").write_text(
                "// second pass\n", encoding="utf-8", newline="\n"
            )
            (package_root / "z-last.txt").write_text("last\n", encoding="utf-8")
            (package_root / ".env").write_text("SECRET_DO_NOT_PACKAGE=test\n", encoding="utf-8")
            first = root / "first.zip"
            second = root / "second.zip"

            package_release.package_zip(package_root, first)
            os.utime(package_root / "package.json", (2_000_000_000, 2_000_000_000))
            package_release.package_zip(package_root, second)

            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                infos = archive.infolist()
            self.assertEqual([info.filename for info in infos], [
                "LICENSE",
                "THIRD_PARTY_NOTICES.md",
                "package.json",
                "shaders/effect.frag",
                "shaders/pass2.frag",
                "tox/effect.tox",
            ])
            self.assertTrue(all(info.date_time == package_release.FIXED_ZIP_TIME for info in infos))
            self.assertTrue(all(info.create_system == 3 for info in infos))
            self.assertTrue(all(info.external_attr >> 16 == 0o100644 for info in infos))

    def test_package_zip_rejects_declared_asset_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package_root = _write_tool_manifest(
                root,
                "tdimagefx.test.symlink",
                name="Symlink",
                category="test",
            )
            shader = package_root / "shaders" / "effect.frag"
            secret = package_root / "undeclared-secret.txt"
            shader.unlink()
            secret.write_text("must not be packaged\n", encoding="utf-8")
            try:
                shader.symlink_to(secret)
            except OSError as exc:
                self.skipTest("symbolic links are unavailable: {}".format(exc))

            with self.assertRaisesRegex(package_release.ReleaseError, "symbolic links"):
                package_release.package_zip(package_root, root / "unsafe.zip")
            self.assertFalse((root / "unsafe.zip").exists())

    def test_build_release_rejects_traversal_manifest_before_writing_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package_root = _write_tool_manifest(
                root,
                "tdimagefx.test.escape",
                name="Escape",
                category="test",
            )
            manifest_path = package_root / "package.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["id"] = "../../escape"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8", newline="\n")
            output = root / "dist" / "packages"

            with mock.patch.object(package_release, "ROOT", root):
                with self.assertRaisesRegex(package_release.ReleaseError, "Invalid package manifest"):
                    package_release.build_release(
                        output,
                        root / "dist" / "feed.json",
                        release_tag="v1.0.0",
                        generated_at="2030-01-02T03:04:05Z",
                        repository="example/imagefx",
                    )

            self.assertEqual(list(output.glob("*.zip")), [])
            self.assertFalse((root / "escape-1.0.0.zip").exists())

    def test_build_release_feed_and_artifacts_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_tool_manifest(
                root,
                "tdimagefx.test.zeta",
                name="Zeta",
                category="test",
                channel="experimental",
            )
            _write_tool_manifest(root, "tdimagefx.test.alpha", name="Alpha", category="test")
            _write_tool_manifest(
                root,
                "tdimagefx.test.alpha",
                name="Alpha",
                category="test",
                version="1.1.0",
            )
            first_output = root / "dist-a" / "packages"
            second_output = root / "dist-b" / "packages"
            first_feed = root / "dist-a" / "feed.json"
            second_feed = root / "dist-b" / "feed.json"
            options = {
                "release_tag": "v9.8.7",
                "generated_at": "2030-01-02T03:04:05Z",
                "repository": "example/imagefx",
            }

            with mock.patch.object(package_release, "ROOT", root):
                feed_a = package_release.build_release(first_output, first_feed, **options)
                feed_b = package_release.build_release(second_output, second_feed, **options)

            self.assertEqual(feed_a, feed_b)
            self.assertEqual(feed_a["feed_id"], package_release.PUBLIC_CATALOG_FEED_ID)
            self.assertEqual(feed_a["channel"], "experimental")
            self.assertEqual(first_feed.read_bytes(), second_feed.read_bytes())
            self.assertEqual(
                [package["id"] for package in feed_a["packages"]],
                ["tdimagefx.test.alpha", "tdimagefx.test.zeta"],
            )
            self.assertEqual(feed_a["packages"][0]["releases"][0]["version"], "1.1.0")
            self.assertFalse((first_output / "tdimagefx.test.alpha-1.0.0.zip").exists())
            UpdateFeed.from_data(feed_a)
            for package in feed_a["packages"]:
                release = package["releases"][0]
                artifact = release["artifacts"][0]
                artifact_name = artifact["url"].rsplit("/", 1)[-1]
                first_artifact = first_output / artifact_name
                second_artifact = second_output / artifact_name
                self.assertEqual(first_artifact.read_bytes(), second_artifact.read_bytes())
                self.assertEqual(artifact["sha256"], package_release.sha256_file(first_artifact))
                self.assertEqual(artifact["size_bytes"], first_artifact.stat().st_size)
                self.assertIn("/releases/download/v9.8.7/", artifact["url"])
                self.assertIn(
                    "/v9.8.7/packages/",
                    release["manifest_url"],
                )

            with mock.patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "0"}):
                self.assertEqual(package_release._timestamp(None), "1970-01-01T00:00:00Z")

    def test_release_source_binding_requires_tag_and_revision_to_share_a_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "user.email", "tests@example.test"], cwd=root, check=True
            )
            subprocess.run(
                ["git", "config", "user.name", "Tests"], cwd=root, check=True
            )
            marker = root / "marker.txt"
            marker.write_text("one\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "one"], cwd=root, check=True)
            tagged = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True
            ).strip()
            subprocess.run(["git", "tag", "v1.2.3"], cwd=root, check=True)

            self.assertEqual(
                package_release.verify_release_source_binding(root, "v1.2.3", tagged),
                tagged,
            )

            marker.write_text("two\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "two"], cwd=root, check=True)
            newer = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True
            ).strip()
            with self.assertRaisesRegex(package_release.ReleaseError, "not source revision"):
                package_release.verify_release_source_binding(root, "v1.2.3", newer)

    def test_release_source_binding_rejects_dirty_release_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "user.email", "tests@example.test"], cwd=root, check=True
            )
            subprocess.run(["git", "config", "user.name", "Tests"], cwd=root, check=True)
            package = root / "packages" / "tdimagefx.test.clean" / "1.0.0"
            package.mkdir(parents=True)
            manifest = package / "package.json"
            manifest.write_text("tracked\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "release"], cwd=root, check=True)
            revision = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True
            ).strip()
            subprocess.run(["git", "tag", "v1.2.3"], cwd=root, check=True)

            manifest.write_text("modified\n", encoding="utf-8")
            with self.assertRaisesRegex(package_release.ReleaseError, "working tree is dirty"):
                package_release.verify_release_source_binding(root, "v1.2.3", revision)

            manifest.write_text("tracked\n", encoding="utf-8")
            untracked = package / "untracked.frag"
            untracked.write_text("untracked\n", encoding="utf-8")
            with self.assertRaisesRegex(package_release.ReleaseError, "working tree is dirty"):
                package_release.verify_release_source_binding(root, "v1.2.3", revision)

            untracked.unlink()
            output = root / "dist" / "generated.zip"
            output.parent.mkdir()
            output.write_bytes(b"output")
            self.assertEqual(
                package_release.verify_release_source_binding(root, "v1.2.3", revision),
                revision,
            )


class VerifyRepositoryToolTests(unittest.TestCase):
    def test_public_documentation_matches_checked_source_counts(self) -> None:
        self.assertEqual(verify_repository._source_test_count(), 162)
        verify_repository._check_public_documentation()

    def test_native_artifact_rejects_symlink_before_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "native" / "effect.tox"

            def is_symlink(path: Path) -> bool:
                return path == artifact

            with mock.patch.object(verify_repository, "ROOT", root), mock.patch.object(
                Path, "is_symlink", autospec=True, side_effect=is_symlink
            ):
                with self.assertRaisesRegex(
                    verify_repository.VerificationError, "missing or unsafe"
                ):
                    verify_repository._resolve_native_artifact("native/effect.tox")


class BuildGalleryToolTests(unittest.TestCase):
    def test_load_and_render_gallery_are_stable_and_category_grouped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_tool_manifest(root, "tdimagefx.zeta.second", name="Second", category="zeta")
            _write_tool_manifest(
                root,
                "tdimagefx.alpha.first",
                name="First",
                category="alpha",
                processing={
                    "model": "multi_pass",
                    "gpu_cost": "high",
                    "capabilities": ["multi_pass"],
                    "passes": ["shaders/effect.frag", "shaders/pass2.frag"],
                    "history_frames": 0,
                },
            )
            _write_tool_manifest(
                root,
                "tdimagefx.alpha.first",
                name="First",
                category="alpha",
                version="1.1.0",
                processing={
                    "model": "multi_pass",
                    "gpu_cost": "high",
                    "capabilities": ["multi_pass"],
                    "passes": ["shaders/effect.frag", "shaders/pass2.frag"],
                    "history_frames": 0,
                },
            )
            (root / "packages" / "tdimagefx.alpha.first" / "1.1.0" / "shaders" / "pass2.frag").write_text(
                "// second pass\n", encoding="utf-8", newline="\n"
            )
            with mock.patch.object(build_gallery, "ROOT", root):
                entries = build_gallery.load_entries()
            markdown = build_gallery.render_markdown(entries)

            self.assertEqual([entry["id"] for entry in entries], [
                "tdimagefx.alpha.first",
                "tdimagefx.zeta.second",
            ])
            self.assertEqual(entries[0]["processing_model"], "multi_pass")
            self.assertEqual(entries[0]["version"], "1.1.0")
            self.assertEqual(entries[1]["processing_model"], "single_pass")
            self.assertEqual(entries[0]["parameters"], ["Enable", "Wet Mix"])
            self.assertIn("Current catalog: **2 effects** across **2 categories**.", markdown)
            self.assertLess(markdown.index("## Alpha"), markdown.index("## Zeta"))

    def test_main_generates_then_detects_stale_gallery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_tool_manifest(root, "tdimagefx.test.gallery", name="Gallery", category="test")
            markdown_path = root / "generated" / "gallery.md"
            json_path = root / "generated" / "gallery.json"

            def run(*extra: str) -> int:
                argv = [
                    "build_gallery.py",
                    "--markdown",
                    str(markdown_path),
                    "--json",
                    str(json_path),
                    *extra,
                ]
                with mock.patch.object(build_gallery, "ROOT", root), mock.patch.object(sys, "argv", argv):
                    with contextlib.redirect_stdout(io.StringIO()):
                        return build_gallery.main()

            self.assertEqual(run(), 0)
            self.assertEqual(run("--check"), 0)
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual([item["id"] for item in payload["effects"]], ["tdimagefx.test.gallery"])

            markdown_path.write_text("stale\n", encoding="utf-8")
            self.assertEqual(run("--check"), 1)


if __name__ == "__main__":
    unittest.main()
