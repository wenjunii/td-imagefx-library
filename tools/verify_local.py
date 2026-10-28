"""Run the local-first safety gate without fetching, installing or publishing.

Use Python 3.11+ with requirements-test.txt installed. The default history base
is the locally cached origin/main; --base accepts an existing local Git ref/SHA.
"""

from __future__ import annotations

import argparse
import importlib
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        default="origin/main",
        help="locally available immutable-history baseline (default: origin/main)",
    )
    args = parser.parse_args(argv)
    if not args.base.strip() or args.base.startswith("-"):
        parser.error("--base must be a nonempty Git ref or commit, not an option")
    if sys.version_info < (3, 11):
        print("[local] Python 3.11 or newer is required.", file=sys.stderr)
        return 2
    try:
        importlib.import_module("numpy")
    except (ImportError, OSError) as exc:
        print(
            "[local] NumPy could not be loaded. Install requirements-test.txt "
            "with this Python interpreter before running the full safety gate. "
            f"({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2

    commands = (
        (
            "Check immutable history (including uncommitted package changes)",
            [sys.executable, "tools/check_immutable_history.py", "--base", args.base],
        ),
        (
            "Verify repository; compilation, credential scan and unit tests run once",
            [sys.executable, "tools/verify_repository.py"],
        ),
    )
    try:
        for label, command in commands:
            print(f"\n[local] {label}", flush=True)
            subprocess.run(command, cwd=ROOT, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"\n[local] FAILED: {exc}", file=sys.stderr)
        print(
            "[local] No fetch or repair was attempted. If the baseline is absent, "
            "choose an existing --base or fetch explicitly when online.",
            file=sys.stderr,
        )
        return 1

    print(
        "\n[local] PASS: portable safety gate. Native rendering, CUDA, cameras "
        "and venue outputs still require their separate rehearsal checks.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
