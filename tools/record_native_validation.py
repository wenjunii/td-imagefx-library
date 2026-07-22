"""Record a successful TouchDesigner build and hash every native artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tdimagefx import Version
DEFAULT_REPORT = ROOT / "build" / "touchdesigner-build-report.json"
DEFAULT_OUTPUT = ROOT / "docs" / "native-validation.json"
CORE_ASSETS = (
    "touchdesigner/core/TDImageFXLibrary.tox",
    "touchdesigner/core/FxBrowser.tox",
    "touchdesigner/core/FxRack.tox",
    "touchdesigner/core/ParticleRandomMove.tox",
    "touchdesigner/core/InkFlowFusion.tox",
    "touchdesigner/core/GlitchFusion.tox",
    "touchdesigner/core/ColorAdjustment.tox",
    "touchdesigner/core/MotionStudio.tox",
    "touchdesigner/core/ReferenceParticleField.tox",
    "touchdesigner/core/CalligraphicShadow.tox",
    "touchdesigner/core/InkOrbitCanvas.tox",
    "touchdesigner/core/FxUpdater.tox",
)
BUILDER_SOURCE = "touchdesigner/scripts/build_project.py"


class NativeValidationError(RuntimeError):
    """The native build report or one of its artifacts is not releasable."""


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise NativeValidationError(f"Cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise NativeValidationError(f"Expected a JSON object in {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def native_artifact_paths(root: Path) -> list[Path]:
    paths = [root / "TD_ImageFX_Library.toe", *(root / path for path in CORE_ASSETS)]
    paths.extend(sorted((root / "packages").glob("*/*/tox/*.tox")))
    return paths


def _latest_manifest_identities(root: Path) -> set[tuple[str, str]]:
    latest: dict[str, tuple[Version, str]] = {}
    for path in sorted((root / "packages").glob("*/*/package.json")):
        manifest = _read_json(path)
        package_id = manifest.get("id")
        version = manifest.get("version")
        if not isinstance(package_id, str) or not isinstance(version, str):
            raise NativeValidationError(f"Manifest identity is missing in {path}")
        if path.parent.parent.name != package_id or path.parent.name != version:
            raise NativeValidationError(f"Manifest path does not match its identity: {path}")
        try:
            parsed = Version.parse(version)
        except Exception as exc:
            raise NativeValidationError(f"Manifest version is invalid in {path}: {exc}") from exc
        current = latest.get(package_id)
        if current is None or current[0] < parsed:
            latest[package_id] = (parsed, version)
    if not latest:
        raise NativeValidationError("Repository contains no package manifests")
    return {(package_id, item[1]) for package_id, item in latest.items()}


def build_record(root: Path, report_path: Path) -> dict:
    report = _read_json(report_path)
    if report.get("schema_version") != 1:
        raise NativeValidationError("TouchDesigner build report must use schema_version 1")
    for field in ("errors", "shader_errors", "preview_errors"):
        value = report.get(field)
        if not isinstance(value, (list, dict)) or value:
            raise NativeValidationError(f"TouchDesigner build report contains {field}")
    effects = report.get("effects")
    if not isinstance(effects, list) or not effects:
        raise NativeValidationError("TouchDesigner build report contains no effects")
    identities = {
        (item.get("id"), item.get("version"))
        for item in effects
        if isinstance(item, dict)
    }
    if len(identities) != len(effects) or any(
        not isinstance(package_id, str) or not isinstance(version, str)
        for package_id, version in identities
    ):
        raise NativeValidationError("TouchDesigner build report has invalid or duplicate effect identities")

    expected_identities = _latest_manifest_identities(root)
    if identities != expected_identities:
        missing = sorted(expected_identities - identities)
        extra = sorted(identities - expected_identities)
        raise NativeValidationError(
            "TouchDesigner build report is not bound to the latest manifest identities "
            f"(missing={missing}, extra={extra})"
        )
    valid_tox_actions = {"created", "rebuilt_unpublished", "preserved_published"}
    if any(item.get("tox_action") not in valid_tox_actions for item in effects):
        raise NativeValidationError("TouchDesigner build report lacks a valid tox_action for an effect")

    builder = report.get("builder")
    builder_path = root / BUILDER_SOURCE
    if (
        not isinstance(builder, dict)
        or builder.get("path") != BUILDER_SOURCE
        or builder.get("sha256") != _sha256(builder_path)
    ):
        raise NativeValidationError("TouchDesigner build report does not match the current builder source")

    manifests = sorted((root / "packages").glob("*/*/package.json"))
    artifacts = []
    for path in native_artifact_paths(root):
        if path.is_symlink() or not path.is_file():
            raise NativeValidationError(f"Missing or unsafe native artifact: {path}")
        artifacts.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )

    benchmark_path = root / "docs" / "benchmark-data.json"
    benchmark = _read_json(benchmark_path)
    return {
        "schema_version": 1,
        "generated_at": report.get("generated_at"),
        "library_version": report.get("library_version"),
        "touchdesigner": {
            "version": report.get("touchdesigner_version"),
            "build": report.get("touchdesigner_build"),
            "os": report.get("touchdesigner_os"),
            "architecture": report.get("touchdesigner_architecture"),
        },
        "builder": {
            "path": BUILDER_SOURCE,
            "sha256": _sha256(builder_path),
        },
        "catalog": {
            "current_effects": len(effects),
            "package_versions": len(manifests),
        },
        "results": {
            "builder_errors": 0,
            "shader_errors": 0,
            "preview_errors": 0,
        },
        "benchmark": {
            "resolution": benchmark.get("resolution"),
            "frames_per_sample": benchmark.get("frames_per_sample"),
            "gpu": benchmark.get("gpu"),
        },
        "artifacts": artifacts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    record = build_record(ROOT, args.report.resolve())
    content = json.dumps(record, indent=2) + "\n"
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != content:
            print(f"Native validation record is stale: {args.output}")
            return 1
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8", newline="\n")
    print(
        "Native validation records "
        f"{record['catalog']['current_effects']} current effects and {len(record['artifacts'])} artifacts"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
