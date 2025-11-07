"""Persistence layer for artifacts, manifests, and sqlite-vec metadata."""

from __future__ import annotations

from pathlib import Path


def cache_root() -> Path:
    """Return the root directory where capture artifacts should live."""

    return Path(".cache")
