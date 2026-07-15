from __future__ import annotations

import unittest

from tdimagefx.errors import ValidationError
from tdimagefx.semver import Version, VersionSpec


class VersionTests(unittest.TestCase):
    def test_semver_precedence_chain(self) -> None:
        values = [
            "1.0.0-alpha",
            "1.0.0-alpha.1",
            "1.0.0-alpha.beta",
            "1.0.0-beta",
            "1.0.0-beta.2",
            "1.0.0-beta.11",
            "1.0.0-rc.1",
            "1.0.0",
        ]
        versions = [Version.parse(value) for value in values]
        self.assertEqual(versions, sorted(reversed(versions)))

    def test_build_metadata_does_not_change_precedence_but_is_exact(self) -> None:
        left = Version.parse("1.2.3+gpu1")
        right = Version.parse("1.2.3+gpu2")
        self.assertEqual(left, right)
        self.assertFalse(left.exactly_equals(right))

    def test_rejects_invalid_versions(self) -> None:
        for value in ("1", "1.2", "01.2.3", "1.02.3", "1.2.03", "1.0.0-01", "v1.0.0", "1.0.0+"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                Version.parse(value)

    def test_constraints(self) -> None:
        self.assertTrue(VersionSpec.parse(">=1.2.0,<2.0.0").matches("1.9.9"))
        self.assertFalse(VersionSpec.parse(">=1.2.0,<2.0.0").matches("2.0.0"))
        self.assertTrue(VersionSpec.parse("^0.2.3").matches("0.2.9"))
        self.assertFalse(VersionSpec.parse("^0.2.3").matches("0.3.0"))
        self.assertTrue(VersionSpec.parse("~1.4.2").matches("1.4.99"))
        self.assertFalse(VersionSpec.parse("~1.4.2").matches("1.5.0"))


if __name__ == "__main__":
    unittest.main()
