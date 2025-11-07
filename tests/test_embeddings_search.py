from __future__ import annotations

# ruff: noqa: E402  # test needs to monkeypatch pyvips before importing app modules

from datetime import datetime, timezone
from pathlib import Path
import sys
import types

fake_pyvips = types.ModuleType("pyvips")
setattr(fake_pyvips, "Image", object)
sys.modules.setdefault("pyvips", fake_pyvips)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from app.embeddings import EMBEDDING_DIM, SectionEmbedding, upsert_embeddings
from app.store import StorageConfig, Store


def _vector(primary: float) -> list[float]:
    vec = [0.0] * EMBEDDING_DIM
    vec[0] = primary
    vec[1] = 1.0 - primary
    return vec


def test_store_embedding_search_ranks_best_match(tmp_path):
    config = StorageConfig(cache_root=tmp_path / "cache", db_path=tmp_path / "runs.db")
    store = Store(config)
    store.allocate_run(job_id="run-1", url="https://example.com", started_at=datetime.now(timezone.utc))

    with store.session() as session:
        upsert_embeddings(
            session=session,
            run_id="run-1",
            sections=[
                SectionEmbedding(section_id="intro", tile_start=0, tile_end=2, vector=_vector(0.9)),
                SectionEmbedding(section_id="details", tile_start=3, tile_end=5, vector=_vector(0.1)),
            ],
        )

    total, matches = store.search_section_embeddings(job_id="run-1", vector=_vector(0.92), top_k=2)

    assert total == 2
    assert matches
    assert matches[0].section_id == "intro"
    assert matches[0].similarity >= matches[-1].similarity
