"""Safe, notify-only update checker for TouchDesigner.

Network work happens on a Python worker thread. The worker only writes bounded,
validated JSON to disk; all operator access remains on TouchDesigner's main thread.
The validation rules intentionally mirror ``tdimagefx.registry`` without requiring
the package core to be importable from an arbitrary .toe project.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import secrets
import tempfile
import threading
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


MAX_FEED_BYTES = 2 * 1024 * 1024
MAX_LOCAL_JSON_BYTES = 2 * 1024 * 1024
MAX_SOURCES = 32
MAX_PACKAGES = 4096
MAX_RELEASES_PER_PACKAGE = 128
MAX_ARTIFACTS_PER_RELEASE = 16
MAX_CHANGELOG_CHARS = 20000
MAX_URL_CHARS = 4096
MAX_STATUS_UPDATES = 1024
MAX_STATUS_CHANGELOG_CHARS = 1000
CHANNEL_ORDER = {"stable": 0, "beta": 1, "experimental": 2}
TRUST_ORDER = {"community": 0, "local": 1, "first_party": 2}
SUPPORTED_KINDS = {
    "effect", "shader", "plugin", "technique", "adapter", "preset",
    "modulator", "example", "core",
}
PACKAGE_ID_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_SEMVER_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<pre>(?:0|[1-9]\d*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


def _unique_object(pairs):
    result = {}
    duplicates = []
    for key, value in pairs:
        if key in result:
            duplicates.append(key)
        result[key] = value
    if duplicates:
        raise ValueError("duplicate JSON object key(s): {}".format(", ".join(sorted(set(duplicates)))))
    return result


def _loads_json(payload, label):
    try:
        value = json.loads(payload.decode("utf-8") if isinstance(payload, bytes) else payload, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("Invalid {}: {}".format(label, exc)) from exc
    if not isinstance(value, dict):
        raise ValueError("{} root must be an object".format(label))
    return value


def _load_json_file(path, label, max_bytes=MAX_LOCAL_JSON_BYTES):
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise ValueError("{} must be a regular non-symlink file".format(label))
    size = source.stat().st_size
    if size < 0 or size > max_bytes:
        raise ValueError("{} exceeds the bounded file-size limit".format(label))
    return _loads_json(source.read_bytes(), label)


def _redact_url(value):
    try:
        raw_value = str(value)
        parsed = urllib.parse.urlsplit(raw_value)
    except (TypeError, ValueError):
        return "invalid-url"
    scheme = parsed.scheme.lower()
    if scheme in {"http", "https"}:
        try:
            host = parsed.hostname or "invalid-host"
            port = parsed.port
        except (TypeError, ValueError):
            return "{}://invalid-host/".format(scheme)
        if ":" in host and not host.startswith("["):
            host = "[{}]".format(host)
        if port is not None:
            host = "{}:{}".format(host, port)
        return urllib.parse.urlunsplit((scheme, host, parsed.path, "", ""))
    if parsed.scheme.lower() == "file":
        return "file://<local>"
    return "invalid-url"


def _split_safe_url(value, label):
    """Parse a bounded update URL and reject all non-identity URL data."""

    if not isinstance(value, str) or not value or len(value) > MAX_URL_CHARS:
        raise ValueError("{} is invalid".format(label))
    try:
        parsed = urllib.parse.urlsplit(value)
        scheme = parsed.scheme.lower()
        hostname = parsed.hostname
        # Accessing ``port`` performs urllib's range and integer validation.
        _ = parsed.port
    except (TypeError, ValueError) as exc:
        raise ValueError("{} is invalid".format(label)) from exc
    if parsed.username or parsed.password:
        raise ValueError("{} must not contain URL credentials".format(label))
    if parsed.query or parsed.fragment:
        raise ValueError("{} must not contain query or fragment data".format(label))
    if scheme == "https":
        if not hostname:
            raise ValueError("{} must include an HTTPS host".format(label))
    elif scheme == "file":
        if parsed.netloc not in ("", "localhost") or not parsed.path:
            raise ValueError("{} must be a local file URL".format(label))
    else:
        raise ValueError("{} must use HTTPS or file".format(label))
    return parsed


def _source_identity(value):
    """Return the exact safe identity used for source reconciliation."""

    parsed = _split_safe_url(value, "update source identity")
    scheme = parsed.scheme.lower()
    if scheme == "https":
        host = parsed.hostname.lower()
        if ":" in host:
            host = "[{}]".format(host)
        port = parsed.port
        if port is not None:
            host = "{}:{}".format(host, port)
        return urllib.parse.urlunsplit((scheme, host, parsed.path, "", ""))
    if scheme == "file":
        local_path = Path(
            urllib.request.url2pathname(urllib.parse.unquote(parsed.path))
        ).resolve()
        return local_path.as_uri()
    raise AssertionError("safe URL parser returned an unsupported scheme")


def _safe_error(exc):
    try:
        text = str(exc)
    except BaseException:
        text = "unprintable error"
    for url in re.findall(r"(?:https?|file)://[^\s'\"]+", text, flags=re.IGNORECASE):
        text = text.replace(url, _redact_url(url))
    return "{}: {}".format(type(exc).__name__, text[:1000])


def _normalize_os(value):
    aliases = {"win32": "windows", "win": "windows", "windows": "windows", "darwin": "macos", "mac": "macos", "macos": "macos", "osx": "macos"}
    return aliases.get(str(value).strip().lower(), str(value).strip().lower())


def _normalize_arch(value):
    aliases = {"amd64": "x86_64", "x64": "x86_64", "x86-64": "x86_64", "x86_64": "x86_64", "aarch64": "arm64", "arm64": "arm64"}
    return aliases.get(str(value).strip().lower(), str(value).strip().lower())


def _build_key(value):
    text = str(value)
    if re.fullmatch(r"\d+(?:\.\d+)*", text) is None:
        raise ValueError("invalid TouchDesigner build {!r}".format(value))
    return tuple(int(part) for part in text.split("."))


def _valid_datetime(value, label):
    if not isinstance(value, str) or not value or len(value) > 100:
        raise ValueError("{} must be a bounded RFC 3339 date-time".format(label))
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("{} must be an RFC 3339 date-time".format(label)) from exc
    if parsed.tzinfo is None:
        raise ValueError("{} must include a timezone".format(label))


def _validate_signature(value, label):
    if value is None:
        return
    fields = {"algorithm", "key_id", "value"}
    _exact_keys(value, fields, fields, label)
    if not isinstance(value["algorithm"], str) or value["algorithm"] not in {"ed25519", "rsa_pss_sha256", "ecdsa_p384_sha384"}:
        raise ValueError("{}.algorithm is invalid".format(label))
    if not isinstance(value["key_id"], str) or not value["key_id"] or len(value["key_id"]) > 200:
        raise ValueError("{}.key_id is invalid".format(label))
    if not isinstance(value["value"], str) or not value["value"] or len(value["value"]) > 16384:
        raise ValueError("{}.value is invalid".format(label))


def _validate_status(value):
    fields = {"schema_version", "check_id", "checked_at", "status", "updates", "errors", "sources_checked", "project_lock", "truncated"}
    _exact_keys(value, fields, fields, "update status")
    if value.get("schema_version") != 1 or not isinstance(value.get("status"), str) or value.get("status") not in {"complete", "failed"}:
        raise ValueError("update status schema or state is invalid")
    check_id = value.get("check_id")
    if not isinstance(check_id, str) or re.fullmatch(r"[0-9a-f]{32}", check_id) is None:
        raise ValueError("update status check_id is invalid")
    _valid_datetime(value.get("checked_at"), "update status.checked_at")
    if not isinstance(value.get("updates"), list) or len(value["updates"]) > MAX_STATUS_UPDATES:
        raise ValueError("update status updates are invalid or too numerous")
    if not all(isinstance(item, dict) for item in value["updates"]):
        raise ValueError("update status entries must be objects")
    if not isinstance(value.get("errors"), list) or len(value["errors"]) > MAX_SOURCES + 1:
        raise ValueError("update status errors are invalid or too numerous")
    if not all(isinstance(item, dict) for item in value["errors"]):
        raise ValueError("update status errors must be objects")
    sources_checked = value.get("sources_checked")
    if not isinstance(sources_checked, int) or isinstance(sources_checked, bool) or not 0 <= sources_checked <= MAX_SOURCES:
        raise ValueError("update status source count is invalid")
    if not isinstance(value.get("truncated"), bool):
        raise ValueError("update status truncated flag is invalid")
    return value


def _exact_keys(value, allowed, required, label):
    if not isinstance(value, dict):
        raise ValueError("{} must be an object".format(label))
    unsupported = set(value) - set(allowed)
    missing = set(required) - set(value)
    if unsupported:
        raise ValueError("{} has unsupported field(s): {}".format(label, ", ".join(sorted(unsupported))))
    if missing:
        raise ValueError("{} is missing field(s): {}".format(label, ", ".join(sorted(missing))))


def _valid_id(value, label):
    if not isinstance(value, str) or len(value) > 180 or PACKAGE_ID_RE.fullmatch(value) is None:
        raise ValueError("{} is invalid".format(label))


def _valid_url(value, label):
    return _split_safe_url(value, label)


class _HttpsOnlyRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_host=None, allowed_port=None):
        super().__init__()
        self.allowed_host = allowed_host.lower() if allowed_host else None
        self.allowed_port = allowed_port

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            original = urllib.parse.urlsplit(req.full_url)
            redirected = urllib.parse.urlsplit(newurl)
        except (TypeError, ValueError) as exc:
            raise ValueError("update feed redirect URL is invalid") from exc
        if original.scheme.lower() == "https" and redirected.scheme.lower() != "https":
            raise ValueError("HTTPS update feeds may only redirect to HTTPS")
        redirected = _valid_url(newurl, "update feed redirect URL")
        if self.allowed_host and (redirected.hostname or "").lower() != self.allowed_host:
            raise ValueError("update feed redirect changed host")
        if self.allowed_host and (redirected.port or 443) != (self.allowed_port or 443):
            raise ValueError("update feed redirect changed port")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class UpdaterExt:
    def __init__(self, ownerComp):
        self.ownerComp = ownerComp
        self._thread = None
        self._scheduled = False
        self._schedule_generation = 0
        self._check_id = None

    def _root(self):
        root_par = self.ownerComp.par["Rootfolder"]
        value = str(root_par.eval()).strip() if root_par is not None else ""
        return Path(value or project.folder).resolve()

    @staticmethod
    def _version_key(version):
        match = _SEMVER_RE.fullmatch(str(version))
        if match is None:
            raise ValueError("Invalid semantic version: {!r}".format(version))
        core = (int(match.group("major")), int(match.group("minor")), int(match.group("patch")))
        prerelease = match.group("pre")
        if prerelease is None:
            return core + (1, ())
        identifiers = tuple((0, int(item)) if item.isdigit() else (1, item) for item in prerelease.split("."))
        return core + (0, identifiers)

    @classmethod
    def _fetch_json_url(cls, url, timeout, expected_sha256=None, file_root=None):
        if not isinstance(url, str) or len(url) > MAX_URL_CHARS:
            raise ValueError("update feed URL is invalid")
        try:
            scheme = urllib.parse.urlsplit(url).scheme.lower()
        except (TypeError, ValueError) as exc:
            raise ValueError("update feed URL is invalid") from exc
        if scheme not in ("https", "file"):
            raise ValueError("Only HTTPS and file update feeds are allowed")
        parsed = _valid_url(url, "update feed URL")
        if scheme == "file":
            if file_root is not None:
                local_path = Path(urllib.request.url2pathname(urllib.parse.unquote(parsed.path))).resolve(strict=True)
                root = Path(file_root).resolve(strict=True)
                try:
                    local_path.relative_to(root)
                except ValueError as exc:
                    raise ValueError("local update feed escapes the library root") from exc
        request = urllib.request.Request(url, headers={"User-Agent": "TD-ImageFX-Updater/0.3", "Accept-Encoding": "identity"})
        opener = urllib.request.build_opener(_HttpsOnlyRedirectHandler(parsed.hostname, parsed.port))
        with opener.open(request, timeout=timeout) as response:
            final_url = response.geturl()
            final = _valid_url(final_url, "final update feed URL")
            if final.scheme.lower() != parsed.scheme.lower():
                raise ValueError("Update feed changed URL scheme")
            if parsed.scheme.lower() == "https":
                initial_origin = ((parsed.hostname or "").lower(), parsed.port or 443)
                final_origin = ((final.hostname or "").lower(), final.port or 443)
                if final_origin != initial_origin:
                    raise ValueError("Update feed changed URL origin")
            encoding = response.headers.get("Content-Encoding")
            if encoding not in (None, "", "identity"):
                raise ValueError("Compressed update feeds are not accepted")
            content_length = response.headers.get("Content-Length")
            if content_length is not None:
                try:
                    announced = int(content_length)
                except ValueError as exc:
                    raise ValueError("Invalid Content-Length") from exc
                if announced < 0 or announced > MAX_FEED_BYTES:
                    raise ValueError("Update feed exceeds the 2 MiB size limit")
            payload = response.read(MAX_FEED_BYTES + 1)
            if len(payload) > MAX_FEED_BYTES:
                raise ValueError("Update feed exceeds the 2 MiB size limit")
        digest = hashlib.sha256(payload).hexdigest()
        if expected_sha256 is not None:
            if not isinstance(expected_sha256, str) or SHA256_RE.fullmatch(expected_sha256) is None:
                raise ValueError("Configured update-feed SHA-256 is invalid")
            if digest != expected_sha256.lower():
                raise ValueError("Update-feed SHA-256 mismatch")
        return _loads_json(payload, "update feed"), digest, _redact_url(final_url)

    @classmethod
    def _load_json_url(cls, url, timeout):
        return cls._fetch_json_url(url, timeout)[0]

    @staticmethod
    def _validate_compatibility(spec, label):
        required = {"touchdesigner_min_build", "touchdesigner_max_build", "os", "architectures"}
        _exact_keys(spec, required, required, label)
        _build_key(spec["touchdesigner_min_build"])
        if spec["touchdesigner_max_build"] is not None:
            _build_key(spec["touchdesigner_max_build"])
        for key, allowed in (("os", {"windows", "macos"}), ("architectures", {"x86_64", "arm64"})):
            values = spec[key]
            if not isinstance(values, list) or not values or any(not isinstance(item, str) or item not in allowed for item in values) or len(values) != len(set(values)):
                raise ValueError("{}.{} is invalid".format(label, key))

    @classmethod
    def _validate_feed(cls, feed, expected_feed_id):
        root_fields = {"schema_version", "feed_id", "generated_at", "channel", "packages", "signature"}
        _exact_keys(feed, root_fields, root_fields - {"signature"}, "feed")
        if feed.get("schema_version") != 1:
            raise ValueError("feed.schema_version must equal 1")
        _valid_id(feed.get("feed_id"), "feed.feed_id")
        if feed["feed_id"] != expected_feed_id:
            raise ValueError("feed_id does not match configured source id")
        if not isinstance(feed.get("channel"), str) or feed.get("channel") not in CHANNEL_ORDER:
            raise ValueError("feed.channel is invalid")
        _valid_datetime(feed.get("generated_at"), "feed.generated_at")
        _validate_signature(feed.get("signature"), "feed.signature")
        packages = feed.get("packages")
        if not isinstance(packages, list) or len(packages) > MAX_PACKAGES:
            raise ValueError("feed.packages exceeds the bounded package limit")
        seen_packages = set()
        for package_index, package in enumerate(packages):
            package_label = "feed.packages[{}]".format(package_index)
            _exact_keys(package, {"id", "name", "kind", "releases"}, {"id", "name", "kind", "releases"}, package_label)
            _valid_id(package.get("id"), package_label + ".id")
            if package["id"] in seen_packages:
                raise ValueError("duplicate feed package id {!r}".format(package["id"]))
            seen_packages.add(package["id"])
            if not isinstance(package.get("name"), str) or not package["name"] or len(package["name"]) > 120:
                raise ValueError(package_label + ".name is invalid")
            if not isinstance(package.get("kind"), str) or package.get("kind") not in SUPPORTED_KINDS:
                raise ValueError(package_label + ".kind is invalid")
            releases = package.get("releases")
            if not isinstance(releases, list) or not releases or len(releases) > MAX_RELEASES_PER_PACKAGE:
                raise ValueError(package_label + ".releases exceeds the bounded release limit")
            seen_versions = set()
            seen_precedence = {}
            for release_index, release in enumerate(releases):
                release_label = package_label + ".releases[{}]".format(release_index)
                fields = {"version", "channel", "published_at", "manifest_url", "manifest_sha256", "artifacts", "compatibility", "requires_restart", "yanked", "changelog", "security_advisory", "permissions_changed"}
                _exact_keys(release, fields, fields - {"security_advisory", "permissions_changed"}, release_label)
                precedence = cls._version_key(release.get("version"))
                if release["version"] in seen_versions:
                    raise ValueError("duplicate release version {!r}".format(release["version"]))
                if precedence in seen_precedence and seen_precedence[precedence] != release["version"]:
                    raise ValueError(
                        "release versions {!r} and {!r} have ambiguous SemVer precedence".format(
                            seen_precedence[precedence], release["version"]
                        )
                    )
                seen_versions.add(release["version"])
                seen_precedence[precedence] = release["version"]
                channel = release.get("channel")
                if not isinstance(channel, str) or channel not in CHANNEL_ORDER or CHANNEL_ORDER[channel] > CHANNEL_ORDER[feed["channel"]]:
                    raise ValueError(release_label + ".channel is outside the feed hierarchy")
                _valid_datetime(release.get("published_at"), release_label + ".published_at")
                _valid_url(release.get("manifest_url"), release_label + ".manifest_url")
                if not isinstance(release.get("manifest_sha256"), str) or SHA256_RE.fullmatch(release["manifest_sha256"]) is None:
                    raise ValueError(release_label + ".manifest_sha256 is invalid")
                cls._validate_compatibility(release.get("compatibility"), release_label + ".compatibility")
                for key in ("requires_restart", "yanked"):
                    if not isinstance(release.get(key), bool):
                        raise ValueError("{}.{} must be boolean".format(release_label, key))
                if "permissions_changed" in release and not isinstance(release["permissions_changed"], bool):
                    raise ValueError(release_label + ".permissions_changed must be boolean")
                if not isinstance(release.get("changelog"), str) or len(release["changelog"]) > MAX_CHANGELOG_CHARS:
                    raise ValueError(release_label + ".changelog is invalid")
                advisory = release.get("security_advisory")
                if advisory is not None and (not isinstance(advisory, str) or len(advisory) > 10000):
                    raise ValueError(release_label + ".security_advisory is invalid")
                artifacts = release.get("artifacts")
                if not isinstance(artifacts, list) or not artifacts or len(artifacts) > MAX_ARTIFACTS_PER_RELEASE:
                    raise ValueError(release_label + ".artifacts exceeds the bounded artifact limit")
                artifact_targets = set()
                for artifact_index, artifact in enumerate(artifacts):
                    artifact_label = release_label + ".artifacts[{}]".format(artifact_index)
                    artifact_fields = {"url", "sha256", "size_bytes", "media_type", "os", "architectures", "signature"}
                    _exact_keys(artifact, artifact_fields, {"url", "sha256", "size_bytes", "os", "architectures"}, artifact_label)
                    _valid_url(artifact.get("url"), artifact_label + ".url")
                    if not isinstance(artifact.get("sha256"), str) or SHA256_RE.fullmatch(artifact["sha256"]) is None:
                        raise ValueError(artifact_label + ".sha256 is invalid")
                    size = artifact.get("size_bytes")
                    if not isinstance(size, int) or isinstance(size, bool) or size < 0 or size > 256 * 1024 * 1024:
                        raise ValueError(artifact_label + ".size_bytes is invalid")
                    media_type = artifact.get("media_type")
                    if media_type is not None and (not isinstance(media_type, str) or not media_type or len(media_type) > 200):
                        raise ValueError(artifact_label + ".media_type is invalid")
                    _validate_signature(artifact.get("signature"), artifact_label + ".signature")
                    for key, allowed in (("os", {"windows", "macos"}), ("architectures", {"x86_64", "arm64"})):
                        values = artifact.get(key)
                        if not isinstance(values, list) or not values or any(not isinstance(item, str) or item not in allowed for item in values) or len(values) != len(set(values)):
                            raise ValueError("{}.{} is invalid".format(artifact_label, key))
                    for target in (
                        (operating_system, architecture)
                        for operating_system in artifact["os"]
                        for architecture in artifact["architectures"]
                    ):
                        if target in artifact_targets:
                            raise ValueError(
                                "{} overlaps another artifact for {}/{}".format(
                                    artifact_label, target[0], target[1]
                                )
                            )
                        artifact_targets.add(target)
        return feed

    @staticmethod
    def _compatibility_report(spec, runtime):
        operating_system = _normalize_os(runtime.get("os", ""))
        architecture = _normalize_arch(runtime.get("architecture", ""))
        if operating_system not in spec["os"] or architecture not in spec["architectures"]:
            return False, False
        build = runtime.get("touchdesigner_build")
        if build is None:
            return True, False
        current = _build_key(build)
        if current < _build_key(spec["touchdesigner_min_build"]):
            return False, False
        maximum = spec["touchdesigner_max_build"]
        compatible = maximum is None or current <= _build_key(maximum)
        return compatible, compatible

    @classmethod
    def _compatible(cls, spec, runtime):
        return cls._compatibility_report(spec, runtime)[0]

    @classmethod
    def _installed_versions(cls, root):
        installed = {}
        manifest_paths = sorted((root / "packages").glob("*/*/package.json"))
        if len(manifest_paths) > MAX_PACKAGES * MAX_RELEASES_PER_PACKAGE:
            raise ValueError("installed manifest count exceeds the bounded limit")
        for manifest_path in manifest_paths:
            manifest = _load_json_file(manifest_path, "installed package manifest")
            package_id = manifest.get("id")
            version = manifest.get("version")
            _valid_id(package_id, "installed package id")
            cls._version_key(version)
            expected = root / "packages" / package_id / str(version) / "package.json"
            if manifest_path.resolve() != expected.resolve():
                raise ValueError("installed package identity does not match its immutable path")
            digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            current = installed.get(package_id)
            if current is None or cls._version_key(version) > cls._version_key(current["version"]):
                installed[package_id] = {"version": version, "manifest_sha256": digest}
        return installed

    @classmethod
    def _project_lock(cls, root, project_root=None):
        path = Path(project_root).resolve() / "tdimagefx.lock.json" if project_root else root / "tdimagefx.lock.json"
        if not path.is_file() and project_root:
            path = root / "tdimagefx.lock.json"
        if not path.is_file():
            return {}, None
        lock = _load_json_file(path, "project lock")
        root_fields = {"schema_version", "generated_at", "project_id", "fx_api", "touchdesigner_build", "packages"}
        _exact_keys(lock, root_fields, root_fields - {"project_id"}, "project lock")
        packages = lock.get("packages")
        if lock.get("schema_version") != 1 or not isinstance(packages, list) or len(packages) > MAX_PACKAGES:
            raise ValueError("project lock has an invalid schema or package count")
        _valid_datetime(lock.get("generated_at"), "project lock.generated_at")
        if lock.get("project_id") is not None and (
            not isinstance(lock["project_id"], str)
            or not lock["project_id"]
            or len(lock["project_id"]) > 200
        ):
            raise ValueError("project lock.project_id is invalid")
        if not isinstance(lock.get("fx_api"), str) or re.fullmatch(r"\d+\.\d+(?:\.\d+)?", lock["fx_api"]) is None:
            raise ValueError("project lock.fx_api is invalid")
        _build_key(lock.get("touchdesigner_build"))
        pins = {}
        pin_fields = {"id", "version", "kind", "channel", "source_feed", "manifest_sha256", "artifact_sha256", "requested", "dependencies"}
        for index, pin in enumerate(packages):
            _exact_keys(pin, pin_fields, pin_fields, "project lock package {}".format(index))
            package_id = pin.get("id")
            version = pin.get("version")
            _valid_id(package_id, "project lock package id")
            cls._version_key(version)
            if package_id in pins:
                raise ValueError("project lock contains duplicate package id {!r}".format(package_id))
            manifest_sha256 = pin.get("manifest_sha256")
            if manifest_sha256 is not None and (not isinstance(manifest_sha256, str) or SHA256_RE.fullmatch(manifest_sha256) is None):
                raise ValueError("project lock manifest digest is invalid")
            artifact_sha256 = pin.get("artifact_sha256")
            if artifact_sha256 is not None and (not isinstance(artifact_sha256, str) or SHA256_RE.fullmatch(artifact_sha256) is None):
                raise ValueError("project lock artifact digest is invalid")
            if (
                not isinstance(pin.get("kind"), str)
                or pin.get("kind") not in SUPPORTED_KINDS
                or not isinstance(pin.get("channel"), str)
                or pin.get("channel") not in CHANNEL_ORDER
            ):
                raise ValueError("project lock package kind or channel is invalid")
            dependencies = pin.get("dependencies")
            if (
                not isinstance(pin.get("requested"), bool)
                or not isinstance(dependencies, list)
                or len(dependencies) > 256
            ):
                raise ValueError("project lock package flags or dependencies are invalid")
            source_feed = pin.get("source_feed")
            if source_feed is not None:
                _valid_url(source_feed, "project lock package source_feed")
            dependency_ids = set()
            for dependency_index, dependency in enumerate(dependencies):
                dependency_label = "project lock dependency {}".format(dependency_index)
                _exact_keys(dependency, {"id", "version"}, {"id", "version"}, dependency_label)
                _valid_id(dependency.get("id"), dependency_label + ".id")
                cls._version_key(dependency.get("version"))
                if dependency["id"] in dependency_ids:
                    raise ValueError("project lock contains a duplicate dependency")
                dependency_ids.add(dependency["id"])
            locked_manifest = root / "packages" / package_id / str(version) / "package.json"
            if not locked_manifest.is_file():
                raise ValueError("project lock package is not installed: {} {}".format(package_id, version))
            if manifest_sha256 is not None:
                actual_digest = hashlib.sha256(locked_manifest.read_bytes()).hexdigest()
                if actual_digest != manifest_sha256.lower():
                    raise ValueError("project lock manifest digest mismatch for {} {}".format(package_id, version))
            pins[package_id] = {
                "version": version,
                "manifest_sha256": manifest_sha256,
                "source_feed": source_feed,
                "dependencies": tuple(
                    (dependency["id"], dependency["version"]) for dependency in dependencies
                ),
            }
        for package_id, pin in pins.items():
            for dependency_id, dependency_version in pin["dependencies"]:
                dependency_pin = pins.get(dependency_id)
                if dependency_pin is None or dependency_pin["version"] != dependency_version:
                    raise ValueError(
                        "project lock dependency mismatch: {} requires {} {}".format(
                            package_id, dependency_id, dependency_version
                        )
                    )
        return pins, str(path)

    @staticmethod
    def _validate_sources(config):
        _exact_keys(config, {"schema_version", "sources"}, {"schema_version", "sources"}, "update source config")
        sources = config.get("sources")
        if config.get("schema_version") != 1 or not isinstance(sources, list) or len(sources) > MAX_SOURCES:
            raise ValueError("update source configuration is invalid or too large")
        seen = set()
        fields = {"id", "name", "url", "enabled", "trust", "auto_stage", "auto_activate", "sha256"}
        for index, source in enumerate(sources):
            label = "sources[{}]".format(index)
            _exact_keys(source, fields, fields - {"sha256"}, label)
            _valid_id(source.get("id"), label + ".id")
            if source["id"] in seen:
                raise ValueError("duplicate update source id {!r}".format(source["id"]))
            seen.add(source["id"])
            if not isinstance(source.get("name"), str) or not source["name"] or len(source["name"]) > 120:
                raise ValueError(label + ".name is invalid")
            if not isinstance(source.get("url"), str) or not source["url"] or len(source["url"]) > MAX_URL_CHARS:
                raise ValueError(label + ".url is invalid")
            try:
                parsed_url = urllib.parse.urlsplit(source["url"])
                _ = parsed_url.port
            except (TypeError, ValueError) as exc:
                raise ValueError(label + ".url is invalid") from exc
            if parsed_url.scheme:
                _valid_url(source["url"], label + ".url")
            elif parsed_url.netloc or parsed_url.query or parsed_url.fragment:
                raise ValueError(label + ".url relative path is invalid")
            for key in ("enabled", "auto_stage", "auto_activate"):
                if not isinstance(source.get(key), bool):
                    raise ValueError("{}.{} must be boolean".format(label, key))
            if source.get("auto_stage") or source.get("auto_activate"):
                raise ValueError("TouchDesigner updater sources must remain notify-only")
            if not isinstance(source.get("trust"), str) or source.get("trust") not in {"first_party", "community", "local"}:
                raise ValueError(label + ".trust is invalid")
            if source.get("sha256") is not None and (not isinstance(source["sha256"], str) or SHA256_RE.fullmatch(source["sha256"]) is None):
                raise ValueError(label + ".sha256 is invalid")
        return sources

    @classmethod
    def _reconcile_candidates(cls, candidates, locked):
        """Select one deterministic candidate per package across configured feeds.

        An exact source recorded in a project lock wins. Otherwise source trust is
        considered before version, so an untrusted feed cannot eclipse a first-party
        package merely by advertising a larger version. Equally ranked sources must
        agree on the bytes for an identical release identity.
        """

        by_package = {}
        for candidate in candidates:
            by_package.setdefault(candidate["id"], []).append(candidate)
        updates = []
        issues = []
        for package_id in sorted(by_package):
            options = by_package[package_id]
            pin = locked.get(package_id)
            locked_source = pin.get("source_feed") if pin else None
            if locked_source is not None:
                expected_source = _source_identity(locked_source)
                source_matches = [
                    item for item in options
                    if item["_source_identity"] == expected_source
                ]
                if not source_matches:
                    issues.append(
                        "{} has candidates only from sources other than its project lock".format(
                            package_id
                        )
                    )
                    continue
                options = source_matches
            else:
                highest_trust = max(TRUST_ORDER[item["source_trust"]] for item in options)
                options = [
                    item for item in options
                    if TRUST_ORDER[item["source_trust"]] == highest_trust
                ]

            highest_version = max(cls._version_key(item["available"]) for item in options)
            options = [
                item for item in options
                if cls._version_key(item["available"]) == highest_version
            ]
            exact_versions = {item["available"] for item in options}
            if len(exact_versions) != 1:
                issues.append(
                    "{} has ambiguous equal-precedence versions across selected sources".format(
                        package_id
                    )
                )
                continue
            byte_identities = {
                (item["manifest_sha256"], item["artifact_sha256"])
                for item in options
            }
            if len(byte_identities) != 1:
                issues.append(
                    "{} has conflicting digests across equally preferred sources".format(
                        package_id
                    )
                )
                continue
            selected = dict(sorted(options, key=lambda item: item["source"])[0])
            selected.pop("_source_identity", None)
            updates.append(selected)
        return updates, issues

    @staticmethod
    def _write_json_atomic(root, output_path, payload):
        root = Path(root).resolve(strict=True)
        output_path = Path(os.path.abspath(output_path))
        try:
            relative = output_path.relative_to(root)
        except ValueError as exc:
            raise ValueError("Update status path must stay inside the library root") from exc
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cursor = root
        for part in relative.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise ValueError("Update status path may not contain symbolic links")
        try:
            output_path.parent.resolve(strict=True).relative_to(root)
        except (OSError, ValueError) as exc:
            raise ValueError("Update status path must stay inside the library root") from exc
        descriptor, temporary_name = tempfile.mkstemp(prefix=".{}-".format(output_path.name), suffix=".tmp", dir=str(output_path.parent))
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                descriptor = None
                json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(str(temporary), str(output_path))
        finally:
            if descriptor is not None:
                os.close(descriptor)
            temporary.unlink(missing_ok=True)

    @classmethod
    def _worker_check(cls, root, channel, timeout, output_path, runtime=None, check_id=None):
        result = {"schema_version": 1, "check_id": check_id or secrets.token_hex(16), "checked_at": datetime.now(timezone.utc).isoformat(), "status": "complete", "updates": [], "errors": [], "sources_checked": 0, "project_lock": None, "truncated": False}
        try:
            if not isinstance(channel, str) or channel not in CHANNEL_ORDER:
                raise ValueError("selected update channel is invalid")
            runtime = runtime or {"os": platform.system(), "architecture": platform.machine(), "touchdesigner_build": None}
            source_path = root / "config" / "update_sources.json"
            config = _load_json_file(source_path, "update source config") if source_path.is_file() else {"schema_version": 1, "sources": []}
            sources = cls._validate_sources(config)
            installed = cls._installed_versions(root)
            locked, lock_path = cls._project_lock(root, runtime.get("project_folder"))
            result["project_lock"] = {"path": Path(lock_path).name, "packages": len(locked)} if lock_path else None
            candidates = []
            for source in sources:
                if not source["enabled"]:
                    continue
                result["sources_checked"] += 1
                try:
                    raw_url = source["url"]
                    parsed = urllib.parse.urlsplit(raw_url)
                    if not parsed.scheme:
                        candidate = (root / raw_url).resolve(strict=True)
                        candidate.relative_to(root.resolve(strict=True))
                        feed_url = candidate.as_uri()
                    else:
                        feed_url = raw_url
                    feed_data, feed_sha256, _final_source = cls._fetch_json_url(
                        feed_url,
                        timeout,
                        expected_sha256=source.get("sha256"),
                        file_root=root,
                    )
                    feed = cls._validate_feed(feed_data, source["id"])
                    for package in feed["packages"]:
                        package_id = package["id"]
                        installed_record = installed.get(package_id)
                        pin = locked.get(package_id)
                        baseline = pin["version"] if pin else (installed_record["version"] if installed_record else None)
                        eligible = []
                        for release in package["releases"]:
                            if release["yanked"] or CHANNEL_ORDER[release["channel"]] > CHANNEL_ORDER[channel]:
                                continue
                            if baseline is not None and cls._version_key(release["version"]) <= cls._version_key(baseline):
                                continue
                            compatible, compatibility_verified = cls._compatibility_report(
                                release["compatibility"], runtime
                            )
                            if not compatible:
                                continue
                            artifact = next(
                                (
                                    item for item in release["artifacts"]
                                    if _normalize_os(runtime.get("os", "")) in item["os"]
                                    and _normalize_arch(runtime.get("architecture", "")) in item["architectures"]
                                ),
                                None,
                            )
                            if artifact is not None:
                                eligible.append((release, artifact, compatibility_verified))
                        if not eligible:
                            continue
                        release, artifact, compatibility_verified = max(
                            eligible, key=lambda item: cls._version_key(item[0]["version"])
                        )
                        candidates.append({
                            "id": package_id,
                            "name": package["name"],
                            "installed": installed_record["version"] if installed_record else None,
                            "locked": pin["version"] if pin else None,
                            "available": release["version"],
                            "channel": release["channel"],
                            "requires_restart": release["requires_restart"],
                            "permissions_changed": bool(release.get("permissions_changed", False)),
                            "compatibility_verified": compatibility_verified,
                            "changelog": release["changelog"][:MAX_STATUS_CHANGELOG_CHARS],
                            "manifest_sha256": release["manifest_sha256"].lower(),
                            "artifact_sha256": artifact["sha256"].lower(),
                            "feed_sha256": feed_sha256,
                            "source": source["id"],
                            "source_trust": source["trust"],
                            "_source_identity": _source_identity(feed_url),
                        })
                except Exception as exc:
                    result["errors"].append({"source": source["id"], "error": _safe_error(exc)})
            reconciled, reconciliation_issues = cls._reconcile_candidates(candidates, locked)
            if len(reconciled) > MAX_STATUS_UPDATES:
                result["truncated"] = True
            result["updates"] = reconciled[:MAX_STATUS_UPDATES]
            if reconciliation_issues:
                summary = "; ".join(reconciliation_issues)
                result["errors"].append({
                    "source": "reconciliation",
                    "error": summary[:1000],
                })
        except Exception as exc:
            result["status"] = "failed"
            result["errors"].append({"source": "local", "error": _safe_error(exc)})
        while len((json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")) > MAX_LOCAL_JSON_BYTES and result["updates"]:
            result["updates"].pop()
            result["truncated"] = True
        cls._write_json_atomic(root, output_path, result)

    def CheckUpdates(self):
        if self._thread is not None and self._thread.is_alive():
            return False
        root = self._root()
        output = root / ".imagefx" / "update-status.json"
        self._check_id = secrets.token_hex(16)
        try:
            touchdesigner_build = app.build
        except (AttributeError, NameError):
            touchdesigner_build = None
        try:
            project_folder = project.folder
        except (AttributeError, NameError):
            project_folder = None
        runtime = {
            "os": platform.system(),
            "architecture": platform.machine(),
            "touchdesigner_build": touchdesigner_build,
            "project_folder": project_folder,
        }
        self.ownerComp.par.Status = "Checking for updates..."
        self.ownerComp.par.Lastcheck = ""
        self._thread = threading.Thread(target=self._worker_check, args=(root, self.ownerComp.par.Channel.eval(), float(self.ownerComp.par.Timeout), output, runtime, self._check_id), daemon=True, name="TDImageFXUpdateCheck")
        self._thread.start()
        run("op({!r}).Poll()".format(self.ownerComp.path), delayMilliSeconds=250, wallTime=True, delayRef=op.TDResources)
        return True

    def Poll(self):
        if self._thread is not None and self._thread.is_alive():
            run("op({!r}).Poll()".format(self.ownerComp.path), delayMilliSeconds=250, wallTime=True, delayRef=op.TDResources)
            return False
        status_path = self._root() / ".imagefx" / "update-status.json"
        try:
            result = _validate_status(_load_json_file(status_path, "update status"))
        except (OSError, ValueError) as exc:
            self.ownerComp.par.Status = "Update check failed: {}".format(_safe_error(exc))
            return False
        if self._check_id is not None and result.get("check_id") != self._check_id:
            self.ownerComp.par.Status = "Update check failed: stale or mismatched status"
            return False
        table = self.ownerComp.op("update_results")
        table.setSize(0, 0)
        table.appendRow(("id", "installed", "locked", "available", "channel", "compatibility_verified", "restart", "permissions_changed", "source", "source_trust", "changelog"))
        for item in result.get("updates", []):
            table.appendRow((item.get("id", ""), item.get("installed") or "not installed", item.get("locked") or "", item.get("available", ""), item.get("channel", ""), str(item.get("compatibility_verified", False)), str(item.get("requires_restart", False)), str(item.get("permissions_changed", False)), item.get("source", ""), item.get("source_trust", ""), item.get("changelog", "")))
        self.ownerComp.par.Lastcheck = result.get("checked_at", "")
        if result.get("truncated"):
            self.ownerComp.par.Status = "{} update(s) shown; results truncated".format(len(result.get("updates", [])))
        elif result.get("errors"):
            self.ownerComp.par.Status = "{} update(s), {} source error(s)".format(len(result.get("updates", [])), len(result["errors"]))
        elif result.get("sources_checked", 0) == 0:
            self.ownerComp.par.Status = "No enabled update sources"
        else:
            self.ownerComp.par.Status = "{} update(s) available".format(len(result.get("updates", [])))
        return True

    def StartAutoCheck(self):
        if not bool(self.ownerComp.par.Autocheck):
            return False
        if not self._scheduled:
            self._scheduled = True
            self._schedule_generation += 1
            generation = self._schedule_generation
            run("op({!r}).AutoTick({})".format(self.ownerComp.path, generation), delayMilliSeconds=1500, wallTime=True, delayRef=op.TDResources)
        return True

    def StopAutoCheck(self):
        self._schedule_generation += 1
        self._scheduled = False
        return True

    def AutoTick(self, generation=None):
        if generation is not None and generation != self._schedule_generation:
            return False
        self._scheduled = False
        if not bool(self.ownerComp.par.Autocheck):
            return False
        self.CheckUpdates()
        hours = max(float(self.ownerComp.par.Intervalhours), 1.0 / 60.0)
        self._scheduled = True
        run("op({!r}).AutoTick({})".format(self.ownerComp.path, self._schedule_generation), delayMilliSeconds=int(hours * 3600000), wallTime=True, delayRef=op.TDResources)
        return True
