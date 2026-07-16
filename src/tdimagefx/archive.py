"""Defensive ZIP staging into an immutable package store."""

from __future__ import annotations

import hashlib
import math
import os
import shutil
import stat
import tempfile
import time
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from .errors import SecurityError, StateError, ValidationError
from .feed import DEFAULT_ARTIFACT_LIMIT, SourcePolicy, download_source, redact_source_url
from .jsonutil import atomic_write_json
from .manifest import PACKAGE_ID_RE, PackageManifest, is_sha256, load_manifest
from .paths import is_relative_to, validate_package_path
from .registry import InstalledVersion, LocalRegistry, load_local_registry, save_local_registry, utc_now
from .semver import Version


_INSTALL_METADATA = ".tdimagefx_install.json"
_RETAINED_ARTIFACT = ".tdimagefx_artifact.zip"
_RESERVED_PACKAGE_FILES = {_INSTALL_METADATA.casefold(), _RETAINED_ARTIFACT.casefold()}
_REGISTRY_LOCK_TIMEOUT_SECONDS = 30.0


def _acquire_registry_lock(descriptor: int, lock_path: Path) -> None:
    """Acquire one byte of an advisory lock file on Windows or POSIX."""

    deadline = time.monotonic() + _REGISTRY_LOCK_TIMEOUT_SECONDS
    if os.name == "nt":
        import msvcrt

        while True:
            try:
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                return
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise StateError(f"timed out waiting for package registry lock {lock_path}") from exc
                time.sleep(0.05)
    else:
        import fcntl

        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except BlockingIOError as exc:
                if time.monotonic() >= deadline:
                    raise StateError(f"timed out waiting for package registry lock {lock_path}") from exc
                time.sleep(0.05)


def _release_registry_lock(descriptor: int) -> None:
    if os.name == "nt":
        import msvcrt

        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(descriptor, fcntl.LOCK_UN)


@contextmanager
def _registry_transaction(registry_path: Path) -> Iterator[None]:
    """Serialize registry read/install/write transactions across processes.

    The lock file is intentionally retained. Removing an advisory-lock file can
    create two independently locked inodes when another process is waiting on it.
    """

    registry_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = registry_path.with_name(f".{registry_path.name}.lock")
    if lock_path.is_symlink():
        raise SecurityError(f"package registry lock may not be a symbolic link: {lock_path}")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise StateError(f"could not open package registry lock {lock_path}: {exc}") from exc
    acquired = False
    try:
        if lock_path.is_symlink() or not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise SecurityError(f"package registry lock must be a regular file: {lock_path}")
        _acquire_registry_lock(descriptor, lock_path)
        acquired = True
        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"\0")
            os.fsync(descriptor)
        yield
    finally:
        if acquired:
            try:
                _release_registry_lock(descriptor)
            finally:
                os.close(descriptor)
        else:
            os.close(descriptor)


@dataclass(frozen=True, slots=True)
class StageLimits:
    max_archive_bytes: int = DEFAULT_ARTIFACT_LIMIT
    max_files: int = 4096
    max_uncompressed_bytes: int = 1024 * 1024 * 1024
    max_file_bytes: int = 256 * 1024 * 1024
    max_compression_ratio: float = 200.0

    def validate(self) -> None:
        for name in ("max_archive_bytes", "max_files", "max_uncompressed_bytes", "max_file_bytes"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValidationError("Invalid staging limits", [f"{name} must be a positive integer"])
        if not isinstance(self.max_compression_ratio, (int, float)) or isinstance(
            self.max_compression_ratio, bool
        ) or not math.isfinite(self.max_compression_ratio) or self.max_compression_ratio <= 0:
            raise ValidationError(
                "Invalid staging limits",
                ["max_compression_ratio must be a positive number"],
            )


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

    # Keep this asset set aligned with tools/package_release.py. The artifact
    # digest authenticates the archive bytes, but every path the manifest says
    # belongs to the package must also resolve to an extracted regular file.
    declared_assets: list[tuple[str, str]] = []
    for name, relative_path in manifest.entrypoints.items():
        if relative_path is None:
            continue
        declared_assets.append((f"entrypoint {name!r}", relative_path))
    declared_assets.extend(
        (f"processing pass {index}", relative_path)
        for index, relative_path in enumerate(manifest.processing.get("passes") or ())
    )
    provenance = manifest.provenance or {}
    changelog = provenance.get("changelog")
    if changelog is not None:
        declared_assets.append(("provenance changelog", changelog))
    declared_assets.extend(
        (f"provenance example {index}", relative_path)
        for index, relative_path in enumerate(provenance.get("examples") or ())
    )
    declared_assets.extend(
        (f"provenance preset {index}", relative_path)
        for index, relative_path in enumerate(provenance.get("presets") or ())
    )

    for label, relative_path in declared_assets:
        path = validate_package_path(relative_path, label=label)
        candidate = root.joinpath(*path.parts)
        if not candidate.is_file():
            raise ValidationError(
                "Staged package is invalid",
                [f"declared {label} does not exist: {relative_path}"],
            )
    return manifest, manifest_path


def stage_package(
    source: str | os.PathLike[str],
    package_store: str | os.PathLike[str],
    *,
    expected_sha256: str,
    expected_size: int | None = None,
    expected_id: str | None = None,
    expected_version: str | Version | None = None,
    expected_manifest_sha256: str | None = None,
    policy: SourcePolicy = SourcePolicy(),
    limits: StageLimits = StageLimits(),
    registry_path: str | os.PathLike[str] | None = None,
    feed_url: str | None = None,
    feed_id: str | None = None,
    feed_sha256: str | None = None,
) -> StageResult:
    """Verify and stage a ZIP into ``<store>/<id>/<exact-version>``.

    Package contents are never imported or executed. Existing version directories
    are never overwritten, even when their bytes appear identical.
    """

    limits.validate()
    if not is_sha256(expected_sha256):
        raise ValidationError(
            "Invalid staging trust metadata",
            ["expected_sha256 must be a non-empty SHA-256 digest"],
        )
    for label, digest in (
        ("expected_manifest_sha256", expected_manifest_sha256),
        ("feed_sha256", feed_sha256),
    ):
        if digest is not None and not is_sha256(digest):
            raise ValidationError("Invalid staging trust metadata", [f"{label} must be a SHA-256 digest"])
    if expected_id is not None and (
        not isinstance(expected_id, str) or PACKAGE_ID_RE.fullmatch(expected_id) is None
    ):
        raise ValidationError("Invalid staging trust metadata", ["expected_id is invalid"])
    if expected_version is not None and not isinstance(expected_version, (str, Version)):
        raise ValidationError(
            "Invalid staging trust metadata",
            ["expected_version must be an exact semantic version"],
        )
    if isinstance(expected_version, str):
        expected_version = Version.parse(expected_version)
    if feed_url is not None:
        missing = [
            name
            for name, value in (
                ("expected_id", expected_id),
                ("expected_version", expected_version),
                ("expected_manifest_sha256", expected_manifest_sha256),
                ("feed_id", feed_id),
                ("feed_sha256", feed_sha256),
            )
            if value is None
        ]
        if missing:
            raise SecurityError(
                "feed-sourced staging requires bound " + ", ".join(missing)
            )
        if not isinstance(feed_url, str) or len(feed_url) > 4096:
            raise SecurityError("feed_url must be a bounded HTTPS or local file URL")
        parsed_feed_url = urlsplit(feed_url)
        if parsed_feed_url.scheme.lower() == "https":
            if not parsed_feed_url.hostname or parsed_feed_url.username or parsed_feed_url.password:
                raise SecurityError("feed_url must not contain credentials")
        elif parsed_feed_url.scheme.lower() == "file":
            if (
                parsed_feed_url.netloc not in {"", "localhost"}
                or parsed_feed_url.query
                or parsed_feed_url.fragment
            ):
                raise SecurityError("feed_url must refer to a local file")
        else:
            raise SecurityError("feed_url must use HTTPS or file")
    if feed_id is not None and (
        not isinstance(feed_id, str) or PACKAGE_ID_RE.fullmatch(feed_id) is None
    ):
        raise ValidationError("Invalid staging trust metadata", ["feed_id is invalid"])

    store = Path(package_store).resolve()
    store.mkdir(parents=True, exist_ok=True)
    downloads = store / ".downloads"
    if downloads.is_symlink():
        raise SecurityError("package download directory may not be a symbolic link")
    downloads.mkdir(exist_ok=True)
    if not is_relative_to(downloads.resolve(strict=True), store):
        raise SecurityError("package download directory escapes the package store")
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
        if (
            expected_manifest_sha256 is not None
            and manifest_sha256 != expected_manifest_sha256.lower()
        ):
            raise SecurityError(
                "manifest SHA-256 mismatch: expected "
                f"{expected_manifest_sha256.lower()}, got {manifest_sha256}"
            )
        package_content_sha256 = content_sha256(extraction_root)
        if archive_content_sha256(archive_path, limits) != package_content_sha256:
            raise SecurityError("extracted package content does not match the verified archive")
        final_path = store / manifest.id / str(manifest.version)
        final_manifest = final_path / "package.json"
        registry_file = (
            Path(registry_path).resolve()
            if registry_path is not None
            else store / "registry.json"
        )
        source_type = "feed" if feed_url is not None else "local"
        source_record: dict[str, object] = {
            "type": source_type,
            "artifact_url": redact_source_url(fetch.final_source),
        }
        if feed_url is not None:
            source_record.update(
                {
                    "feed_url": redact_source_url(feed_url),
                    "feed_id": feed_id,
                    "feed_sha256": feed_sha256.lower() if feed_sha256 else None,
                }
            )
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
        with _registry_transaction(registry_file):
            if final_path.exists():
                raise StateError(f"immutable package directory already exists: {final_path}")
            if final_path.parent.is_symlink():
                raise SecurityError(
                    f"package identity directory may not be a symbolic link: {final_path.parent}"
                )
            final_path.parent.mkdir(parents=True, exist_ok=True)
            if not is_relative_to(final_path.parent.resolve(strict=True), store):
                raise SecurityError("package identity directory escapes the package store")

            registry = (
                load_local_registry(registry_file)
                if registry_file.exists()
                else LocalRegistry.empty(store)
            )
            if Path(registry.library_root).resolve() != store:
                raise StateError(
                    f"registry library_root {registry.library_root} does not match package store {store}"
                )
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
            updated_registry = registry.add(manifest.id, installed)
            # Validate the complete registry before making the package directory visible.
            updated_registry = LocalRegistry.from_data(updated_registry.to_dict())

            try:
                extraction_root.rename(final_path)
            except FileExistsError as exc:
                raise StateError(f"immutable package directory already exists: {final_path}") from exc
            extraction_root = None
            try:
                save_local_registry(registry_file, updated_registry)
            except BaseException:
                # The directory was created by this call and was already confined to store.
                shutil.rmtree(final_path, ignore_errors=True)
                raise
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
