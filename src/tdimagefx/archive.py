"""Defensive ZIP staging into an immutable package store."""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .errors import SecurityError, StateError, ValidationError
from .feed import DEFAULT_ARTIFACT_LIMIT, SourcePolicy, download_source, redact_source_url
from .jsonutil import atomic_write_json
from .manifest import PackageManifest, load_manifest
from .paths import is_relative_to, validate_package_path
from .registry import InstalledVersion, LocalRegistry, load_local_registry, save_local_registry, utc_now
from .semver import Version


_INSTALL_METADATA = ".tdimagefx_install.json"
_RETAINED_ARTIFACT = ".tdimagefx_artifact.zip"
_RESERVED_PACKAGE_FILES = {_INSTALL_METADATA.casefold(), _RETAINED_ARTIFACT.casefold()}

@dataclass(frozen=True, slots=True)
class StageLimits:
    max_archive_bytes: int = DEFAULT_ARTIFACT_LIMIT
    max_files: int = 4096
    max_uncompressed_bytes: int = 1024 * 1024 * 1024
    max_file_bytes: int = 256 * 1024 * 1024
    max_compression_ratio: float = 200.0


@dataclass(frozen=True, slots=True)
class StageResult:
    package_id: str
    version: Version
    install_path: Path
    manifest_path: Path
    artifact_sha256: str
    manifest_sha256: str
    content_sha256: str
    size_bytes: int
    file_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.package_id,
            "version": str(self.version),
            "install_path": str(self.install_path),
            "manifest_path": str(self.manifest_path),
            "artifact_sha256": self.artifact_sha256,
            "manifest_sha256": self.manifest_sha256,
            "content_sha256": self.content_sha256,
            "size_bytes": self.size_bytes,
            "file_count": self.file_count,
        }


def sha256_file(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def content_sha256(root: str | os.PathLike[str]) -> str:
    """Hash package paths and bytes, excluding the generated install metadata."""

    package_root = Path(root)
    if package_root.is_symlink() or not package_root.is_dir():
        raise SecurityError("package content root must be a real directory")
    records: list[tuple[str, Path]] = []
    for directory, directory_names, file_names in os.walk(package_root, topdown=True, followlinks=False):
        directory_path = Path(directory)
        directory_names.sort()
        file_names.sort()
        for name in directory_names:
            candidate = directory_path / name
            if candidate.is_symlink():
                raise SecurityError(f"package content contains a symbolic-link directory: {candidate}")
        for name in file_names:
            candidate = directory_path / name
            relative = candidate.relative_to(package_root).as_posix()
            if relative.casefold() in _RESERVED_PACKAGE_FILES:
                continue
            mode = candidate.lstat().st_mode
            if not stat.S_ISREG(mode):
                raise SecurityError(f"package content contains a non-regular file: {candidate}")
            records.append((relative, candidate))
    digest = hashlib.sha256()
    for relative, candidate in sorted(records):
        file_digest = bytes.fromhex(sha256_file(candidate))
        _add_content_record(digest, relative, candidate.stat().st_size, file_digest)
    return digest.hexdigest()


def _add_content_record(digest: "hashlib._Hash", relative: str, size: int, file_digest: bytes) -> None:
    path_bytes = relative.encode("utf-8")
    digest.update(len(path_bytes).to_bytes(4, "big"))
    digest.update(path_bytes)
    digest.update(size.to_bytes(8, "big"))
    digest.update(file_digest)


@dataclass(frozen=True, slots=True)
class _ArchiveMember:
    info: zipfile.ZipInfo
    path: PurePosixPath
    is_directory: bool


def _member_type(info: zipfile.ZipInfo) -> int:
    return stat.S_IFMT((info.external_attr >> 16) & 0xFFFF)


def _preflight(archive: zipfile.ZipFile, limits: StageLimits) -> tuple[_ArchiveMember, ...]:
    infos = archive.infolist()
    if len(infos) > limits.max_files:
        raise SecurityError(f"archive has {len(infos)} entries; maximum is {limits.max_files}")
    members: list[_ArchiveMember] = []
    names: dict[str, _ArchiveMember] = {}
    total_size = 0
    for info in infos:
        if info.flag_bits & 0x1:
            raise SecurityError(f"encrypted ZIP member is not allowed: {info.filename!r}")
        raw_name = info.filename.rstrip("/") if info.is_dir() else info.filename
        path = validate_package_path(raw_name, label="ZIP member")
        if len(path.parts) == 1 and path.name.casefold() in _RESERVED_PACKAGE_FILES:
            raise SecurityError(f"ZIP member uses a reserved package filename: {info.filename!r}")
        mode_type = _member_type(info)
        if mode_type == stat.S_IFLNK:
            raise SecurityError(f"symbolic link is not allowed: {info.filename!r}")
        if mode_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
            raise SecurityError(f"special filesystem member is not allowed: {info.filename!r}")
        is_directory = info.is_dir() or mode_type == stat.S_IFDIR
        if is_directory and (info.file_size or info.compress_size):
            raise SecurityError(f"directory member has payload data: {info.filename!r}")
        if info.file_size < 0 or info.compress_size < 0:
            raise SecurityError(f"member has invalid size: {info.filename!r}")
        if info.file_size > limits.max_file_bytes:
            raise SecurityError(f"member exceeds per-file size limit: {info.filename!r}")
        total_size += info.file_size
        if total_size > limits.max_uncompressed_bytes:
            raise SecurityError("archive exceeds total uncompressed-size limit")
        if not is_directory and info.file_size >= 1024 * 1024:
            if info.compress_size == 0 or info.file_size / info.compress_size > limits.max_compression_ratio:
                raise SecurityError(f"member exceeds compression-ratio limit: {info.filename!r}")
        collision_key = "/".join(part.casefold() for part in path.parts)
        if collision_key in names:
            raise SecurityError(f"duplicate or case-colliding ZIP member: {info.filename!r}")
        member = _ArchiveMember(info, path, is_directory)
        names[collision_key] = member
        members.append(member)

    for member in members:
        canonical_parts = tuple(part.casefold() for part in member.path.parts)
        for index in range(1, len(canonical_parts)):
            parent_key = "/".join(canonical_parts[:index])
            parent_member = names.get(parent_key)
            if parent_member is not None and not parent_member.is_directory:
                raise SecurityError(f"file/directory path conflict below {parent_member.path}")
        if not member.is_directory:
            prefix = "/".join(canonical_parts) + "/"
            if any(
                other_key.startswith(prefix)
                for other_key in names
            ):
                raise SecurityError(f"file/directory path conflict at {member.path}")
    return tuple(members)


def archive_content_sha256(path: str | os.PathLike[str], limits: StageLimits = StageLimits()) -> str:
    """Hash the canonical uncompressed file set of a safely structured ZIP."""

    try:
        archive = zipfile.ZipFile(path, "r")
    except (zipfile.BadZipFile, OSError) as exc:
        raise SecurityError(f"artifact is not a valid ZIP archive: {exc}") from exc
    with archive:
        members = _preflight(archive, limits)
        digest = hashlib.sha256()
        for member in sorted((item for item in members if not item.is_directory), key=lambda item: item.path.as_posix()):
            file_digest = hashlib.sha256()
            actual_size = 0
            try:
                with archive.open(member.info, "r") as input_file:
                    while chunk := input_file.read(1024 * 1024):
                        actual_size += len(chunk)
                        if actual_size > member.info.file_size or actual_size > limits.max_file_bytes:
                            raise SecurityError(f"member expanded beyond declared size: {member.info.filename!r}")
                        file_digest.update(chunk)
            except (zipfile.BadZipFile, EOFError, RuntimeError, OSError) as exc:
                raise SecurityError(f"could not verify ZIP member {member.info.filename!r}: {exc}") from exc
            if actual_size != member.info.file_size:
                raise SecurityError(f"member size does not match ZIP directory: {member.info.filename!r}")
            _add_content_record(digest, member.path.as_posix(), actual_size, file_digest.digest())
        return digest.hexdigest()


def _extract(archive: zipfile.ZipFile, members: tuple[_ArchiveMember, ...], destination: Path, limits: StageLimits) -> None:
    destination_resolved = destination.resolve()
    actual_total = 0
    for member in members:
        target = destination.joinpath(*member.path.parts)
        resolved_target = target.resolve(strict=False)
        if not is_relative_to(resolved_target, destination_resolved):
            raise SecurityError(f"ZIP member escapes staging directory: {member.info.filename!r}")
        if member.is_directory:
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        member_size = 0
        try:
            with archive.open(member.info, "r") as input_file, target.open("xb") as output_file:
                while chunk := input_file.read(1024 * 1024):
                    member_size += len(chunk)
                    actual_total += len(chunk)
                    if member_size > member.info.file_size or member_size > limits.max_file_bytes:
                        raise SecurityError(f"member expanded beyond declared or permitted size: {member.info.filename!r}")
                    if actual_total > limits.max_uncompressed_bytes:
                        raise SecurityError("archive expanded beyond total uncompressed-size limit")
                    output_file.write(chunk)
        except (zipfile.BadZipFile, EOFError, RuntimeError, OSError) as exc:
            raise SecurityError(f"could not safely extract {member.info.filename!r}: {exc}") from exc
        if member_size != member.info.file_size:
            raise SecurityError(f"member size does not match ZIP directory: {member.info.filename!r}")


def _validate_extracted_package(
    root: Path,
    *,
    expected_id: str | None,
    expected_version: str | Version | None,
) -> tuple[PackageManifest, Path]:
    manifest_path = root / "package.json"
    if not manifest_path.is_file():
        raise ValidationError("Staged package is invalid", ["archive must contain package.json at its root"])
    manifest = load_manifest(manifest_path)
    if expected_id is not None and manifest.id != expected_id:
        raise SecurityError(f"package id mismatch: expected {expected_id}, archive contains {manifest.id}")
    if expected_version is not None:
        required = Version.parse(expected_version) if isinstance(expected_version, str) else expected_version
        if not manifest.version.exactly_equals(required):
            raise SecurityError(f"package version mismatch: expected {required}, archive contains {manifest.version}")
    for name, relative_path in manifest.entrypoints.items():
        if relative_path is None:
            continue
        path = validate_package_path(relative_path, label=f"entrypoint {name}")
        candidate = root.joinpath(*path.parts)
        if not candidate.is_file():
            raise ValidationError("Staged package is invalid", [f"declared entrypoint {name!r} does not exist: {relative_path}"])
    return manifest, manifest_path


def stage_package(
    source: str | os.PathLike[str],
    package_store: str | os.PathLike[str],
    *,
    expected_sha256: str,
    expected_size: int | None = None,
    expected_id: str | None = None,
    expected_version: str | Version | None = None,
    policy: SourcePolicy = SourcePolicy(),
    limits: StageLimits = StageLimits(),
    registry_path: str | os.PathLike[str] | None = None,
    feed_url: str | None = None,
) -> StageResult:
    """Verify and stage a ZIP into ``<store>/<id>/<exact-version>``.

    Package contents are never imported or executed. Existing version directories
    are never overwritten, even when their bytes appear identical.
    """

    store = Path(package_store).resolve()
    store.mkdir(parents=True, exist_ok=True)
    downloads = store / ".downloads"
    downloads.mkdir(exist_ok=True)
    descriptor, archive_name = tempfile.mkstemp(prefix="artifact-", suffix=".zip", dir=downloads)
    os.close(descriptor)
    archive_path = Path(archive_name)
    extraction_root: Path | None = None
    try:
        fetch = download_source(
            source,
            archive_path,
            policy=policy,
            expected_sha256=expected_sha256,
            expected_size=expected_size,
            max_bytes=limits.max_archive_bytes,
        )
        try:
            archive = zipfile.ZipFile(archive_path, "r")
        except (zipfile.BadZipFile, OSError) as exc:
            raise SecurityError(f"artifact is not a valid ZIP archive: {exc}") from exc
        with archive:
            members = _preflight(archive, limits)
            extraction_root = Path(tempfile.mkdtemp(prefix=".stage-", dir=store))
            _extract(archive, members, extraction_root, limits)
        manifest, temporary_manifest_path = _validate_extracted_package(
            extraction_root,
            expected_id=expected_id,
            expected_version=expected_version,
        )
        manifest_sha256 = sha256_file(temporary_manifest_path)
        package_content_sha256 = content_sha256(extraction_root)
        if archive_content_sha256(archive_path, limits) != package_content_sha256:
            raise SecurityError("extracted package content does not match the verified archive")
        final_path = store / manifest.id / str(manifest.version)
        if final_path.exists():
            raise StateError(f"immutable package directory already exists: {final_path}")
        final_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(archive_path, extraction_root / _RETAINED_ARTIFACT)
        metadata = {
            "schema_version": 1,
            "artifact_sha256": fetch.sha256,
            "artifact_file": _RETAINED_ARTIFACT,
            "manifest_sha256": manifest_sha256,
            "content_sha256": package_content_sha256,
            "source": redact_source_url(fetch.final_source),
            "staged_at": utc_now(),
        }
        atomic_write_json(extraction_root / _INSTALL_METADATA, metadata)
        try:
            extraction_root.rename(final_path)
        except FileExistsError as exc:
            raise StateError(f"immutable package directory already exists: {final_path}") from exc
        extraction_root = None
        final_manifest = final_path / "package.json"

        registry_file = Path(registry_path) if registry_path is not None else store / "registry.json"
        registry = load_local_registry(registry_file) if registry_file.exists() else LocalRegistry.empty(store)
        if Path(registry.library_root).resolve() != store:
            raise StateError(f"registry library_root {registry.library_root} does not match package store {store}")
        source_type = "feed" if feed_url is not None else "local"
        source_record: dict[str, object] = {"type": source_type, "artifact_url": redact_source_url(fetch.final_source)}
        if feed_url is not None:
            source_record["feed_url"] = feed_url
        installed = InstalledVersion(
            version=manifest.version,
            install_path=str(final_path),
            manifest_path=str(final_manifest),
            installed_at=utc_now(),
            source=source_record,
            integrity={
                "manifest_sha256": manifest_sha256,
                "artifact_sha256": fetch.sha256,
                "verification": "verified",
            },
            status="staged",
        )
        save_local_registry(registry_file, registry.add(manifest.id, installed))
        return StageResult(
            package_id=manifest.id,
            version=manifest.version,
            install_path=final_path,
            manifest_path=final_manifest,
            artifact_sha256=fetch.sha256,
            manifest_sha256=manifest_sha256,
            content_sha256=package_content_sha256,
            size_bytes=fetch.size_bytes,
            file_count=sum(1 for member in members if not member.is_directory),
        )
    finally:
        archive_path.unlink(missing_ok=True)
        if extraction_root is not None:
            shutil.rmtree(extraction_root, ignore_errors=True)
