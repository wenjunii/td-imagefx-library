"""Create deterministic package ZIPs and an update feed for a GitHub Release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
FIXED_ZIP_TIME = (2020, 1, 1, 0, 0, 0)
CHANNEL_ORDER = {"stable": 0, "beta": 1, "experimental": 2}
PUBLIC_CATALOG_FEED_ID = "tdimagefx.github.catalog"
_RELEASE_SOURCE_PATHS = (
    "packages",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "src/tdimagefx",
    "tools/package_release.py",
)

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tdimagefx import PackageManifest, Version, load_manifest  # noqa: E402
from tdimagefx.errors import ImageFxError, SecurityError  # noqa: E402
from tdimagefx.paths import validate_package_path  # noqa: E402
from tdimagefx.registry import UpdateFeed  # noqa: E402


class ReleaseError(RuntimeError):
    """A package cannot be released without violating repository boundaries."""


_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_RELEASE_TAG_RE = re.compile(
    r"^v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(path))


def _confined(path: Path, root: Path, *, label: str) -> Path:
    candidate = _absolute(path)
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise ReleaseError(f"{label} escapes release output root {root}: {candidate}") from exc
    cursor = root
    if cursor.is_symlink():
        raise ReleaseError(f"Release output root may not be a symbolic link: {cursor}")
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ReleaseError(f"{label} may not contain symbolic links: {cursor}")
    return candidate


def _atomic_write(path: Path, payload: bytes, *, root: Path) -> None:
    target = _confined(path, root, label="release output")
    target.parent.mkdir(parents=True, exist_ok=True)
    _confined(target.parent, root, label="release output directory")
    if target.is_symlink():
        raise ReleaseError(f"Release output may not be a symbolic link: {target}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def verify_release_source_binding(
    repository_root: Path,
    release_tag: str,
    source_revision: str,
) -> str:
    """Require an exact release tag and source revision to resolve to one commit."""

    if _RELEASE_TAG_RE.fullmatch(release_tag) is None:
        raise ReleaseError(f"Release tag must be an exact v-prefixed SemVer: {release_tag!r}")
    if re.fullmatch(r"[0-9a-fA-F]{40,64}", source_revision) is None:
        raise ReleaseError("source revision must be a full 40-64 character hexadecimal digest")
    root = repository_root.resolve()

    def resolve_commit(revision: str, label: str) -> str:
        process = subprocess.run(
            ["git", "rev-parse", "--verify", f"{revision}^{{commit}}"],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if process.returncode:
            detail = process.stderr.strip()[:500]
            raise ReleaseError(f"Cannot resolve {label} to a Git commit: {detail}")
        commit = process.stdout.strip().lower()
        if re.fullmatch(r"[0-9a-f]{40,64}", commit) is None:
            raise ReleaseError(f"Git returned an invalid commit identity for {label}")
        return commit

    tag_commit = resolve_commit(f"refs/tags/{release_tag}", "release tag")
    revision_commit = resolve_commit(source_revision, "source revision")
    if tag_commit != revision_commit:
        raise ReleaseError(
            f"Release tag {release_tag} resolves to {tag_commit}, not source revision {revision_commit}"
        )

    status = subprocess.run(
        [
            "git",
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
            "--ignore-submodules=none",
            "--",
            *_RELEASE_SOURCE_PATHS,
        ],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if status.returncode:
        detail = status.stderr.decode("utf-8", errors="replace").strip()[:500]
        raise ReleaseError(f"Cannot inspect release source working tree: {detail}")
    if status.stdout:
        raise ReleaseError(
            "Release source working tree is dirty; commit or restore all package, legal, "
            "and release-tool inputs before enabling Git source binding"
        )
    return tag_commit


def _load_package_manifest(path: Path) -> PackageManifest:
    try:
        return load_manifest(path)
    except ImageFxError as exc:
        raise ReleaseError(f"Invalid package manifest {path}: {exc}") from exc


def _timestamp(value: str | None) -> str:
    if value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ReleaseError("generated_at must be an RFC 3339 date-time") from exc
        if parsed.tzinfo is None:
            raise ReleaseError("generated_at must include an explicit timezone")
    elif epoch := os.environ.get("SOURCE_DATE_EPOCH"):
        try:
            parsed = datetime.fromtimestamp(int(epoch), timezone.utc)
        except (OverflowError, ValueError) as exc:
            raise ReleaseError("SOURCE_DATE_EPOCH must be a supported integer timestamp") from exc
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
    provenance = manifest.provenance or {}
    if provenance.get("changelog") is not None:
        declared.add(provenance["changelog"])
    declared.update(provenance.get("examples") or ())
    declared.update(provenance.get("presets") or ())

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
    destination = _absolute(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise ReleaseError(f"Release artifact may not be a symbolic link: {destination}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for relative, source in assets:
                info = zipfile.ZipInfo(relative, FIXED_ZIP_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                info.create_system = 3
                archive.writestr(info, source.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        with temporary.open("r+b") as handle:
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _artifact_path(output_root: Path, artifact_name: str) -> Path:
    if Path(artifact_name).name != artifact_name or any(separator in artifact_name for separator in ("/", "\\")):
        raise ReleaseError(f"Unsafe artifact filename: {artifact_name!r}")
    candidate = _absolute(output_root / artifact_name)
    canonical_root = output_root.resolve()
    canonical_candidate = candidate.resolve()
    try:
        canonical_candidate.relative_to(canonical_root)
    except ValueError as exc:
        raise ReleaseError(f"Artifact path escapes output directory: {artifact_name!r}") from exc
    return candidate


def _build_release_in_place(
    output_dir: Path,
    feed_path: Path,
    *,
    release_tag: str,
    generated_at: str,
    repository: str,
    source_revision: str | None = None,
) -> dict:
    generated_at = _timestamp(generated_at)
    if _RELEASE_TAG_RE.fullmatch(release_tag) is None:
        raise ReleaseError(f"Release tag must be an exact v-prefixed SemVer: {release_tag!r}")
    if _REPOSITORY_RE.fullmatch(repository) is None:
        raise ReleaseError(f"Repository must have owner/name form: {repository!r}")
    resolved_revision = source_revision or os.environ.get("GITHUB_SHA") or "unrecorded"
    if resolved_revision != "unrecorded" and re.fullmatch(r"[0-9a-fA-F]{40,64}", resolved_revision) is None:
        raise ReleaseError("source revision must be a full 40-64 character hexadecimal digest")
    selected: dict[str, tuple[Version, PackageManifest, Path]] = {}
    identity_metadata: dict[str, tuple[str, str]] = {}
    packages_root = (ROOT / "packages").resolve()
    output_root = _absolute(output_dir)
    release_root = output_root.parent
    release_root.mkdir(parents=True, exist_ok=True)
    _confined(output_root, release_root, label="package output directory")
    feed_target = _confined(feed_path, release_root, label="update feed")
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
        artifact_path = _confined(
            _artifact_path(output_root, artifact_name),
            release_root,
            label="release artifact",
        )
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
    feed_channel = max(
        (package["releases"][0]["channel"] for package in packages),
        key=CHANNEL_ORDER.__getitem__,
        default="stable",
    )
    feed = {
        "schema_version": 1,
        "feed_id": PUBLIC_CATALOG_FEED_ID,
        "generated_at": generated_at,
        # This is the highest maturity level represented in the feed. Clients
        # still apply their configured channel when selecting candidates.
        "channel": feed_channel,
        "packages": packages,
        "signature": None,
    }
    try:
        UpdateFeed.from_data(feed)
    except ImageFxError as exc:
        raise ReleaseError(f"Generated update feed is invalid: {exc}") from exc
    feed_payload = (json.dumps(feed, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    _atomic_write(feed_target, feed_payload, root=release_root)

    artifact_records = []
    for package in packages:
        artifact_name = package["releases"][0]["artifacts"][0]["url"].rsplit("/", 1)[-1]
        artifact_path = _confined(output_root / artifact_name, release_root, label="release artifact")
        artifact_records.append(
            {
                "path": artifact_path.relative_to(release_root).as_posix(),
                "sha256": sha256_file(artifact_path),
                "size_bytes": artifact_path.stat().st_size,
            }
        )
    artifact_records.append(
        {
            "path": feed_target.relative_to(release_root).as_posix(),
            "sha256": sha256_file(feed_target),
            "size_bytes": feed_target.stat().st_size,
        }
    )
    provenance = {
        "schema_version": 1,
        "builder": "tools/package_release.py",
        "repository": repository,
        "release_tag": release_tag,
        "source_revision": resolved_revision.lower() if resolved_revision != "unrecorded" else resolved_revision,
        "generated_at": generated_at,
        "artifacts": sorted(artifact_records, key=lambda item: item["path"]),
    }
    provenance_target = release_root / "release-provenance.json"
    _atomic_write(
        provenance_target,
        (json.dumps(provenance, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"),
        root=release_root,
    )
    checksum_records = [
        *artifact_records,
        {
            "path": provenance_target.relative_to(release_root).as_posix(),
            "sha256": sha256_file(provenance_target),
            "size_bytes": provenance_target.stat().st_size,
        },
    ]
    checksums = "".join(
        f"{item['sha256']}  {item['path']}\n"
        for item in sorted(checksum_records, key=lambda item: item["path"])
    )
    _atomic_write(release_root / "SHA256SUMS", checksums.encode("ascii"), root=release_root)
    return feed


def build_release(
    output_dir: Path,
    feed_path: Path,
    *,
    release_tag: str,
    generated_at: str,
    repository: str,
    source_revision: str | None = None,
    verify_source_binding: bool = False,
) -> dict:
    """Build a complete release in a sibling transaction and expose it atomically."""

    if verify_source_binding:
        if source_revision is None:
            raise ReleaseError("source revision is required when Git source binding is enabled")
        verify_release_source_binding(ROOT, release_tag, source_revision)

    requested_output = _absolute(output_dir)
    requested_root = requested_output.parent
    requested_feed = _absolute(feed_path)
    try:
        output_relative = requested_output.relative_to(requested_root)
        feed_relative = requested_feed.relative_to(requested_root)
    except ValueError as exc:
        raise ReleaseError(
            f"Update feed escapes release output root {requested_root}: {requested_feed}"
        ) from exc
    if requested_root.exists() or requested_root.is_symlink():
        raise ReleaseError(
            f"Release output root already exists; choose an empty destination: {requested_root}"
        )
    requested_root.parent.mkdir(parents=True, exist_ok=True)
    if requested_root.parent.is_symlink():
        raise ReleaseError(f"Release output parent may not be a symbolic link: {requested_root.parent}")
    staging_root = Path(
        tempfile.mkdtemp(
            prefix=f".{requested_root.name}.",
            suffix=".stage",
            dir=requested_root.parent,
        )
    )
    try:
        feed = _build_release_in_place(
            staging_root / output_relative,
            staging_root / feed_relative,
            release_tag=release_tag,
            generated_at=generated_at,
            repository=repository,
            source_revision=source_revision,
        )
        try:
            staging_root.rename(requested_root)
        except FileExistsError as exc:
            raise ReleaseError(f"Release output root appeared during build: {requested_root}") from exc
        staging_root = None
        return feed
    finally:
        if staging_root is not None:
            shutil.rmtree(staging_root, ignore_errors=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "packages")
    parser.add_argument("--feed", type=Path, default=ROOT / "dist" / "update-feed.json")
    parser.add_argument("--release-tag", default="v0.3.0")
    parser.add_argument("--repository", default="wenjunii/td-imagefx-library")
    parser.add_argument("--generated-at", help="ISO-8601 timestamp; defaults to now or SOURCE_DATE_EPOCH")
    parser.add_argument("--source-revision", help="source commit recorded in release provenance")
    parser.add_argument(
        "--verify-source-binding",
        action="store_true",
        help="require --release-tag and --source-revision to resolve to the same Git commit",
    )
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
        source_revision=args.source_revision,
        verify_source_binding=args.verify_source_binding,
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
