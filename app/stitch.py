"""Stitch OCR chunks into Markdown with provenance markers."""

from __future__ import annotations

from typing import Iterable


def stitch_markdown(chunks: Iterable[str]) -> str:
    """Join OCR-derived Markdown segments until smarter heuristics land."""

    return "\n\n".join(chunks)
