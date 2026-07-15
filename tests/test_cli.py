from __future__ import annotations

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tdimagefx.cli import main

from tests.helpers import feed_data, manifest_data, write_package_zip


def invoke(arguments: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        result = main(arguments)
    return result, stdout.getvalue(), stderr.getvalue()


class CliTests(unittest.TestCase):
    def test_validate_and_catalog_and_check(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "package.json"
            manifest_path.write_text(json.dumps(manifest_data()), encoding="utf-8")
            code, output, error = invoke(["validate", str(manifest_path), "--json"])
            self.assertEqual(code, 0, error)
            self.assertIn("tdimagefx.test.effect", output)

            artifact = root / "effect.zip"
            digest, _ = write_package_zip(artifact, version="1.1.0")
            feed_path = root / "feed.json"
            feed_path.write_text(json.dumps(feed_data(artifact.as_uri(), digest, artifact.stat().st_size)), encoding="utf-8")
            feed_hash = hashlib.sha256(feed_path.read_bytes()).hexdigest()
            code, output, error = invoke(
                ["catalog", str(feed_path), "--allow-file", "--file-root", str(root), "--feed-sha256", feed_hash, "--json"]
            )
            self.assertEqual(code, 0, error)
            self.assertIn("1.1.0", output)
            code, output, error = invoke(
                [
                    "check", str(feed_path), "--allow-file", "--file-root", str(root), "--feed-sha256", feed_hash,
                    "--os", "windows", "--architecture", "x86_64", "--touchdesigner-build", "2023.1", "--json",
                ]
            )
            self.assertEqual(code, 0, error)
            self.assertIn('"count": 1', output)

    def test_stage_activate_upgrade_and_rollback_commands(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = root / "packages"
            state = root / "active-state.json"
            hashes: dict[str, str] = {}
            for version in ("1.0.0", "2.0.0"):
                artifact = root / f"effect-{version}.zip"
                digest, _ = write_package_zip(artifact, version=version)
                hashes[version] = digest
                code, output, error = invoke(
                    [
                        "stage", str(artifact), "--store", str(store), "--sha256", digest,
                        "--id", "tdimagefx.test.effect", "--package-version", version,
                        "--allow-file", "--file-root", str(root), "--json",
                    ]
                )
                self.assertEqual(code, 0, error)
                self.assertIn(version, output)
            for version in ("1.0.0", "2.0.0"):
                code, output, error = invoke(
                    [
                        "activate", "tdimagefx.test.effect", version, "--store", str(store), "--state", str(state),
                        "--sha256", hashes[version], "--os", "windows", "--architecture", "x86_64",
                        "--touchdesigner-build", "2023.1", "--json",
                    ]
                )
                self.assertEqual(code, 0, error)
            code, output, error = invoke(
                ["rollback", "tdimagefx.test.effect", "--store", str(store), "--state", str(state), "--json"]
            )
            self.assertEqual(code, 0, error)
            self.assertIn("1.0.0", output)

    def test_expected_errors_have_nonzero_exit(self) -> None:
        code, _, error = invoke(["catalog", "http://example.test/feed.json"])
        self.assertEqual(code, 2)
        self.assertIn("HTTPS", error)


if __name__ == "__main__":
    unittest.main()
