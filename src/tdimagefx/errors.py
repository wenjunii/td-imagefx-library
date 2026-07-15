"""Typed errors used by the public API and CLI."""

from __future__ import annotations

from collections.abc import Iterable


class ImageFxError(Exception):
    """Base class for expected user-facing failures."""


class ValidationError(ImageFxError):
    """A document failed structural or semantic validation."""

    def __init__(self, message: str, issues: Iterable[str] = ()) -> None:
        self.message = message
        self.issues = tuple(issues)
        detail = "\n".join(f"- {item}" for item in self.issues)
        super().__init__(f"{message}\n{detail}" if detail else message)


class SecurityError(ImageFxError):
    """Untrusted input violated a security boundary."""


class FeedError(ImageFxError):
    """An update feed could not be fetched or decoded safely."""


class CompatibilityError(ImageFxError):
    """A package is incompatible with the selected runtime."""


class StateError(ImageFxError):
    """Activation or lockfile state could not be changed safely."""
