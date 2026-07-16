"""Command-line interface for validation, discovery, staging, and activation."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

from . import __version__
from .archive import StageLimits, stage_package
from .compatibility import RuntimeContext, normalize_architecture, normalize_os
from .errors import ImageFxError, ValidationError
from .feed import SourcePolicy, load_update_feed, redact_source_url
from .jsonutil import load_json
from .lockfile import load_lockfile
from .manifest import load_manifest
from .registry import LocalRegistry, UpdateFeed, load_local_registry
from .state import ActiveState, activate_package, load_active_state, rollback_package


def _emit(value: Any, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))
    elif isinstance(value, str):
        print(value)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                print("  ".join(f"{key}={val}" for key, val in item.items()))
            else:
                print(item)
    elif isinstance(value, dict):
        print("  ".join(f"{key}={val}" for key, val in value.items()))
    else:
        print(value)


def _policy(args: argparse.Namespace) -> SourcePolicy:
    hosts = frozenset(args.allow_host) if getattr(args, "allow_host", None) else None
    root = Path(args.file_root) if getattr(args, "file_root", None) else None
    return SourcePolicy(
        allow_file=bool(getattr(args, "allow_file", False) or root is not None),
        file_root=root,
        allowed_https_hosts=hosts,
        timeout_seconds=getattr(args, "timeout", 15.0),
    )


def _add_source_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--allow-file", action="store_true", help="explicitly allow a local path or file: URL")
    parser.add_argument("--file-root", type=Path, help="limit local sources to this resolved directory")
    parser.add_argument("--allow-host", action="append", default=[], help="allow-list an HTTPS host; repeat as needed")
    parser.add_argument("--timeout", type=float, default=15.0, help="network timeout in seconds (default: 15)")
    parser.add_argument("--expected-feed-id", help="bind the source to this exact feed_id")


def _document_kind(data: dict[str, Any]) -> str:
    if "entrypoints" in data and "version" in data and "id" in data:
        return "package"
    if "feed_id" in data:
        return "feed"
    if "library_root" in data and "updated_at" in data:
        return "registry"
    if "active_packages" in data and "revision" in data:
        return "state"
    if "fx_api" in data and "touchdesigner_build" in data and "packages" in data:
        return "lock"
    raise ValidationError("Cannot infer JSON document type", ["pass --type explicitly"])


def _validate_file(path: Path, kind: str) -> dict[str, Any]:
    inferred = _document_kind(load_json(path)) if kind == "auto" else kind
    if inferred == "package":
        document = load_manifest(path)
        summary = {"id": document.id, "version": str(document.version), "kind": document.kind}
    elif inferred == "feed":
        document = UpdateFeed.from_data(load_json(path))
        summary = {"feed_id": document.feed_id, "packages": len(document.packages)}
    elif inferred == "registry":
        document = LocalRegistry.from_data(load_json(path))
        summary = {"library_root": document.library_root, "packages": len(document.packages)}
    elif inferred == "lock":
        document = load_lockfile(path)
        summary = {"packages": len(document.packages), "fx_api": document.fx_api}
    elif inferred == "state":
        document = ActiveState.from_data(load_json(path))
        summary = {"revision": document.revision, "active_packages": len(document.active_packages)}
    else:  # pragma: no cover - argparse constrains this
        raise ValidationError(f"Unknown document type {inferred}")
    return {"path": str(path), "type": inferred, "valid": True, **summary}


def _cmd_validate(args: argparse.Namespace) -> int:
    targets: list[Path] = []
    for raw_target in args.targets:
        target = Path(raw_target)
        if target.is_dir():
            targets.extend(sorted(target.rglob("package.json")))
        else:
            targets.append(target)
    if not targets:
        raise ValidationError("No JSON documents found to validate")
    results = [_validate_file(path, args.type) for path in targets]
    _emit(results, as_json=args.json)
    return 0


def _cmd_catalog(args: argparse.Namespace) -> int:
    if args.type == "registry":
        registry = load_local_registry(args.source)
        rows: list[dict[str, Any]] = []
        for package_id, versions in sorted(registry.packages.items()):
            for installed in sorted(versions, key=lambda item: item.version, reverse=True):
                rows.append(
                    {
                        "id": package_id,
                        "version": str(installed.version),
                        "status": installed.status,
                        "verification": installed.integrity.get("verification"),
                    }
                )
    else:
        feed, fetch = load_update_feed(
            args.source,
            policy=_policy(args),
            expected_sha256=args.feed_sha256,
            expected_feed_id=args.expected_feed_id,
        )
        rows = list(feed.catalog())
        if args.json:
            _emit(
                {
                    "feed": {
                        "id": feed.feed_id,
                        "sha256": fetch.sha256,
                        "source": redact_source_url(fetch.final_source),
                    },
                    "packages": rows,
                },
                as_json=True,
            )
            return 0
    _emit(rows, as_json=args.json)
    return 0


def _runtime(args: argparse.Namespace) -> RuntimeContext:
    current = RuntimeContext.current()
    return RuntimeContext(
        operating_system=normalize_os(args.os or current.operating_system),
        architecture=normalize_architecture(args.architecture or current.architecture),
        python_version=args.python_version or current.python_version,
        touchdesigner_build=args.touchdesigner_build,
        renderer=args.renderer,
        gpu_features=frozenset(args.gpu_feature),
    )


def _installed_versions(args: argparse.Namespace) -> dict[str, Any]:
    if args.lock:
        return load_lockfile(args.lock).versions()
    if args.registry:
        return load_local_registry(args.registry).installed_map()
    if args.state:
        state = load_active_state(args.state)
        return {package.id: package.version for package in state.active_packages}
    return {}


def _cmd_check(args: argparse.Namespace) -> int:
    feed, fetch = load_update_feed(
        args.source,
        policy=_policy(args),
        expected_sha256=args.feed_sha256,
        expected_feed_id=args.expected_feed_id,
    )
    candidates = feed.updates(
        _installed_versions(args),
        _runtime(args),
        channel=args.channel,
        include_new=not args.installed_only,
        strict_compatibility=args.strict_compatibility,
    )
    rows = [candidate.to_dict() for candidate in candidates]
    if args.json:
        _emit(
            {
                "feed_id": feed.feed_id,
                "feed_sha256": fetch.sha256,
                "updates": rows,
                "count": len(rows),
            },
            as_json=True,
        )
    elif not rows:
        print("No compatible updates or new packages found.")
    else:
        _emit(rows, as_json=False)
    return 0


def _cmd_stage(args: argparse.Namespace) -> int:
    limits = StageLimits(
        max_archive_bytes=args.max_archive_bytes,
        max_files=args.max_files,
        max_uncompressed_bytes=args.max_uncompressed_bytes,
        max_file_bytes=args.max_file_bytes,
        max_compression_ratio=args.max_compression_ratio,
    )
    result = stage_package(
        args.source,
        args.store,
        expected_sha256=args.sha256,
        expected_size=args.size,
        expected_id=args.package_id,
        expected_version=args.package_version,
        expected_manifest_sha256=args.manifest_sha256,
        policy=_policy(args),
        limits=limits,
        registry_path=args.registry,
        feed_url=args.feed_url,
        feed_id=args.source_feed_id,
        feed_sha256=args.source_feed_sha256,
    )
    _emit(result.to_dict(), as_json=args.json)
    return 0


def _cmd_activate(args: argparse.Namespace) -> int:
    result = activate_package(
        args.state,
        args.store,
        args.package_id,
        args.version,
        expected_artifact_sha256=args.sha256,
        requires_restart=args.requires_restart,
        runtime=_runtime(args),
        supported_fx_api=args.fx_api,
        strict_compatibility=args.strict_compatibility,
    )
    active = result.active(args.package_id)
    _emit(
        {
            "id": args.package_id,
            "version": str(active.version) if active else None,
            "status": active.status if active else None,
            "revision": result.revision,
            "last_good_revision": result.last_good_revision,
        },
        as_json=args.json,
    )
    return 0


def _cmd_rollback(args: argparse.Namespace) -> int:
    result = rollback_package(args.state, args.store, args.package_id)
    active = result.active(args.package_id)
    _emit(
        {
            "id": args.package_id,
            "version": str(active.version) if active else None,
            "status": active.status if active else None,
            "revision": result.revision,
        },
        as_json=args.json,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tdimagefx", description=__doc__)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate package/state/registry JSON")
    validate.add_argument("targets", nargs="+", help="JSON files or package directories")
    validate.add_argument("--type", choices=("auto", "package", "feed", "registry", "lock", "state"), default="auto")
    validate.add_argument("--json", action="store_true")
    validate.set_defaults(handler=_cmd_validate)

    catalog = subparsers.add_parser("catalog", help="list releases from an update feed or local registry")
    catalog.add_argument("source")
    catalog.add_argument("--type", choices=("feed", "registry"), default="feed")
    catalog.add_argument("--feed-sha256")
    catalog.add_argument("--json", action="store_true")
    _add_source_options(catalog)
    catalog.set_defaults(handler=_cmd_catalog)

    check = subparsers.add_parser("check", help="check an update feed for compatible releases")
    check.add_argument("source")
    installed = check.add_mutually_exclusive_group()
    installed.add_argument("--lock", type=Path)
    installed.add_argument("--registry", type=Path)
    installed.add_argument("--state", type=Path)
    check.add_argument("--channel", choices=("stable", "beta", "experimental"), default="stable")
    check.add_argument("--installed-only", action="store_true", help="do not report entirely new packages")
    check.add_argument("--strict-compatibility", action="store_true", help="reject releases when runtime details are unknown")
    check.add_argument("--os", choices=("windows", "macos"))
    check.add_argument("--architecture", choices=("x86_64", "arm64"))
    check.add_argument("--python-version")
    check.add_argument("--touchdesigner-build")
    check.add_argument("--renderer")
    check.add_argument("--gpu-feature", action="append", default=[])
    check.add_argument("--feed-sha256")
    check.add_argument("--json", action="store_true")
    _add_source_options(check)
    check.set_defaults(handler=_cmd_check)

    stage = subparsers.add_parser("stage", help="verify and install an immutable package ZIP")
    stage.add_argument("source")
    stage.add_argument("--store", type=Path, required=True)
    stage.add_argument("--sha256", required=True)
    stage.add_argument("--size", type=int)
    stage.add_argument("--id", dest="package_id")
    stage.add_argument("--package-version")
    stage.add_argument("--manifest-sha256", help="expected package.json digest from the trusted feed")
    stage.add_argument("--registry", type=Path)
    stage.add_argument("--feed-url")
    stage.add_argument("--source-feed-id", help="feed_id that selected this artifact")
    stage.add_argument("--source-feed-sha256", help="digest of the feed that selected this artifact")
    stage.add_argument("--max-archive-bytes", type=int, default=256 * 1024 * 1024)
    stage.add_argument("--max-files", type=int, default=4096)
    stage.add_argument("--max-uncompressed-bytes", type=int, default=1024 * 1024 * 1024)
    stage.add_argument("--max-file-bytes", type=int, default=256 * 1024 * 1024)
    stage.add_argument("--max-compression-ratio", type=float, default=200.0)
    stage.add_argument("--json", action="store_true")
    _add_source_options(stage)
    stage.set_defaults(handler=_cmd_stage)

    activate = subparsers.add_parser("activate", help="select a staged immutable package version")
    activate.add_argument("package_id")
    activate.add_argument("version")
    activate.add_argument("--store", type=Path, required=True)
    activate.add_argument("--state", type=Path, required=True)
    activate.add_argument("--sha256")
    activate.add_argument("--requires-restart", action=argparse.BooleanOptionalAction, default=None)
    activate.add_argument("--fx-api", default="1.0", help="FX adapter API provided by the host (default: 1.0)")
    activate.add_argument("--strict-compatibility", action="store_true")
    activate.add_argument("--os", choices=("windows", "macos"))
    activate.add_argument("--architecture", choices=("x86_64", "arm64"))
    activate.add_argument("--python-version")
    activate.add_argument("--touchdesigner-build")
    activate.add_argument("--renderer")
    activate.add_argument("--gpu-feature", action="append", default=[])
    activate.add_argument("--json", action="store_true")
    activate.set_defaults(handler=_cmd_activate)

    rollback = subparsers.add_parser("rollback", help="restore the previous exact version")
    rollback.add_argument("package_id")
    rollback.add_argument("--store", type=Path, required=True)
    rollback.add_argument("--state", type=Path, required=True)
    rollback.add_argument("--json", action="store_true")
    rollback.set_defaults(handler=_cmd_rollback)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except ImageFxError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("error: interrupted", file=sys.stderr)
        return 130
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
