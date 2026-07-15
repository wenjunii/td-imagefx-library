"""Atomic active-version selection and one-step rollback."""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterator

from .archive import archive_content_sha256, content_sha256, sha256_file
from .compatibility import RuntimeContext, check_package_compatibility
from .errors import CompatibilityError, StateError, ValidationError
from .jsonutil import atomic_write_json, load_json
from .manifest import PACKAGE_ID_RE, PackageManifest, is_sha256, load_manifest
from .paths import validate_package_path
from .registry import utc_now
from .semver import Version


STATE_SCHEMA_VERSION = 1
_ACTIVE_STATUSES = {"active", "disabled", "error", "pending_restart"}
_PENDING_STATUSES = {"staged", "awaiting_approval", "awaiting_restart", "failed"}
_REASONS = {"install", "update", "rollback", "repair"}


def _is_datetime(value: Any) -> bool:
    from datetime import datetime

    if not isinstance(value, str):
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


@dataclass(frozen=True, slots=True)
class ActivePackage:
    id: str
    version: Version
    previous_version: Version | None
    install_path: str
    manifest_path: str
    entrypoints: dict[str, str | None]
    status: str
    activated_at: str
    restart_required: bool
    last_error: str | None = None

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "ActivePackage":
        return cls(
            id=data["id"],
            version=Version.parse(data["version"]),
            previous_version=Version.parse(data["previous_version"]) if data["previous_version"] else None,
            install_path=data["install_path"],
            manifest_path=data["manifest_path"],
            entrypoints=dict(data["entrypoints"]),
            status=data["status"],
            activated_at=data["activated_at"],
            restart_required=data["restart_required"],
            last_error=data["last_error"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": str(self.version),
            "previous_version": str(self.previous_version) if self.previous_version else None,
            "install_path": self.install_path,
            "manifest_path": self.manifest_path,
            "entrypoints": dict(self.entrypoints),
            "status": self.status,
            "activated_at": self.activated_at,
            "restart_required": self.restart_required,
            "last_error": self.last_error,
        }


@dataclass(frozen=True, slots=True)
class PendingActivation:
    id: str
    from_version: Version | None
    to_version: Version
    staged_path: str
    requested_at: str
    reason: str
    requires_restart: bool
    status: str
    last_error: str | None = None

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "PendingActivation":
        return cls(
            id=data["id"],
            from_version=Version.parse(data["from_version"]) if data["from_version"] else None,
            to_version=Version.parse(data["to_version"]),
            staged_path=data["staged_path"],
            requested_at=data["requested_at"],
            reason=data["reason"],
            requires_restart=data["requires_restart"],
            status=data["status"],
            last_error=data["last_error"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "from_version": str(self.from_version) if self.from_version else None,
            "to_version": str(self.to_version),
            "staged_path": self.staged_path,
            "requested_at": self.requested_at,
            "reason": self.reason,
            "requires_restart": self.requires_restart,
            "status": self.status,
            "last_error": self.last_error,
        }


def _validate_entrypoints(value: Any, path: str, issues: list[str]) -> None:
    if not isinstance(value, dict):
        issues.append(f"{path} must be an object")
        return
    for key in value.keys() - {"shader", "touchdesigner_component", "native_plugin"}:
        issues.append(f"{path}.{key} is not supported")
    for key, entrypoint in value.items():
        if entrypoint is not None and (not isinstance(entrypoint, str) or not entrypoint):
            issues.append(f"{path}.{key} must be null or a non-empty string")


def validate_active_state_data(data: Any) -> list[str]:
    issues: list[str] = []
    if not isinstance(data, dict):
        return ["$ must be an object"]
    required_root = {"schema_version", "updated_at", "revision", "last_good_revision", "active_packages", "pending_activations"}
    for key in data.keys() - required_root:
        issues.append(f"$.{key} is not supported")
    for key in required_root:
        if key not in data:
            issues.append(f"$.{key} is required")
    if data.get("schema_version") != STATE_SCHEMA_VERSION:
        issues.append(f"$.schema_version must equal {STATE_SCHEMA_VERSION}")
    if not _is_datetime(data.get("updated_at")):
        issues.append("$.updated_at must be an RFC 3339 date-time with timezone")
    for key in ("revision", "last_good_revision"):
        if not isinstance(data.get(key), int) or isinstance(data.get(key), bool) or data[key] < 0:
            issues.append(f"$.{key} must be a non-negative integer")
    if isinstance(data.get("last_good_revision"), int) and isinstance(data.get("revision"), int) and data["last_good_revision"] > data["revision"]:
        issues.append("$.last_good_revision cannot exceed $.revision")

    active = data.get("active_packages")
    if not isinstance(active, list):
        issues.append("$.active_packages must be an array")
        active = []
    active_ids: set[str] = set()
    active_keys = {
        "id", "version", "previous_version", "install_path", "manifest_path", "entrypoints",
        "status", "activated_at", "restart_required", "last_error",
    }
    for index, item in enumerate(active):
        path = f"$.active_packages[{index}]"
        if not isinstance(item, dict):
            issues.append(f"{path} must be an object")
            continue
        if set(item) != active_keys:
            for key in active_keys - item.keys():
                issues.append(f"{path}.{key} is required")
            for key in item.keys() - active_keys:
                issues.append(f"{path}.{key} is not supported")
        package_id = item.get("id")
        if not isinstance(package_id, str) or PACKAGE_ID_RE.fullmatch(package_id) is None:
            issues.append(f"{path}.id is invalid")
        elif package_id in active_ids:
            issues.append(f"{path}.id duplicates {package_id!r}")
        else:
            active_ids.add(package_id)
        for key in ("version", "previous_version"):
            if item.get(key) is not None:
                try:
                    Version.parse(item[key])
                except ValidationError as exc:
                    issues.append(f"{path}.{key}: {exc.message}")
        for key in ("install_path", "manifest_path"):
            if not isinstance(item.get(key), str) or not item[key]:
                issues.append(f"{path}.{key} must be a non-empty string")
        _validate_entrypoints(item.get("entrypoints"), f"{path}.entrypoints", issues)
        if item.get("status") not in _ACTIVE_STATUSES:
            issues.append(f"{path}.status is invalid")
        if not _is_datetime(item.get("activated_at")):
            issues.append(f"{path}.activated_at must be a date-time")
        if not isinstance(item.get("restart_required"), bool):
            issues.append(f"{path}.restart_required must be boolean")
        if item.get("last_error") is not None and not isinstance(item["last_error"], str):
            issues.append(f"{path}.last_error must be null or a string")

    pending = data.get("pending_activations")
    if not isinstance(pending, list):
        issues.append("$.pending_activations must be an array")
        pending = []
    pending_ids: set[str] = set()
    pending_keys = {
        "id", "from_version", "to_version", "staged_path", "requested_at", "reason",
        "requires_restart", "status", "last_error",
    }
    for index, item in enumerate(pending):
        path = f"$.pending_activations[{index}]"
        if not isinstance(item, dict):
            issues.append(f"{path} must be an object")
            continue
        if set(item) != pending_keys:
            for key in pending_keys - item.keys():
                issues.append(f"{path}.{key} is required")
            for key in item.keys() - pending_keys:
                issues.append(f"{path}.{key} is not supported")
        package_id = item.get("id")
        if not isinstance(package_id, str) or PACKAGE_ID_RE.fullmatch(package_id) is None:
            issues.append(f"{path}.id is invalid")
        elif package_id in pending_ids:
            issues.append(f"{path}.id duplicates {package_id!r}")
        else:
            pending_ids.add(package_id)
        for key in ("from_version", "to_version"):
            if item.get(key) is not None:
                try:
                    Version.parse(item[key])
                except ValidationError as exc:
                    issues.append(f"{path}.{key}: {exc.message}")
        if not isinstance(item.get("staged_path"), str) or not item["staged_path"]:
            issues.append(f"{path}.staged_path must be a non-empty string")
        if not _is_datetime(item.get("requested_at")):
            issues.append(f"{path}.requested_at must be a date-time")
        if item.get("reason") not in _REASONS:
            issues.append(f"{path}.reason is invalid")
        if not isinstance(item.get("requires_restart"), bool):
            issues.append(f"{path}.requires_restart must be boolean")
        if item.get("status") not in _PENDING_STATUSES:
            issues.append(f"{path}.status is invalid")
        if item.get("last_error") is not None and not isinstance(item["last_error"], str):
            issues.append(f"{path}.last_error must be null or a string")
    return issues


@dataclass(frozen=True, slots=True)
class ActiveState:
    updated_at: str
    revision: int
    last_good_revision: int
    active_packages: tuple[ActivePackage, ...]
    pending_activations: tuple[PendingActivation, ...]

    @classmethod
    def empty(cls) -> "ActiveState":
        return cls(utc_now(), 0, 0, (), ())

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "ActiveState":
        issues = validate_active_state_data(data)
        if issues:
            raise ValidationError("Active state validation failed", issues)
        return cls(
            updated_at=data["updated_at"],
            revision=data["revision"],
            last_good_revision=data["last_good_revision"],
            active_packages=tuple(ActivePackage.from_data(item) for item in data["active_packages"]),
            pending_activations=tuple(PendingActivation.from_data(item) for item in data["pending_activations"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": STATE_SCHEMA_VERSION,
            "updated_at": self.updated_at,
            "revision": self.revision,
            "last_good_revision": self.last_good_revision,
            "active_packages": [item.to_dict() for item in sorted(self.active_packages, key=lambda package: package.id)],
            "pending_activations": [item.to_dict() for item in sorted(self.pending_activations, key=lambda pending: pending.id)],
        }

    def active(self, package_id: str) -> ActivePackage | None:
        return next((package for package in self.active_packages if package.id == package_id), None)

    def pending(self, package_id: str) -> PendingActivation | None:
        return next((pending for pending in self.pending_activations if pending.id == package_id), None)


def load_active_state(path: str | Path) -> ActiveState:
    source = Path(path)
    return ActiveState.from_data(load_json(source)) if source.exists() else ActiveState.empty()


def save_active_state(path: str | Path, state: ActiveState) -> None:
    issues = validate_active_state_data(state.to_dict())
    if issues:
        raise ValidationError("Active state validation failed", issues)
    atomic_write_json(path, state.to_dict())


@contextmanager
def _state_lock(state_path: Path) -> Iterator[None]:
    lock_path = state_path.with_name(f".{state_path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise StateError(f"state is being modified by another process: {lock_path}") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="ascii") as handle:
            handle.write(str(os.getpid()))
            handle.flush()
        yield
    finally:
        lock_path.unlink(missing_ok=True)


def _load_staged_manifest(
    store: Path,
    package_id: str,
    version: Version,
    expected_artifact_sha256: str | None,
) -> tuple[PackageManifest, Path, dict[str, str | None]]:
    unresolved_parent = store / package_id
    unresolved_install_path = unresolved_parent / str(version)
    if unresolved_parent.is_symlink() or unresolved_install_path.is_symlink():
        raise StateError("package path must not contain symbolic links")
    install_path = unresolved_install_path.resolve()
    try:
        install_path.relative_to(store)
    except ValueError as exc:
        raise StateError("computed package path escapes package store") from exc
    if not install_path.is_dir():
        raise StateError(f"staged package does not exist: {install_path}")
    manifest_path = install_path / "package.json"
    manifest = load_manifest(manifest_path)
    if manifest.id != package_id or not manifest.version.exactly_equals(version):
        raise StateError("staged package manifest identity does not match its immutable path")
    metadata_path = install_path / ".tdimagefx_install.json"
    if metadata_path.exists():
        metadata = load_json(metadata_path)
        artifact_hash = metadata.get("artifact_sha256")
        artifact_file = metadata.get("artifact_file")
        manifest_hash = metadata.get("manifest_sha256")
        content_hash = metadata.get("content_sha256")
        if (
            not is_sha256(artifact_hash)
            or artifact_file != ".tdimagefx_artifact.zip"
            or not is_sha256(manifest_hash)
            or not is_sha256(content_hash)
        ):
            raise StateError("staged package integrity metadata is invalid")
        retained_artifact = install_path / artifact_file
        if not retained_artifact.is_file() or retained_artifact.is_symlink():
            raise StateError("staged package retained artifact is missing or unsafe")
        if sha256_file(retained_artifact) != artifact_hash.lower():
            raise StateError("staged package retained artifact failed SHA-256 verification")
        if expected_artifact_sha256 is not None and artifact_hash.lower() != expected_artifact_sha256.lower():
            raise StateError("staged package artifact hash does not match activation request")
        if sha256_file(manifest_path) != manifest_hash.lower():
            raise StateError("staged package manifest changed after verification")
        if content_sha256(install_path) != content_hash.lower():
            raise StateError("staged package content changed after verification")
        if archive_content_sha256(retained_artifact) != content_hash.lower():
            raise StateError("staged package content does not match its retained verified artifact")
    elif expected_artifact_sha256 is not None:
        raise StateError("staged package has no integrity metadata")
    entrypoints: dict[str, str | None] = {}
    for name in ("shader", "touchdesigner_component", "native_plugin"):
        relative = manifest.entrypoints.get(name)
        if relative is None:
            entrypoints[name] = None
            continue
        safe_path = validate_package_path(relative, label=f"entrypoint {name}")
        absolute = install_path.joinpath(*safe_path.parts).resolve()
        if not absolute.is_file():
            raise StateError(f"staged package entrypoint is missing: {relative}")
        entrypoints[name] = str(absolute)
    return manifest, install_path, entrypoints


def activate_package(
    state_path: str | os.PathLike[str],
    package_store: str | os.PathLike[str],
    package_id: str,
    version: str | Version,
    *,
    expected_artifact_sha256: str | None = None,
    reason: str | None = None,
    requires_restart: bool | None = None,
    runtime: RuntimeContext | None = None,
    supported_fx_api: str = "1.0",
    strict_compatibility: bool = False,
) -> ActiveState:
    """Record a staged request, then atomically select the immutable version."""

    if PACKAGE_ID_RE.fullmatch(package_id) is None:
        raise ValidationError("Invalid package id")
    target_version = Version.parse(version) if isinstance(version, str) else version
    state_file = Path(state_path)
    store = Path(package_store).resolve()
    with _state_lock(state_file):
        state = load_active_state(state_file)
        current = state.active(package_id)
        if current is not None and current.version.exactly_equals(target_version):
            raise StateError(f"package {package_id} {target_version} is already active")
        existing_pending = state.pending(package_id)
        if existing_pending is not None:
            current_version = current.version if current else None
            from_matches = (
                existing_pending.from_version is None and current_version is None
            ) or (
                existing_pending.from_version is not None
                and current_version is not None
                and existing_pending.from_version.exactly_equals(current_version)
            )
            if (
                existing_pending.status != "staged"
                or not existing_pending.to_version.exactly_equals(target_version)
                or not from_matches
            ):
                raise StateError(f"package {package_id} already has a different pending activation")
        manifest, install_path, entrypoints = _load_staged_manifest(
            store,
            package_id,
            target_version,
            expected_artifact_sha256,
        )
        if runtime is not None:
            compatibility = check_package_compatibility(
                manifest,
                runtime,
                supported_fx_api=supported_fx_api,
                strict_unknown=strict_compatibility,
            )
            if not compatibility.compatible:
                raise CompatibilityError("package activation is incompatible:\n- " + "\n- ".join(compatibility.errors))
        inferred_restart = manifest.kind == "plugin" or entrypoints.get("native_plugin") is not None
        restart = (
            existing_pending.requires_restart
            if existing_pending is not None
            else (requires_restart if requires_restart is not None else inferred_restart)
        )
        activation_reason = existing_pending.reason if existing_pending is not None else (reason or ("install" if current is None else "update"))
        if activation_reason not in _REASONS:
            raise ValidationError("Invalid activation reason")
        if existing_pending is None:
            pending = PendingActivation(
                id=package_id,
                from_version=current.version if current else None,
                to_version=target_version,
                staged_path=str(install_path),
                requested_at=utc_now(),
                reason=activation_reason,
                requires_restart=restart,
                status="staged",
            )
            staged_state = replace(
                state,
                updated_at=utc_now(),
                pending_activations=state.pending_activations + (pending,),
            )
            save_active_state(state_file, staged_state)
        else:
            pending = existing_pending

        active = ActivePackage(
            id=package_id,
            version=target_version,
            previous_version=current.version if current else None,
            install_path=str(install_path),
            manifest_path=str(install_path / "package.json"),
            entrypoints=entrypoints,
            status="pending_restart" if restart else "active",
            activated_at=utc_now(),
            restart_required=restart,
        )
        active_packages = tuple(item for item in state.active_packages if item.id != package_id) + (active,)
        next_revision = state.revision + 1
        if restart:
            waiting = replace(pending, status="awaiting_restart")
            pending_activations = tuple(item for item in state.pending_activations if item.id != package_id) + (waiting,)
            last_good = state.last_good_revision
        else:
            pending_activations = tuple(item for item in state.pending_activations if item.id != package_id)
            last_good = next_revision
        result = ActiveState(utc_now(), next_revision, last_good, active_packages, pending_activations)
        save_active_state(state_file, result)
        return result


def finalize_pending_activation(state_path: str | os.PathLike[str], package_id: str) -> ActiveState:
    state_file = Path(state_path)
    with _state_lock(state_file):
        state = load_active_state(state_file)
        pending = state.pending(package_id)
        active = state.active(package_id)
        if pending is None or pending.status != "awaiting_restart" or active is None:
            raise StateError(f"package {package_id} has no restart activation to finalize")
        active_packages = tuple(
            replace(item, status="active", activated_at=utc_now()) if item.id == package_id else item
            for item in state.active_packages
        )
        result = replace(
            state,
            updated_at=utc_now(),
            last_good_revision=state.revision,
            active_packages=active_packages,
            pending_activations=tuple(item for item in state.pending_activations if item.id != package_id),
        )
        save_active_state(state_file, result)
        return result


def rollback_package(
    state_path: str | os.PathLike[str],
    package_store: str | os.PathLike[str],
    package_id: str,
) -> ActiveState:
    state = load_active_state(state_path)
    active = state.active(package_id)
    if active is None:
        raise StateError(f"package {package_id} is not active")
    if active.previous_version is None:
        raise StateError(f"package {package_id} has no previous version to restore")
    if state.pending(package_id) is not None:
        raise StateError(f"package {package_id} has a pending activation")
    return activate_package(
        state_path,
        package_store,
        package_id,
        active.previous_version,
        reason="rollback",
    )
