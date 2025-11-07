"""Helpers to append capture warning/blocklist events to ops logs."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
import json
from typing import Any

from app.schemas import ManifestWarning
from app.settings import get_settings


def _normalize_warning(entry: Any) -> dict[str, Any]:
    if isinstance(entry, ManifestWarning):
        return entry.model_dump()
    if hasattr(entry, "model_dump"):
        return entry.model_dump()
    if is_dataclass(entry):
        return asdict(entry)
    if isinstance(entry, dict):
        return entry
    return {"code": str(entry)}


def append_warning_log(
    *,
    job_id: str,
    url: str,
    manifest: Any,
) -> None:
    """Append warning/blocklist events for ops review.

    Writes a JSON line containing job identifiers, timestamp, warning list, and
    blocklist stats. No-op when neither warnings nor blocklist hits exist.
    """

    warning_entries = getattr(manifest, "warnings", []) or []
    warnings = [_normalize_warning(entry) for entry in warning_entries]
    blocklist_hits = getattr(manifest, "blocklist_hits", {}) or {}
    if not warnings and not blocklist_hits:
        return

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "job_id": job_id,
        "url": url,
        "warnings": warnings,
        "blocklist_version": getattr(manifest, "blocklist_version", None),
        "blocklist_hits": blocklist_hits,
    }
    log_path = get_settings().logging.warning_log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record))
        handle.write("\n")
