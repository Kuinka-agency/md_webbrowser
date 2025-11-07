"""sqlite-vec helpers for section embeddings."""

from __future__ import annotations

from typing import Sequence


def upsert_embeddings(*, run_id: str, sections: Sequence[list[float]]) -> None:
    """Placeholder for sqlite-vec insert logic."""

    raise NotImplementedError("upsert_embeddings to be implemented in later milestone")
