"""Create deterministic package ZIPs and an update feed for a GitHub Release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
FIXED_ZIP_TIME = (2020, 1, 1, 0, 0, 0)

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tdimagefx import PackageManifest, Version, load_manifest  # noqa: E402
from tdimagefx.errors import ImageFxError, SecurityError  # noqa: E402
from tdimagefx.paths import validate_package_path  # noqa: E402


class ReleaseError(RuntimeError):
    """A package cannot be released without violating repository boundaries."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _load_package_manifest(path: Path) -> PackageManifest:
    try:
        return load_manifest(path)
    except ImageFxError as exc:
        raise ReleaseError(f"Invalid package manifest {path}: {exc}") from exc


def _timestamp(value: str | None) -> str:
    if value:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    elif epoch := os.environ.get("SOURCE_DATE_EPOCH"):
        parsed = datetime.fromtimestamp(int(epoch), timezone.utc)
    else:
        parsed = datetime.now(timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _declared_package_assets(
    package_root: Path,
    manifest: PackageManifest,
) -> list[tuple[str, Path]]:
    try:
        root = package_root.resolve(strict=True)
    except OSError as exc:
        raise ReleaseError(f"Cannot resolve package root {package_root}: {exc}") from exc
    if not root.is_dir():
        raise ReleaseError(f"Package root is not a directory: {root}")

    declared = {"package.json"}
    declared.update(path for path in manifest.entrypoints.values() if path is not None)
    declared.update(manifest.processing.get("passes") or ())

    assets: list[tuple[str, Path]] = []
    for relative_path in sorted(declared):
        try:
            safe_path = validate_package_path(relative_path, label="declared package asset")
        except SecurityError as exc:
            raise ReleaseError(str(exc)) from exc
        unresolved = root.joinpath(*safe_path.parts)
        cursor = root
        for part in safe_path.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise ReleaseError(f"Declared package asset may not use symbolic links: {relative_path}")
        candidate = unresolved.resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ReleaseError(f"Declared package asset escapes its package: {relative_path}") from exc
        if not candidate.is_file():
            raise ReleaseError(f"Missing declared package asset: {candidate}")
        assets.append((safe_path.as_posix(), candidate))
    return assets


def _distribution_notices() -> list[tuple[str, Path]]:
    root = ROOT.resolve()
    notices = []
    for filename in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        unresolved = ROOT / filename
        if unresolved.is_symlink():
            raise ReleaseError(f"Distribution notice may not be a symbolic link: {filename}")
        try:
            source = unresolved.resolve(strict=True)
            source.relative_to(root)
        except (OSError, ValueError) as exc:
            raise ReleaseError(f"Missing or unsafe distribution notice: {filename}") from exc
        if not source.is_file():
            raise ReleaseError(f"Distribution notice is not a regular file: {filename}")
        notices.append((filename, source))
    return notices


def package_zip(
    package_root: Path,
    destination: Path,
    *,
    manifest: PackageManifest | None = None,
) -> None:
    package_root = package_root.resolve()
    manifest = manifest or _load_package_manifest(package_root / "package.json")
    assets = sorted(
        [*_distribution_notices(), *_declared_package_assets(package_root, manifest)],
        key=lambda item: item[0],
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for relative, source in assets:
                info = zipfile.ZipInfo(relative, FIXED_ZIP_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                info.create_system = 3
                archive.writestr(info, source.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _artifact_path(output_root: Path, artifact_name: str) -> Path:
    if Path(artifact_name).name != artifact_name or any(separator in artifact_name for separator in ("/", "\\")):
        raise ReleaseError(f"Unsafe artifact filename: {artifact_name!r}")
    candidate = (output_root / artifact_name).resolve()
    try:
        candidate.relative_to(output_root)
    except ValueError as exc:
        raise ReleaseError(f"Artifact path escapes output directory: {artifact_name!r}") from exc
    return candidate


def build_release(
    output_dir: Path,
    feed_path: Path,
    *,
    release_tag: str,
    generated_at: str,
    repository: str,
) -> dict:
    selected: dict[str, tuple[Version, PackageManifest, Path]] = {}
    identity_metadata: dict[str, tuple[str, str]] = {}
    packages_root = (ROOT / "packages").resolve()
    output_root = output_dir.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    release_base = f"https://github.com/{repository}/releases/download/{release_tag}"
    raw_base = f"https://raw.githubusercontent.com/{repository}/{release_tag}"
    seen: set[tuple[str, str]] = set()
    for manifest_path in sorted((ROOT / "packages").glob("*/*/package.json")):
        resolved_manifest = manifest_path.resolve()
        try:
            resolved_manifest.relative_to(packages_root)
        except ValueError as exc:
            raise ReleaseError(f"Manifest escapes packages directory: {manifest_path}") from exc
        manifest = _load_package_manifest(resolved_manifest)
        version = str(manifest.version)
        identity = (manifest.id, version)
        if identity in seen:
            raise ReleaseError(f"Duplicate package identity: {manifest.id}@{version}")
        seen.add(identity)
        package_root = resolved_manifest.parent
        expected_root = (packages_root / manifest.id / version).resolve()
        if package_root != expected_root:
            raise ReleaseError(
                f"Package path mismatch for {manifest.id}@{version}: expected {expected_root}, found {package_root}"
            )
        metadata = (manifest.name, manifest.kind)
        if manifest.id in identity_metadata and identity_metadata[manifest.id] != metadata:
            raise ReleaseError(f"Package identity metadata changed across versions for {manifest.id}")
        identity_metadata[manifest.id] = metadata
        current = selected.get(manifest.id)
        if (
            current is not None
            and manifest.version == current[0]
            and not manifest.version.exactly_equals(current[0])
        ):
            raise ReleaseError(
                f"Ambiguous versions with equal SemVer precedence for {manifest.id}: "
                f"{current[0]} and {manifest.version}"
            )
        if current is None or current[0] < manifest.version:
            selected[manifest.id] = (manifest.version, manifest, resolved_manifest)

    packages = []
    for package_id in sorted(selected):
        _parsed_version, manifest, resolved_manifest = selected[package_id]
        version = str(manifest.version)
        package_root = resolved_manifest.parent
        artifact_name = f"{manifest.id}-{version}.zip"
        artifact_path = _artifact_path(output_root, artifact_name)
        package_zip(package_root, artifact_path, manifest=manifest)
        manifest_relative = resolved_manifest.relative_to(ROOT).as_posix()
        packages.append({
            "id": manifest.id,
            "name": manifest.name,
            "kind": manifest.kind,
            "releases": [{
                "version": version,
                "channel": manifest.channel,
                "published_at": generated_at,
                "manifest_url": f"{raw_base}/{manifest_relative}",
                "manifest_sha256": sha256_file(resolved_manifest),
                "artifacts": [{
                    "url": f"{release_base}/{artifact_name}",
                    "sha256": sha256_file(artifact_path),
                    "size_bytes": artifact_path.stat().st_size,
                    "media_type": "application/zip",
                    "os": manifest.compatibility["os"],
                    "architectures": manifest.compatibility["architectures"],
                    "signature": None,
                }],
                "compatibility": manifest.compatibility,
                "requires_restart": bool(manifest.permissions.get("native_code")),
                "yanked": False,
                "changelog": f"TD ImageFX {release_tag} package release.",
                "permissions_changed": False,
            }],
        })
    feed = {
        "schema_version": 1,
        "feed_id": "tdimagefx.github.stable",
        "generated_at": generated_at,
        "channel": "stable",
        "packages": packages,
        "signature": None,
    }
    feed_path.parent.mkdir(parents=True, exist_ok=True)
    feed_path.write_text(json.dumps(feed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return feed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "packages")
    parser.add_argument("--feed", type=Path, default=ROOT / "dist" / "update-feed.json")
    parser.add_argument("--release-tag", default="v0.2.0")
    parser.add_argument("--repository", default="wenjunii/td-imagefx-library")
    parser.add_argument("--generated-at", help="ISO-8601 timestamp; defaults to now or SOURCE_DATE_EPOCH")
    return parser


def main() -> int:
    args = _parser().parse_args()
    generated_at = _timestamp(args.generated_at)
    feed = build_release(
        args.output.resolve(),
        args.feed.resolve(),
        release_tag=args.release_tag,
        generated_at=generated_at,
        repository=args.repository,
    )
    version_count = sum(len(package["releases"]) for package in feed["packages"])
    print(
        f"Packaged {len(feed['packages'])} package IDs / {version_count} versions "
        f"in {args.output.resolve()}"
    )
    print(f"Feed: {args.feed.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
