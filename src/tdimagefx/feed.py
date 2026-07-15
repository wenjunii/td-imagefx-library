"""Constrained HTTPS and local-file fetching for update metadata/artifacts."""

from __future__ import annotations

import hashlib
import os
import re
import ssl
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from urllib.parse import unquote, urlsplit, urlunsplit
from urllib.request import url2pathname

from .errors import FeedError, SecurityError, ValidationError
from .jsonutil import loads_json
from .paths import is_relative_to
from .registry import UpdateFeed


DEFAULT_FEED_LIMIT = 2 * 1024 * 1024
DEFAULT_ARTIFACT_LIMIT = 256 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class SourcePolicy:
    allow_file: bool = False
    file_root: Path | None = None
    allowed_https_hosts: frozenset[str] | None = None
    timeout_seconds: float = 15.0
    user_agent: str = "tdimagefx/0.2"


@dataclass(frozen=True, slots=True)
class FetchResult:
    source: str
    final_source: str
    sha256: str
    size_bytes: int


def redact_source_url(value: str) -> str:
    """Remove query tokens and fragments before persisting a source URL."""

    parsed = urlsplit(value)
    if parsed.scheme.lower() == "https":
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    return value


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, policy: SourcePolicy) -> None:
        super().__init__()
        self._policy = policy

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):  # type: ignore[no-untyped-def]
        _validate_https_url(new_url, self._policy)
        return super().redirect_request(request, file_pointer, code, message, headers, new_url)


def _is_windows_path(value: str) -> bool:
    return re.match(r"^[A-Za-z]:[\\/]", value) is not None or value.startswith("\\\\")


def _local_path(source: str | os.PathLike[str], policy: SourcePolicy) -> Path | None:
    raw = os.fspath(source)
    parsed = urlsplit(raw)
    if _is_windows_path(raw) or parsed.scheme == "":
        candidate = Path(raw)
    elif parsed.scheme.lower() == "file":
        if parsed.username or parsed.password:
            raise SecurityError("file URL must not contain credentials")
        if parsed.netloc not in {"", "localhost"}:
            raise SecurityError("remote file URLs are not allowed")
        if parsed.query or parsed.fragment:
            raise SecurityError("file URL must not contain query or fragment data")
        candidate = Path(url2pathname(unquote(parsed.path)))
    else:
        return None
    if not policy.allow_file:
        raise SecurityError("local update sources are disabled; explicitly enable file access")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise FeedError(f"cannot resolve local source {candidate}: {exc}") from exc
    if policy.file_root is not None:
        try:
            root = policy.file_root.resolve(strict=True)
        except OSError as exc:
            raise FeedError(f"cannot resolve allowed file root {policy.file_root}: {exc}") from exc
        if not is_relative_to(resolved, root):
            raise SecurityError(f"local source {resolved} escapes allowed root {root}")
    if not resolved.is_file():
        raise FeedError(f"local source {resolved} is not a regular file")
    return resolved


def _validate_https_url(source: str, policy: SourcePolicy) -> None:
    parsed = urlsplit(source)
    if parsed.scheme.lower() != "https":
        raise SecurityError("remote update sources must use HTTPS")
    if not parsed.hostname:
        raise SecurityError("HTTPS source must include a host")
    if parsed.username or parsed.password:
        raise SecurityError("HTTPS source must not contain URL credentials")
    if policy.allowed_https_hosts is not None and parsed.hostname.lower() not in {
        host.lower() for host in policy.allowed_https_hosts
    }:
        raise SecurityError(f"HTTPS host {parsed.hostname!r} is not allow-listed")


def _copy_limited(
    source: BinaryIO,
    destination: BinaryIO,
    *,
    max_bytes: int,
    expected_size: int | None,
) -> tuple[int, str]:
    digest = hashlib.sha256()
    total = 0
    while True:
        chunk = source.read(min(1024 * 1024, max_bytes - total + 1))
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise SecurityError(f"download exceeds the {max_bytes}-byte limit")
        destination.write(chunk)
        digest.update(chunk)
    if expected_size is not None and total != expected_size:
        raise SecurityError(f"download size {total} does not match expected size {expected_size}")
    return total, digest.hexdigest()


def download_source(
    source: str | os.PathLike[str],
    destination: str | os.PathLike[str],
    *,
    policy: SourcePolicy = SourcePolicy(),
    expected_sha256: str | None = None,
    expected_size: int | None = None,
    max_bytes: int = DEFAULT_ARTIFACT_LIMIT,
) -> FetchResult:
    """Fetch to a file atomically, allowing only HTTPS or explicitly enabled files."""

    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    if expected_size is not None and (expected_size < 0 or expected_size > max_bytes):
        raise SecurityError("expected size is outside the configured download limit")
    normalized_hash = expected_sha256.lower() if expected_sha256 else None
    if normalized_hash is not None and re.fullmatch(r"[0-9a-f]{64}", normalized_hash) is None:
        raise ValidationError("Expected SHA-256 digest is invalid")

    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".download", dir=target.parent)
    temporary = Path(temporary_name)
    final_source = os.fspath(source)
    try:
        with os.fdopen(descriptor, "wb") as output:
            local = _local_path(source, policy)
            if local is not None:
                size = local.stat().st_size
                if size > max_bytes:
                    raise SecurityError(f"local source exceeds the {max_bytes}-byte limit")
                with local.open("rb") as input_file:
                    actual_size, actual_hash = _copy_limited(
                        input_file,
                        output,
                        max_bytes=max_bytes,
                        expected_size=expected_size,
                    )
                final_source = local.as_uri()
            else:
                raw_source = os.fspath(source)
                _validate_https_url(raw_source, policy)
                request = urllib.request.Request(raw_source, headers={"User-Agent": policy.user_agent, "Accept-Encoding": "identity"})
                try:
                    opener = urllib.request.build_opener(
                        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
                        _SafeRedirectHandler(policy),
                    )
                    response = opener.open(request, timeout=policy.timeout_seconds)
                except (urllib.error.URLError, TimeoutError, OSError) as exc:
                    raise FeedError(f"could not fetch {raw_source}: {exc}") from exc
                with response:
                    final_source = response.geturl()
                    _validate_https_url(final_source, policy)
                    status = getattr(response, "status", 200)
                    if status != 200:
                        raise FeedError(f"update source returned HTTP {status}")
                    content_encoding = response.headers.get("Content-Encoding")
                    if content_encoding not in {None, "", "identity"}:
                        raise SecurityError(f"unsupported Content-Encoding {content_encoding!r}")
                    content_length = response.headers.get("Content-Length")
                    if content_length is not None:
                        try:
                            announced = int(content_length)
                        except ValueError as exc:
                            raise SecurityError("invalid Content-Length response header") from exc
                        if announced < 0 or announced > max_bytes:
                            raise SecurityError("announced download size exceeds the configured limit")
                        if expected_size is not None and announced != expected_size:
                            raise SecurityError("announced download size does not match expected size")
                    actual_size, actual_hash = _copy_limited(
                        response,
                        output,
                        max_bytes=max_bytes,
                        expected_size=expected_size,
                    )
            output.flush()
            os.fsync(output.fileno())
        if normalized_hash is not None and actual_hash != normalized_hash:
            raise SecurityError(f"SHA-256 mismatch: expected {normalized_hash}, got {actual_hash}")
        os.replace(temporary, target)
        return FetchResult(os.fspath(source), final_source, actual_hash, actual_size)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def fetch_bytes(
    source: str | os.PathLike[str],
    *,
    policy: SourcePolicy = SourcePolicy(),
    expected_sha256: str | None = None,
    max_bytes: int = DEFAULT_FEED_LIMIT,
) -> tuple[bytes, FetchResult]:
    with tempfile.TemporaryDirectory(prefix="tdimagefx-feed-") as directory:
        destination = Path(directory, "payload")
        result = download_source(
            source,
            destination,
            policy=policy,
            expected_sha256=expected_sha256,
            max_bytes=max_bytes,
        )
        return destination.read_bytes(), result


def load_update_feed(
    source: str | os.PathLike[str],
    *,
    policy: SourcePolicy = SourcePolicy(),
    expected_sha256: str | None = None,
    max_bytes: int = DEFAULT_FEED_LIMIT,
) -> tuple[UpdateFeed, FetchResult]:
    payload, fetch_result = fetch_bytes(
        source,
        policy=policy,
        expected_sha256=expected_sha256,
        max_bytes=max_bytes,
    )
    try:
        data = loads_json(payload, source=f"update feed {source}")
        return UpdateFeed.from_data(data), fetch_result
    except ValidationError as exc:
        raise FeedError(str(exc)) from exc
