"""
Agent starter helpers and sample scripts.

These modules intentionally reuse the existing mdwb_cli plumbing so agent
builders can import lightweight helpers without re-implementing auth,
HTTP clients, or polling logic.
"""

from __future__ import annotations

__all__ = ["shared"]

