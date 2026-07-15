"""Core package-management primitives for the TouchDesigner Image FX library."""

from .compatibility import CompatibilityReport, RuntimeContext, check_compatibility, check_fx_api, check_package_compatibility
from .errors import (
    CompatibilityError,
    FeedError,
    ImageFxError,
    SecurityError,
    StateError,
    ValidationError,
)
from .lockfile import LockPin, Lockfile, load_lockfile, resolve_lockfile, write_lockfile
from .manifest import PackageManifest, load_manifest
from .semver import Version, VersionSpec

__all__ = [
    "CompatibilityError",
    "CompatibilityReport",
    "FeedError",
    "ImageFxError",
    "LockPin",
    "Lockfile",
    "PackageManifest",
    "RuntimeContext",
    "SecurityError",
    "StateError",
    "ValidationError",
    "Version",
    "VersionSpec",
    "check_compatibility",
    "check_fx_api",
    "check_package_compatibility",
    "load_lockfile",
    "load_manifest",
    "resolve_lockfile",
    "write_lockfile",
]

__version__ = "0.1.0"
