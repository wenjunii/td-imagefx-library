"""Local package inventory and remote update-feed models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

from .compatibility import CompatibilityReport, RuntimeContext, check_compatibility, normalize_architecture, normalize_os, validate_compatibility_spec
from .errors import StateError, ValidationError
from .jsonutil import atomic_write_json, load_json
from .manifest import CHANNELS, KINDS, PACKAGE_ID_RE, is_sha256
from .semver import Version


REGISTRY_SCHEMA_VERSION = 1
MAX_FEED_PACKAGES = 4096
MAX_RELEASES_PER_PACKAGE = 128
MAX_ARTIFACTS_PER_RELEASE = 16
MAX_UPDATE_URI_LENGTH = 4096
MAX_FEED_TEXT_LENGTH = 20000
MAX_ARTIFACT_SIZE_BYTES = 256 * 1024 * 1024
_INSTALL_STATUSES = {"staged", "ready", "broken", "quarantined", "pending_delete"}
_VERIFICATIONS = {"verified", "unverified", "failed"}
_SOURCE_TYPES = {"bundled", "feed", "local"}
_SUPPORTED_OS = {"windows", "macos"}
_SUPPORTED_ARCHES = {"x86_64", "arm64"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _valid_datetime(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _valid_uri(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    parsed = urlsplit(value)
    return bool(parsed.scheme and (parsed.netloc or parsed.scheme == "file"))


def _valid_update_uri(value: Any) -> bool:
    if not _valid_uri(value) or len(value) > MAX_UPDATE_URI_LENGTH:
        return False
    parsed = urlsplit(value)
    if parsed.scheme.lower() == "https":
        try:
            parsed.port
        except ValueError:
            return False
        return bool(parsed.hostname and parsed.username is None and parsed.password is None)
    if parsed.scheme.lower() == "file":
        return parsed.netloc in {"", "localhost"} and not parsed.query and not parsed.fragment
    return False


def _valid_persisted_uri(value: Any) -> bool:
    if not _valid_update_uri(value):
        return False
    parsed = urlsplit(value)
    return not parsed.query and not parsed.fragment


def _redact_update_uri(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme.lower() == "https":
        hostname = parsed.hostname or "invalid-host"
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        authority = f"{hostname}:{parsed.port}" if parsed.port is not None else hostname
        return urlunsplit(("https", authority, parsed.path, "", ""))
    if parsed.scheme.lower() == "file":
        return "file:///REDACTED"
    return value


def _check_exact_keys(value: dict[str, Any], allowed: set[str], path: str, issues: list[str]) -> None:
    for key in value.keys() - allowed:
        issues.append(f"{path}.{key} is not supported")


@dataclass(frozen=True, slots=True)
class InstalledVersion:
    version: Version
    install_path: str
    manifest_path: str
    installed_at: str
    source: dict[str, Any]
    integrity: dict[str, Any]
    status: str
    last_checked_at: str | None = None
    error: str | None = None

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "InstalledVersion":
        return cls(
            version=Version.parse(data["version"]),
            install_path=data["install_path"],
            manifest_path=data["manifest_path"],
            installed_at=data["installed_at"],
            source=dict(data["source"]),
            integrity=dict(data["integrity"]),
            status=data["status"],
            last_checked_at=data.get("last_checked_at"),
            error=data.get("error"),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "version": str(self.version),
            "install_path": self.install_path,
            "manifest_path": self.manifest_path,
            "installed_at": self.installed_at,
            "source": dict(self.source),
            "integrity": dict(self.integrity),
            "status": self.status,
        }
        if self.last_checked_at is not None:
            result["last_checked_at"] = self.last_checked_at
        if self.error is not None:
            result["error"] = self.error
        return result


def validate_local_registry_data(data: Any) -> list[str]:
    issues: list[str] = []
    if not isinstance(data, dict):
        return ["$ must be an object"]
    _check_exact_keys(data, {"schema_version", "updated_at", "library_root", "packages"}, "$", issues)
    if data.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        issues.append(f"$.schema_version must equal {REGISTRY_SCHEMA_VERSION}")
    if not _valid_datetime(data.get("updated_at")):
        issues.append("$.updated_at must be an RFC 3339 date-time with timezone")
    if not isinstance(data.get("library_root"), str) or not data["library_root"]:
        issues.append("$.library_root must be a non-empty string")
    elif len(data["library_root"]) > 2048:
        issues.append("$.library_root must be at most 2048 characters")
    packages = data.get("packages")
    if not isinstance(packages, list):
        issues.append("$.packages must be an array")
        return issues
    package_ids: set[str] = set()
    for package_index, package in enumerate(packages):
        package_path = f"$.packages[{package_index}]"
        if not isinstance(package, dict):
            issues.append(f"{package_path} must be an object")
            continue
        _check_exact_keys(package, {"id", "installed_versions"}, package_path, issues)
        package_id = package.get("id")
        if not isinstance(package_id, str) or PACKAGE_ID_RE.fullmatch(package_id) is None:
            issues.append(f"{package_path}.id is invalid")
        elif len(package_id) > 180:
            issues.append(f"{package_path}.id is too long")
        elif package_id in package_ids:
            issues.append(f"{package_path}.id duplicates {package_id!r}")
        else:
            package_ids.add(package_id)
        versions = package.get("installed_versions")
        if not isinstance(versions, list) or not versions:
            issues.append(f"{package_path}.installed_versions must be a non-empty array")
            continue
        seen_versions: set[str] = set()
        for version_index, installed in enumerate(versions):
            path = f"{package_path}.installed_versions[{version_index}]"
            if not isinstance(installed, dict):
                issues.append(f"{path} must be an object")
                continue
            allowed = {
                "version", "install_path", "manifest_path", "installed_at", "source", "integrity",
                "status", "last_checked_at", "error",
            }
            _check_exact_keys(installed, allowed, path, issues)
            try:
                parsed_version = Version.parse(installed.get("version"))
            except ValidationError as exc:
                issues.append(f"{path}.version: {exc.message}")
            else:
                exact = str(parsed_version)
                if exact in seen_versions:
                    issues.append(f"{path}.version duplicates {exact!r}")
                seen_versions.add(exact)
            for key in ("install_path", "manifest_path"):
                if not isinstance(installed.get(key), str) or not installed[key]:
                    issues.append(f"{path}.{key} must be a non-empty string")
            if not _valid_datetime(installed.get("installed_at")):
                issues.append(f"{path}.installed_at must be an RFC 3339 date-time")
            source = installed.get("source")
            if (
                not isinstance(source, dict)
                or not isinstance(source.get("type"), str)
                or source.get("type") not in _SOURCE_TYPES
            ):
                issues.append(f"{path}.source.type must be bundled, feed, or local")
            else:
                _check_exact_keys(
                    source,
                    {"type", "feed_url", "artifact_url", "feed_id", "feed_sha256"},
                    f"{path}.source",
                    issues,
                )
                for key in ("feed_url", "artifact_url"):
                    if source.get(key) is not None and not _valid_persisted_uri(source[key]):
                        issues.append(f"{path}.source.{key} must be null or a safe update URI")
                if source.get("feed_id") is not None:
                    feed_id = source["feed_id"]
                    if (
                        not isinstance(feed_id, str)
                        or len(feed_id) > 180
                        or PACKAGE_ID_RE.fullmatch(feed_id) is None
                    ):
                        issues.append(f"{path}.source.feed_id must be null or a valid feed id")
                if source.get("feed_sha256") is not None and not is_sha256(source["feed_sha256"]):
                    issues.append(f"{path}.source.feed_sha256 must be null or a SHA-256 digest")
            integrity = installed.get("integrity")
            if not isinstance(integrity, dict):
                issues.append(f"{path}.integrity must be an object")
            else:
                _check_exact_keys(integrity, {"manifest_sha256", "artifact_sha256", "verification", "signature_key_id"}, f"{path}.integrity", issues)
                for required in ("manifest_sha256", "artifact_sha256", "verification"):
                    if required not in integrity:
                        issues.append(f"{path}.integrity.{required} is required")
                for key in ("manifest_sha256", "artifact_sha256"):
                    if integrity.get(key) is not None and not is_sha256(integrity[key]):
                        issues.append(f"{path}.integrity.{key} must be null or a SHA-256 digest")
                if not isinstance(integrity.get("verification"), str) or integrity.get("verification") not in _VERIFICATIONS:
                    issues.append(f"{path}.integrity.verification is invalid")
            if not isinstance(installed.get("status"), str) or installed.get("status") not in _INSTALL_STATUSES:
                issues.append(f"{path}.status is invalid")
            if installed.get("last_checked_at") is not None and not _valid_datetime(installed["last_checked_at"]):
                issues.append(f"{path}.last_checked_at must be null or a date-time")
            if installed.get("error") is not None and not isinstance(installed["error"], str):
                issues.append(f"{path}.error must be null or a string")
    return issues


@dataclass(frozen=True, slots=True)
class LocalRegistry:
    library_root: str
    packages: dict[str, tuple[InstalledVersion, ...]]
    updated_at: str

    @classmethod
    def empty(cls, library_root: str | Path) -> "LocalRegistry":
        return cls(str(Path(library_root).resolve()), {}, utc_now())

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "LocalRegistry":
        issues = validate_local_registry_data(data)
        if issues:
            raise ValidationError("Local registry validation failed", issues)
        packages = {
            package["id"]: tuple(InstalledVersion.from_data(item) for item in package["installed_versions"])
            for package in data["packages"]
        }
        return cls(data["library_root"], packages, data["updated_at"])

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": REGISTRY_SCHEMA_VERSION,
            "updated_at": self.updated_at,
            "library_root": self.library_root,
            "packages": [
                {"id": package_id, "installed_versions": [item.to_dict() for item in versions]}
                for package_id, versions in sorted(self.packages.items())
            ],
        }

    def installed_map(self, *, statuses: set[str] | None = None) -> dict[str, Version]:
        allowed = statuses or {"staged", "ready"}
        result: dict[str, Version] = {}
        for package_id, versions in self.packages.items():
            eligible = [item.version for item in versions if item.status in allowed]
            if eligible:
                result[package_id] = max(eligible)
        return result

    def add(self, package_id: str, installed: InstalledVersion) -> "LocalRegistry":
        records = list(self.packages.get(package_id, ()))
        for existing in records:
            if str(existing.version) == str(installed.version):
                old_hash = existing.integrity.get("artifact_sha256")
                new_hash = installed.integrity.get("artifact_sha256")
                if old_hash != new_hash:
                    raise StateError(f"immutable package {package_id} {installed.version} already has a different artifact hash")
                raise StateError(f"package {package_id} {installed.version} is already registered")
        records.append(installed)
        packages = dict(self.packages)
        packages[package_id] = tuple(sorted(records, key=lambda item: item.version))
        return LocalRegistry(self.library_root, packages, utc_now())


def load_local_registry(path: str | Path) -> LocalRegistry:
    return LocalRegistry.from_data(load_json(path))


def save_local_registry(path: str | Path, registry: LocalRegistry) -> None:
    atomic_write_json(path, registry.to_dict())


@dataclass(frozen=True, slots=True)
class ReleaseArtifact:
    url: str
    sha256: str
    size_bytes: int
    operating_systems: tuple[str, ...]
    architectures: tuple[str, ...]
    media_type: str | None = None
    signature: dict[str, Any] | None = None

    def supports(self, runtime: RuntimeContext) -> bool:
        return (
            normalize_os(runtime.operating_system) in {normalize_os(item) for item in self.operating_systems}
            and normalize_architecture(runtime.architecture) in {normalize_architecture(item) for item in self.architectures}
        )


@dataclass(frozen=True, slots=True)
class FeedRelease:
    version: Version
    channel: str
    published_at: str
    manifest_url: str
    manifest_sha256: str
    artifacts: tuple[ReleaseArtifact, ...]
    compatibility: dict[str, Any]
    requires_restart: bool
    yanked: bool
    changelog: str
    security_advisory: str | None = None
    permissions_changed: bool = False

    def artifact_for(self, runtime: RuntimeContext) -> ReleaseArtifact | None:
        return next((artifact for artifact in self.artifacts if artifact.supports(runtime)), None)


@dataclass(frozen=True, slots=True)
class FeedPackage:
    id: str
    name: str
    kind: str
    releases: tuple[FeedRelease, ...]


@dataclass(frozen=True, slots=True)
class UpdateCandidate:
    package: FeedPackage
    installed_version: Version | None
    release: FeedRelease
    artifact: ReleaseArtifact
    compatibility: CompatibilityReport

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.package.id,
            "name": self.package.name,
            "kind": self.package.kind,
            "installed_version": str(self.installed_version) if self.installed_version else None,
            "available_version": str(self.release.version),
            "channel": self.release.channel,
            "manifest_url": _redact_update_uri(self.release.manifest_url),
            "manifest_sha256": self.release.manifest_sha256,
            "artifact_url": _redact_update_uri(self.artifact.url),
            "artifact_sha256": self.artifact.sha256,
            "size_bytes": self.artifact.size_bytes,
            "requires_restart": self.release.requires_restart,
            "permissions_changed": self.release.permissions_changed,
            "compatibility": self.compatibility.to_dict(),
        }


def _validate_signature(value: Any, path: str, issues: list[str]) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        issues.append(f"{path} must be null or an object")
        return
    _check_exact_keys(value, {"algorithm", "key_id", "value"}, path, issues)
    if not isinstance(value.get("algorithm"), str) or value.get("algorithm") not in {"ed25519", "rsa_pss_sha256", "ecdsa_p384_sha384"}:
        issues.append(f"{path}.algorithm is invalid")
    for key in ("key_id", "value"):
        if not isinstance(value.get(key), str) or not value[key]:
            issues.append(f"{path}.{key} must be a non-empty string")
    if isinstance(value.get("key_id"), str) and len(value["key_id"]) > 200:
        issues.append(f"{path}.key_id is too long")
    if isinstance(value.get("value"), str) and len(value["value"]) > 16384:
        issues.append(f"{path}.value is too long")


def validate_update_feed_data(data: Any) -> list[str]:
    issues: list[str] = []
    if not isinstance(data, dict):
        return ["$ must be an object"]
    _check_exact_keys(data, {"schema_version", "feed_id", "generated_at", "channel", "packages", "signature"}, "$", issues)
    if data.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        issues.append(f"$.schema_version must equal {REGISTRY_SCHEMA_VERSION}")
    feed_id = data.get("feed_id")
    if not isinstance(feed_id, str) or PACKAGE_ID_RE.fullmatch(feed_id) is None:
        issues.append("$.feed_id is invalid")
    elif len(feed_id) > 180:
        issues.append("$.feed_id is too long")
    if not _valid_datetime(data.get("generated_at")):
        issues.append("$.generated_at must be an RFC 3339 date-time with timezone")
    if not isinstance(data.get("channel"), str) or data.get("channel") not in CHANNELS:
        issues.append("$.channel is invalid")
    _validate_signature(data.get("signature"), "$.signature", issues)
    packages = data.get("packages")
    if not isinstance(packages, list):
        issues.append("$.packages must be an array")
        return issues
    if len(packages) > MAX_FEED_PACKAGES:
        issues.append(f"$.packages exceeds the {MAX_FEED_PACKAGES}-package limit")
        return issues
    channel_order = {"stable": 0, "beta": 1, "experimental": 2}
    feed_channel = data.get("channel")
    seen_packages: set[str] = set()
    for package_index, package in enumerate(packages):
        package_path = f"$.packages[{package_index}]"
        if not isinstance(package, dict):
            issues.append(f"{package_path} must be an object")
            continue
        _check_exact_keys(package, {"id", "name", "kind", "releases"}, package_path, issues)
        package_id = package.get("id")
        if not isinstance(package_id, str) or PACKAGE_ID_RE.fullmatch(package_id) is None:
            issues.append(f"{package_path}.id is invalid")
        elif len(package_id) > 180:
            issues.append(f"{package_path}.id is too long")
        elif package_id in seen_packages:
            issues.append(f"{package_path}.id duplicates {package_id!r}")
        else:
            seen_packages.add(package_id)
        if not isinstance(package.get("name"), str) or not package["name"]:
            issues.append(f"{package_path}.name must be a non-empty string")
        elif len(package["name"]) > 120:
            issues.append(f"{package_path}.name is too long")
        if not isinstance(package.get("kind"), str) or package.get("kind") not in KINDS:
            issues.append(f"{package_path}.kind is invalid")
        releases = package.get("releases")
        if not isinstance(releases, list) or not releases:
            issues.append(f"{package_path}.releases must be a non-empty array")
            continue
        if len(releases) > MAX_RELEASES_PER_PACKAGE:
            issues.append(
                f"{package_path}.releases exceeds the {MAX_RELEASES_PER_PACKAGE}-release limit"
            )
            continue
        seen_releases: set[str] = set()
        seen_precedence: dict[Version, str] = {}
        for release_index, release in enumerate(releases):
            path = f"{package_path}.releases[{release_index}]"
            if not isinstance(release, dict):
                issues.append(f"{path} must be an object")
                continue
            allowed = {
                "version", "channel", "published_at", "manifest_url", "manifest_sha256", "artifacts",
                "compatibility", "requires_restart", "yanked", "changelog", "security_advisory", "permissions_changed",
            }
            _check_exact_keys(release, allowed, path, issues)
            required = allowed - {"security_advisory", "permissions_changed"}
            for key in required:
                if key not in release:
                    issues.append(f"{path}.{key} is required")
            try:
                parsed_version = Version.parse(release.get("version"))
            except ValidationError as exc:
                issues.append(f"{path}.version: {exc.message}")
            else:
                exact = str(parsed_version)
                if exact in seen_releases:
                    issues.append(f"{path}.version duplicates {exact!r}")
                previous = seen_precedence.get(parsed_version)
                if previous is not None and previous != exact:
                    issues.append(
                        f"{path}.version has ambiguous SemVer precedence with {previous!r}"
                    )
                seen_releases.add(exact)
                seen_precedence[parsed_version] = exact
            if not isinstance(release.get("channel"), str) or release.get("channel") not in CHANNELS:
                issues.append(f"{path}.channel is invalid")
            elif isinstance(feed_channel, str) and feed_channel in CHANNELS and channel_order[release["channel"]] > channel_order[feed_channel]:
                issues.append(f"{path}.channel is outside the {feed_channel!r} feed hierarchy")
            if not _valid_datetime(release.get("published_at")):
                issues.append(f"{path}.published_at must be a date-time")
            if not _valid_update_uri(release.get("manifest_url")):
                issues.append(f"{path}.manifest_url must be a safe HTTPS or local file URI")
            if not is_sha256(release.get("manifest_sha256")):
                issues.append(f"{path}.manifest_sha256 must be a SHA-256 digest")
            try:
                compatibility_issues = validate_compatibility_spec(
                    release.get("compatibility"), path=f"{path}.compatibility"
                )
            except (TypeError, ValueError):
                compatibility_issues = [f"{path}.compatibility contains invalid value types"]
            issues.extend(compatibility_issues)
            for key in ("requires_restart", "yanked"):
                if not isinstance(release.get(key), bool):
                    issues.append(f"{path}.{key} must be boolean")
            if "permissions_changed" in release and not isinstance(release["permissions_changed"], bool):
                issues.append(f"{path}.permissions_changed must be boolean")
            if not isinstance(release.get("changelog"), str):
                issues.append(f"{path}.changelog must be a string")
            elif len(release["changelog"]) > MAX_FEED_TEXT_LENGTH:
                issues.append(f"{path}.changelog is too long")
            if release.get("security_advisory") is not None and not isinstance(release["security_advisory"], str):
                issues.append(f"{path}.security_advisory must be null or a string")
            elif isinstance(release.get("security_advisory"), str) and len(release["security_advisory"]) > 10000:
                issues.append(f"{path}.security_advisory is too long")
            artifacts = release.get("artifacts")
            if not isinstance(artifacts, list) or not artifacts:
                issues.append(f"{path}.artifacts must be a non-empty array")
                continue
            if len(artifacts) > MAX_ARTIFACTS_PER_RELEASE:
                issues.append(
                    f"{path}.artifacts exceeds the {MAX_ARTIFACTS_PER_RELEASE}-artifact limit"
                )
                continue
            artifact_targets: set[tuple[str, str]] = set()
            for artifact_index, artifact in enumerate(artifacts):
                artifact_path = f"{path}.artifacts[{artifact_index}]"
                if not isinstance(artifact, dict):
                    issues.append(f"{artifact_path} must be an object")
                    continue
                _check_exact_keys(artifact, {"url", "sha256", "size_bytes", "media_type", "os", "architectures", "signature"}, artifact_path, issues)
                for key in ("url", "sha256", "size_bytes", "os", "architectures"):
                    if key not in artifact:
                        issues.append(f"{artifact_path}.{key} is required")
                if not _valid_update_uri(artifact.get("url")):
                    issues.append(f"{artifact_path}.url must be a safe HTTPS or local file URI")
                if not is_sha256(artifact.get("sha256")):
                    issues.append(f"{artifact_path}.sha256 must be a SHA-256 digest")
                size = artifact.get("size_bytes")
                if (
                    not isinstance(size, int)
                    or isinstance(size, bool)
                    or size < 0
                    or size > MAX_ARTIFACT_SIZE_BYTES
                ):
                    issues.append(
                        f"{artifact_path}.size_bytes must be between 0 and "
                        f"{MAX_ARTIFACT_SIZE_BYTES} bytes"
                    )
                for key, allowed_values in (("os", _SUPPORTED_OS), ("architectures", _SUPPORTED_ARCHES)):
                    values = artifact.get(key)
                    if (
                        not isinstance(values, list)
                        or not values
                        or any(not isinstance(item, str) or item not in allowed_values for item in values)
                    ):
                        issues.append(f"{artifact_path}.{key} contains unsupported values")
                    elif len(set(values)) != len(values):
                        issues.append(f"{artifact_path}.{key} must not contain duplicates")
                operating_systems = artifact.get("os")
                architectures = artifact.get("architectures")
                if (
                    isinstance(operating_systems, list)
                    and isinstance(architectures, list)
                    and all(isinstance(item, str) for item in operating_systems)
                    and all(isinstance(item, str) for item in architectures)
                ):
                    for target in (
                        (operating_system, architecture)
                        for operating_system in operating_systems
                        for architecture in architectures
                    ):
                        if target in artifact_targets:
                            issues.append(
                                f"{artifact_path} overlaps another artifact for {target[0]}/{target[1]}"
                            )
                        artifact_targets.add(target)
                if "media_type" in artifact and (not isinstance(artifact["media_type"], str) or not artifact["media_type"]):
                    issues.append(f"{artifact_path}.media_type must be a non-empty string")
                elif isinstance(artifact.get("media_type"), str) and len(artifact["media_type"]) > 200:
                    issues.append(f"{artifact_path}.media_type is too long")
                _validate_signature(artifact.get("signature"), f"{artifact_path}.signature", issues)
    return issues


@dataclass(frozen=True, slots=True)
class UpdateFeed:
    feed_id: str
    generated_at: str
    channel: str
    packages: tuple[FeedPackage, ...]
    signature: dict[str, Any] | None = None

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "UpdateFeed":
        issues = validate_update_feed_data(data)
        if issues:
            raise ValidationError("Update feed validation failed", issues)
        packages: list[FeedPackage] = []
        for package in data["packages"]:
            releases: list[FeedRelease] = []
            for release in package["releases"]:
                artifacts = tuple(
                    ReleaseArtifact(
                        url=artifact["url"],
                        sha256=artifact["sha256"].lower(),
                        size_bytes=artifact["size_bytes"],
                        operating_systems=tuple(artifact["os"]),
                        architectures=tuple(artifact["architectures"]),
                        media_type=artifact.get("media_type"),
                        signature=artifact.get("signature"),
                    )
                    for artifact in release["artifacts"]
                )
                releases.append(
                    FeedRelease(
                        version=Version.parse(release["version"]),
                        channel=release["channel"],
                        published_at=release["published_at"],
                        manifest_url=release["manifest_url"],
                        manifest_sha256=release["manifest_sha256"].lower(),
                        artifacts=artifacts,
                        compatibility=dict(release["compatibility"]),
                        requires_restart=release["requires_restart"],
                        yanked=release["yanked"],
                        changelog=release["changelog"],
                        security_advisory=release.get("security_advisory"),
                        permissions_changed=release.get("permissions_changed", False),
                    )
                )
            packages.append(FeedPackage(package["id"], package["name"], package["kind"], tuple(releases)))
        return cls(data["feed_id"], data["generated_at"], data["channel"], tuple(packages), data.get("signature"))

    def updates(
        self,
        installed: dict[str, Version | str],
        runtime: RuntimeContext,
        *,
        channel: str = "stable",
        include_new: bool = True,
        strict_compatibility: bool = False,
    ) -> tuple[UpdateCandidate, ...]:
        if not isinstance(channel, str) or channel not in CHANNELS:
            raise ValidationError("Invalid update channel", [f"channel must be one of {', '.join(sorted(CHANNELS))}"])
        channel_order = {"stable": 0, "beta": 1, "experimental": 2}
        installed_versions = {
            package_id: Version.parse(version) if isinstance(version, str) else version
            for package_id, version in installed.items()
        }
        candidates: list[UpdateCandidate] = []
        for package in self.packages:
            current = installed_versions.get(package.id)
            if current is None and not include_new:
                continue
            eligible: list[UpdateCandidate] = []
            for release in package.releases:
                if release.yanked or channel_order[release.channel] > channel_order[channel]:
                    continue
                if current is not None and release.version <= current:
                    continue
                report = check_compatibility(release.compatibility, runtime, strict_unknown=strict_compatibility)
                if not report.compatible:
                    continue
                artifact = release.artifact_for(runtime)
                if artifact is None:
                    continue
                eligible.append(UpdateCandidate(package, current, release, artifact, report))
            if eligible:
                candidates.append(max(eligible, key=lambda item: item.release.version))
        return tuple(sorted(candidates, key=lambda item: item.package.id))

    def catalog(self) -> tuple[dict[str, Any], ...]:
        rows: list[dict[str, Any]] = []
        for package in self.packages:
            for release in sorted(package.releases, key=lambda item: item.version, reverse=True):
                rows.append(
                    {
                        "id": package.id,
                        "name": package.name,
                        "kind": package.kind,
                        "version": str(release.version),
                        "channel": release.channel,
                        "yanked": release.yanked,
                        "published_at": release.published_at,
                        "requires_restart": release.requires_restart,
                    }
                )
        return tuple(rows)


def load_update_feed_file(path: str | Path) -> UpdateFeed:
    return UpdateFeed.from_data(load_json(path))
