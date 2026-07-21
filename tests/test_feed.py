from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tdimagefx.errors import FeedError, SecurityError, ValidationError
from tdimagefx.feed import SourcePolicy, download_source, fetch_bytes, load_update_feed

from tests.helpers import feed_data


class FeedFetchingTests(unittest.TestCase):
    def test_file_access_is_explicit_and_hash_checked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "payload.bin"
            source.write_bytes(b"trusted")
            digest = hashlib.sha256(b"trusted").hexdigest()
            with self.assertRaises(SecurityError):
                fetch_bytes(source)
            payload, result = fetch_bytes(
                source,
                policy=SourcePolicy(allow_file=True, file_root=root),
                expected_sha256=digest,
            )
        self.assertEqual(payload, b"trusted")
        self.assertEqual(result.sha256, digest)

    def test_local_source_cannot_escape_allowed_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            outside_file = Path(outside, "feed.json")
            outside_file.write_text("{}", encoding="utf-8")
            with self.assertRaises(SecurityError):
                fetch_bytes(outside_file, policy=SourcePolicy(allow_file=True, file_root=Path(directory)))

    def test_hash_and_size_mismatch_leave_no_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "payload.bin"
            destination = root / "destination.bin"
            source.write_bytes(b"payload")
            with self.assertRaises(SecurityError):
                download_source(
                    source,
                    destination,
                    policy=SourcePolicy(allow_file=True),
                    expected_sha256="0" * 64,
                )
            self.assertFalse(destination.exists())
            with self.assertRaises(SecurityError):
                download_source(
                    source,
                    destination,
                    policy=SourcePolicy(allow_file=True),
                    expected_size=99,
                )
            self.assertFalse(destination.exists())

    def test_empty_expected_hash_is_invalid_not_optional(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "payload.bin"
            destination = root / "destination.bin"
            source.write_bytes(b"payload")
            with self.assertRaisesRegex(ValidationError, "digest is invalid"):
                download_source(
                    source,
                    destination,
                    policy=SourcePolicy(allow_file=True),
                    expected_sha256="",
                )
            self.assertFalse(destination.exists())

    def test_http_is_never_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(SecurityError):
                download_source("http://example.test/feed.json", Path(directory, "out"))

    def test_valid_local_feed_and_feed_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = feed_data("https://example.test/effect.zip", "b" * 64, 20)
            source = root / "feed.json"
            source.write_text(json.dumps(data), encoding="utf-8")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            feed, result = load_update_feed(
                source,
                policy=SourcePolicy(allow_file=True, file_root=root),
                expected_sha256=digest,
            )
        self.assertEqual(feed.feed_id, "tdimagefx.test.feed")
        self.assertEqual(result.sha256, digest)

    def test_invalid_feed_is_wrapped_as_feed_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory, "feed.json")
            source.write_text("{}", encoding="utf-8")
            with self.assertRaises(FeedError):
                load_update_feed(source, policy=SourcePolicy(allow_file=True))


if __name__ == "__main__":
    unittest.main()
