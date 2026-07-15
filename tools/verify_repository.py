"""Run the repository checks used locally and by GitHub Actions.

This script has no third-party dependencies. Run it from any working directory:

    python tools/verify_repository.py
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
PACKAGE_ROOT = ROOT / "packages"
PUBLIC_FEED = ROOT / "registry" / "update-feed.json"
LOCAL_FEED = ROOT / "registry" / "update-feed.local.json"
EXPECTED_EFFECT_ID_COUNT = 66
EXPECTED_PACKAGE_VERSION_COUNT = 78
PUBLIC_FEED_URL = (
    "https://raw.githubusercontent.com/wenjunii/td-imagefx-library/"
    "main/registry/update-feed.json"
)

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tdimagefx import Version, load_manifest  # noqa: E402
from tdimagefx.errors import ImageFxError, SecurityError  # noqa: E402
from tdimagefx.paths import validate_package_path  # noqa: E402


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


def _require_package_file(
    package_dir: Path,
    relative_path: str,
    *,
    label: str,
    manifest_path: Path,
) -> Path:
    try:
        safe_path = validate_package_path(relative_path, label=label)
    except SecurityError as exc:
        raise VerificationError(f"{manifest_path.relative_to(ROOT)}: {exc}") from exc
    candidate = package_dir.joinpath(*safe_path.parts).resolve()
    try:
        candidate.relative_to(package_dir)
    except ValueError as exc:
        raise VerificationError(
            f"{label} escapes its package: {manifest_path.relative_to(ROOT)} -> {relative_path}"
        ) from exc
    if not candidate.is_file():
        raise VerificationError(f"Missing {label}: {candidate.relative_to(ROOT)}")
    return candidate


def _check_manifests() -> tuple[int, set[str], dict[str, str]]:
    manifest_paths = sorted(PACKAGE_ROOT.glob("*/*/package.json"))
    if not manifest_paths:
        raise VerificationError("No package manifests found")

    seen: set[tuple[str, str]] = set()
    package_ids: set[str] = set()
    latest: dict[str, Version] = {}
    for manifest_path in manifest_paths:
        try:
            manifest = load_manifest(manifest_path)
        except ImageFxError as exc:
            raise VerificationError(
                f"Invalid package manifest {manifest_path.relative_to(ROOT)}: {exc}"
            ) from exc
        package_id = manifest.id
        version = str(manifest.version)
        identity = (package_id, version)
        if identity in seen:
            raise VerificationError(f"Duplicate package identity: {package_id}@{version}")
        seen.add(identity)
        package_ids.add(package_id)
        current = latest.get(package_id)
        if (
            current is not None
            and manifest.version == current
            and not manifest.version.exactly_equals(current)
        ):
            raise VerificationError(
                f"Ambiguous versions with equal SemVer precedence for {package_id}: "
                f"{current} and {manifest.version}"
            )
        if current is None or current < manifest.version:
            latest[package_id] = manifest.version

        package_dir = manifest_path.parent.resolve()
        try:
            package_dir.relative_to(PACKAGE_ROOT.resolve())
        except ValueError as exc:
            raise VerificationError(
                f"Package directory escapes packages/: {manifest_path.relative_to(ROOT)}"
            ) from exc
        expected_dir = (PACKAGE_ROOT / package_id / version).resolve()
        if package_dir != expected_dir:
            raise VerificationError(
                f"Package path mismatch for {package_id}@{version}: "
                f"expected {expected_dir.relative_to(ROOT)}, found {package_dir.relative_to(ROOT)}"
            )

        for entrypoint_name, relative_path in manifest.entrypoints.items():
            if relative_path is None:
                continue
            _require_package_file(
                package_dir,
                relative_path,
                label=f"{entrypoint_name} entrypoint",
                manifest_path=manifest_path,
            )

        passes = manifest.processing.get("passes")
        if passes is not None:
            for index, relative_path in enumerate(passes):
                _require_package_file(
                    package_dir,
                    relative_path,
                    label=f"processing pass {index + 1}",
                    manifest_path=manifest_path,
                )

    if (
        len(manifest_paths) != EXPECTED_PACKAGE_VERSION_COUNT
        or len(package_ids) != EXPECTED_EFFECT_ID_COUNT
    ):
        raise VerificationError(
            "Completed v0.2 catalog must contain exactly "
            f"{EXPECTED_EFFECT_ID_COUNT} effect IDs and {EXPECTED_PACKAGE_VERSION_COUNT} immutable versions; "
            f"found {len(manifest_paths)} manifests for {len(package_ids)} effect IDs"
        )

    required_native_assets = (
        ROOT / "TD_ImageFX_Library.toe",
        ROOT / "touchdesigner" / "core" / "TDImageFXLibrary.tox",
        ROOT / "touchdesigner" / "core" / "FxBrowser.tox",
        ROOT / "touchdesigner" / "core" / "FxRack.tox",
        ROOT / "touchdesigner" / "core" / "FxUpdater.tox",
    )
    missing = [path.relative_to(ROOT) for path in required_native_assets if not path.is_file()]
    if missing:
        raise VerificationError("Missing native assets: " + ", ".join(map(str, missing)))
    return len(manifest_paths), package_ids, {
        package_id: str(version) for package_id, version in latest.items()
    }


def _item_ids(items: object, *, label: str) -> list[str]:
    if not isinstance(items, list):
        raise VerificationError(f"{label} must be a list")
    identifiers: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
            raise VerificationError(f"{label}[{index}] must contain a non-empty id")
        identifiers.append(item["id"])
    if len(identifiers) != len(set(identifiers)):
        raise VerificationError(f"{label} contains duplicate package ids")
    return identifiers


def _check_generated_artifacts(package_ids: set[str], latest_versions: dict[str, str]) -> None:
    generated_files = (
        ROOT / "docs" / "gallery.md",
        ROOT / "docs" / "gallery.json",
        ROOT / "docs" / "gallery-baselines.json",
        ROOT / "docs" / "benchmark-data.json",
        ROOT / "docs" / "benchmarks.md",
    )
    missing = [path.relative_to(ROOT) for path in generated_files if not path.is_file()]
    if missing:
        raise VerificationError("Missing generated documentation: " + ", ".join(map(str, missing)))

    gallery = _read_json(ROOT / "docs" / "gallery.json")
    if gallery.get("schema_version") != 1:
        raise VerificationError("docs/gallery.json must use schema_version 1")
    gallery_ids = _item_ids(gallery.get("effects"), label="docs/gallery.json effects")
    if set(gallery_ids) != package_ids or len(gallery_ids) != EXPECTED_EFFECT_ID_COUNT:
        raise VerificationError("docs/gallery.json must contain every catalog package exactly once")
    gallery_versions = {
        item.get("id"): item.get("version")
        for item in gallery.get("effects", [])
        if isinstance(item, dict)
    }
    if gallery_versions != latest_versions:
        raise VerificationError("docs/gallery.json must describe the latest version of every effect")

    expected_previews = {f"{package_id}.png" for package_id in package_ids}
    gallery_dir = ROOT / "docs" / "gallery"
    actual_previews = {path.name for path in gallery_dir.glob("*.png") if path.is_file()}
    if actual_previews != expected_previews:
        missing_previews = sorted(expected_previews - actual_previews)
        extra_previews = sorted(actual_previews - expected_previews)
        raise VerificationError(
            f"Gallery previews do not match catalog: missing={missing_previews}, extra={extra_previews}"
        )

    baselines = _read_json(ROOT / "docs" / "gallery-baselines.json")
    images = baselines.get("images")
    if (
        baselines.get("schema_version") != 1
        or baselines.get("algorithm") != "sha256"
        or not isinstance(images, dict)
        or set(images) != expected_previews
        or any(
            not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None
            for value in images.values()
        )
    ):
        raise VerificationError("docs/gallery-baselines.json must contain one SHA-256 baseline per preview")

    benchmark_data = _read_json(ROOT / "docs" / "benchmark-data.json")
    if benchmark_data.get("schema_version") != 1:
        raise VerificationError("docs/benchmark-data.json must use schema_version 1")
    benchmark_ids = _item_ids(benchmark_data.get("samples"), label="docs/benchmark-data.json samples")
    if set(benchmark_ids) != package_ids or len(benchmark_ids) != EXPECTED_EFFECT_ID_COUNT:
        raise VerificationError("docs/benchmark-data.json must contain one unique sample per catalog package")
    benchmark_versions = {
        item.get("id"): item.get("version")
        for item in benchmark_data.get("samples", [])
        if isinstance(item, dict)
    }
    if benchmark_versions != latest_versions:
        raise VerificationError("docs/benchmark-data.json must measure the latest version of every effect")
    measured = False
    for index, sample in enumerate(benchmark_data["samples"]):
        gpu_ms = sample.get("gpu_ms")
        cpu_ms = sample.get("cpu_submission_ms")
        memory = sample.get("gpu_memory_bytes")
        passes = sample.get("passes")
        if gpu_ms is not None and (
            isinstance(gpu_ms, bool) or not isinstance(gpu_ms, (int, float))
            or not math.isfinite(gpu_ms) or gpu_ms < 0
        ):
            raise VerificationError(f"benchmark sample {index} has invalid gpu_ms")
        if (
            isinstance(cpu_ms, bool) or not isinstance(cpu_ms, (int, float))
            or not math.isfinite(cpu_ms) or cpu_ms < 0
        ):
            raise VerificationError(f"benchmark sample {index} has invalid cpu_submission_ms")
        if isinstance(memory, bool) or not isinstance(memory, int) or memory < 0:
            raise VerificationError(f"benchmark sample {index} has invalid gpu_memory_bytes")
        if isinstance(passes, bool) or not isinstance(passes, int) or passes < 1:
            raise VerificationError(f"benchmark sample {index} has invalid pass count")
        measured = measured or gpu_ms is not None or cpu_ms > 0 or memory > 0
    if not measured:
        raise VerificationError("benchmark data contains no runtime measurement")


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
        package_version_count, package_ids, latest_versions = _check_manifests()
        for feed_path in (PUBLIC_FEED, LOCAL_FEED):
            if not feed_path.is_file():
                raise VerificationError(f"Missing update feed: {feed_path.relative_to(ROOT)}")
        _check_update_sources()
        _check_generated_artifacts(package_ids, latest_versions)

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
        _run(
            "Check generated effect gallery",
            [python, "tools/build_gallery.py", "--check"],
            env,
        )
        _run(
            "Check gallery visual baselines",
            [python, "tools/check_gallery.py"],
            env,
        )
        _run(
            "Check generated benchmark report",
            [python, "tools/benchmark_report.py", "--check"],
            env,
        )
    except (OSError, VerificationError, subprocess.CalledProcessError) as exc:
        print(f"\n[verify] FAILED: {exc}", file=sys.stderr)
        return 1

    print(
        f"\n[verify] PASS: TD ImageFX {version}, {len(package_ids)} effect IDs / "
        f"{package_version_count} immutable versions, "
        "2 feeds, gallery and benchmarks",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
