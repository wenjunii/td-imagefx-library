"""Convert an existing local 2D observation cache; never upload media."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "touchdesigner/scripts"))
from dance_backdrop_motion import convert_observations, read_document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("observations", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--video", type=Path, help="Optional original video: record a local content hash")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Destination exists; choose a new file (no automatic overwrite)")
    doc = convert_observations(read_document(args.observations))
    if args.video:
        digest = hashlib.sha256()
        with args.video.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        doc["source_video_sha256"] = digest.hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(doc, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    print(f"Prepared {len(doc['frames'])} frames at {doc['fps']} fps; local cache: {args.output}")


if __name__ == "__main__":
    main()
