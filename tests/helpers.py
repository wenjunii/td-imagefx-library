from __future__ import annotations

import copy
import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any


def manifest_data(
    version: str = "1.0.0",
    *,
    package_id: str = "tdimagefx.test.effect",
    kind: str = "effect",
    component: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "id": package_id,
        "name": "Test Effect",
        "version": version,
        "fx_api": "1.0",
        "kind": kind,
        "category": "test",
        "channel": "stable",
        "description": "A fixture package.",
        "publisher": "Tests",
        "license": "MIT",
        "entrypoints": {
            "shader": "shaders/effect.frag",
            "touchdesigner_component": component,
        },
        "inputs": [{"id": "image", "family": "TOP", "required": True}],
        "outputs": [{"id": "image", "family": "TOP"}],
        "parameters": [
            {"id": "mix", "name": "Mix", "type": "float", "default": 1.0, "min": 0.0, "max": 1.0}
        ],
        "compatibility": {
            "touchdesigner_min_build": 2022.2,
            "touchdesigner_max_build": None,
            "os": ["windows", "macos"],
            "architectures": ["x86_64", "arm64"],
        },
        "permissions": {"python": False, "filesystem": False, "network": False, "subprocess": False},
        "dependencies": [],
        "alpha_policy": "preserve",
        "resolution_policy": "input",
        "stateful": False,
        "tags": ["test"],
    }


def write_package_zip(
    path: Path,
    *,
    version: str = "1.0.0",
    package_id: str = "tdimagefx.test.effect",
    component: str | None = None,
    extra_entries: dict[str, bytes | str] | None = None,
) -> tuple[str, dict[str, Any]]:
    manifest = manifest_data(version, package_id=package_id, component=component)
    entries: dict[str, bytes | str] = {
        "package.json": json.dumps(manifest),
        "shaders/effect.frag": "// shader\nvoid main() {}\n",
    }
    if component:
        entries[component] = b"fake-tox"
    entries.update(extra_entries or {})
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return hashlib.sha256(path.read_bytes()).hexdigest(), manifest


def feed_data(artifact_url: str, artifact_sha256: str, artifact_size: int, *, version: str = "1.1.0") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "feed_id": "tdimagefx.test.feed",
        "generated_at": "2026-07-15T12:00:00Z",
        "channel": "stable",
        "packages": [
            {
                "id": "tdimagefx.test.effect",
                "name": "Test Effect",
                "kind": "effect",
                "releases": [
                    {
                        "version": version,
                        "channel": "stable",
                        "published_at": "2026-07-15T12:00:00Z",
                        "manifest_url": "https://example.test/package.json",
                        "manifest_sha256": "a" * 64,
                        "artifacts": [
                            {
                                "url": artifact_url,
                                "sha256": artifact_sha256,
                                "size_bytes": artifact_size,
                                "media_type": "application/zip",
                                "os": ["windows", "macos"],
                                "architectures": ["x86_64", "arm64"],
                            }
                        ],
                        "compatibility": {
                            "touchdesigner_min_build": 2022.2,
                            "touchdesigner_max_build": None,
                            "os": ["windows", "macos"],
                            "architectures": ["x86_64", "arm64"],
                        },
                        "requires_restart": False,
                        "yanked": False,
                        "changelog": "Test release",
                    }
                ],
            }
        ],
    }


def clone(value: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(value)
