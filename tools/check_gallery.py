"""Verify or update exact SHA-256 baselines for TouchDesigner preview PNGs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GALLERY = ROOT / "docs" / "gallery"
BASELINES = ROOT / "docs" / "gallery-baselines.json"


def current_hashes() -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(GALLERY.glob("*.png"))
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true", help="Replace baselines with current preview hashes")
    args = parser.parse_args()
    hashes = current_hashes()
    if args.update:
        BASELINES.parent.mkdir(parents=True, exist_ok=True)
        BASELINES.write_text(
            json.dumps({"schema_version": 1, "algorithm": "sha256", "images": hashes}, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"Updated {len(hashes)} gallery baselines")
        return 0
    if not BASELINES.is_file():
        print("Missing docs/gallery-baselines.json; run with --update after rendering previews")
        return 1
    baseline = json.loads(BASELINES.read_text(encoding="utf-8"))
    expected = baseline.get("images")
    if expected != hashes:
        missing = sorted(set(expected or {}) - set(hashes))
        added = sorted(set(hashes) - set(expected or {}))
        changed = sorted(name for name in set(hashes) & set(expected or {}) if hashes[name] != expected[name])
        print(f"Gallery regression: missing={missing}, added={added}, changed={changed}")
        return 1
    print(f"Verified {len(hashes)} gallery baselines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
