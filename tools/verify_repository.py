"""Run the repository checks used locally and by GitHub Actions.

This script has no third-party dependencies. Run it from any working directory:

    python tools/verify_repository.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "packages"
PUBLIC_FEED = ROOT / "registry" / "update-feed.json"
LOCAL_FEED = ROOT / "registry" / "update-feed.local.json"
PUBLIC_FEED_URL = (
    "https://raw.githubusercontent.com/wenjunii/td-imagefx-library/"
    "main/registry/update-feed.json"
)


class VerificationError(RuntimeError):
    """A repository invariant failed."""


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise VerificationError(f"Cannot read JSON from {path.relative_to(ROOT)}: {exc}") from exc


def _extract_assignment(path: Path, name: str) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"^{re.escape(name)}\s*=\s*[\"']([^\"']+)[\"']", text, re.MULTILINE)
    if match is None:
        raise VerificationError(f"Cannot find {name} in {path.relative_to(ROOT)}")
    return match.group(1)


def _check_versions() -> str:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    versions = {
        "pyproject.toml": str(project["version"]),
        "src/tdimagefx/__init__.py": _extract_assignment(ROOT / "src" / "tdimagefx" / "__init__.py", "__version__"),
        "touchdesigner/scripts/build_project.py": _extract_assignment(
            ROOT / "touchdesigner" / "scripts" / "build_project.py", "LIBRARY_VERSION"
        ),
    }
    if len(set(versions.values())) != 1:
        details = ", ".join(f"{path}={version}" for path, version in versions.items())
        raise VerificationError(f"Library version mismatch: {details}")
    return next(iter(versions.values()))


def _check_manifests() -> int:
    manifest_paths = sorted(PACKAGE_ROOT.glob("*/*/package.json"))
    if not manifest_paths:
        raise VerificationError("No package manifests found")

    seen: set[tuple[str, str]] = set()
    for manifest_path in manifest_paths:
        data = _read_json(manifest_path)
        package_id = str(data.get("id", ""))
        version = str(data.get("version", ""))
        identity = (package_id, version)
        if not package_id or not version:
            raise VerificationError(f"Missing id or version in {manifest_path.relative_to(ROOT)}")
        if identity in seen:
            raise VerificationError(f"Duplicate package identity: {package_id}@{version}")
        seen.add(identity)

        package_dir = manifest_path.parent.resolve()
        expected_dir = (PACKAGE_ROOT / package_id / version).resolve()
        if package_dir != expected_dir:
            raise VerificationError(
                f"Package path mismatch for {package_id}@{version}: "
                f"expected {expected_dir.relative_to(ROOT)}, found {package_dir.relative_to(ROOT)}"
            )

        entrypoints = data.get("entrypoints")
        if not isinstance(entrypoints, dict) or not entrypoints:
            raise VerificationError(f"No entrypoints declared by {manifest_path.relative_to(ROOT)}")
        for entrypoint_name, relative_path in entrypoints.items():
            if not isinstance(relative_path, str) or not relative_path:
                raise VerificationError(f"Invalid {entrypoint_name} entrypoint in {manifest_path.relative_to(ROOT)}")
            candidate = (package_dir / relative_path).resolve()
            try:
                candidate.relative_to(package_dir)
            except ValueError as exc:
                raise VerificationError(
                    f"Entrypoint escapes its package: {manifest_path.relative_to(ROOT)} -> {relative_path}"
                ) from exc
            if not candidate.is_file():
                raise VerificationError(
                    f"Missing {entrypoint_name} entrypoint: {candidate.relative_to(ROOT)}"
                )

    required_native_assets = (
        ROOT / "TD_ImageFX_Library.toe",
        ROOT / "touchdesigner" / "core" / "TDImageFXLibrary.tox",
        ROOT / "touchdesigner" / "core" / "FxRack.tox",
        ROOT / "touchdesigner" / "core" / "FxUpdater.tox",
    )
    missing = [path.relative_to(ROOT) for path in required_native_assets if not path.is_file()]
    if missing:
        raise VerificationError("Missing native assets: " + ", ".join(map(str, missing)))
    return len(manifest_paths)


def _check_update_sources() -> None:
    config = _read_json(ROOT / "config" / "update_sources.json")
    sources = config.get("sources")
    if not isinstance(sources, list):
        raise VerificationError("config/update_sources.json must contain a sources list")
    sources_by_id = {
        source.get("id"): source
        for source in sources
        if isinstance(source, dict) and isinstance(source.get("id"), str)
    }
    public_feed = _read_json(PUBLIC_FEED)
    public_source = sources_by_id.get(public_feed.get("feed_id"))
    if public_source is None:
        raise VerificationError("Public feed is not declared in config/update_sources.json")
    if (
        public_source.get("url") != PUBLIC_FEED_URL
        or public_source.get("enabled") is not True
        or public_source.get("trust") != "first_party"
    ):
        raise VerificationError("Public feed source must use the canonical HTTPS URL and be enabled")
    if public_source.get("auto_stage") is not False or public_source.get("auto_activate") is not False:
        raise VerificationError("Public feed must remain notification-only")

    local_feed = _read_json(LOCAL_FEED)
    local_source = sources_by_id.get(local_feed.get("feed_id"))
    if (
        local_source is None
        or local_source.get("url") != "registry/update-feed.local.json"
        or local_source.get("enabled") is not False
    ):
        raise VerificationError("Bundled local feed is not declared correctly")


def _run(label: str, arguments: list[str], env: dict[str, str]) -> None:
    print(f"\n[verify] {label}", flush=True)
    subprocess.run(arguments, cwd=ROOT, env=env, check=True)


def main() -> int:
    if sys.version_info < (3, 11):
        print("[verify] Python 3.11 or newer is required", file=sys.stderr)
        return 1

    try:
        version = _check_versions()
        package_count = _check_manifests()
        for feed_path in (PUBLIC_FEED, LOCAL_FEED):
            if not feed_path.is_file():
                raise VerificationError(f"Missing update feed: {feed_path.relative_to(ROOT)}")
        _check_update_sources()

        env = os.environ.copy()
        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = os.pathsep.join(
            part for part in (str(ROOT / "src"), existing_pythonpath) if part
        )
        python = sys.executable
        _run(
            "Compile Python sources",
            [python, "-m", "compileall", "-q", "src", "tests", "tools", "touchdesigner"],
            env,
        )
        _run("Run unit tests", [python, "-m", "unittest", "discover", "-s", "tests", "-v"], env)
        _run(
            "Validate package manifests",
            [python, "-m", "tdimagefx", "validate", "packages", "--type", "package"],
            env,
        )
        for feed_path in (PUBLIC_FEED, LOCAL_FEED):
            _run(
                f"Validate {feed_path.relative_to(ROOT)}",
                [python, "-m", "tdimagefx", "validate", str(feed_path), "--type", "feed"],
                env,
            )
    except (OSError, VerificationError, subprocess.CalledProcessError) as exc:
        print(f"\n[verify] FAILED: {exc}", file=sys.stderr)
        return 1

    print(f"\n[verify] PASS: TD ImageFX {version}, {package_count} packages, 2 feeds", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
