from __future__ import annotations

from typing import Any, Mapping, Sequence, Tuple, TYPE_CHECKING

from prometheus_client import Counter, Histogram

if TYPE_CHECKING:  # pragma: no cover - typing only
    pass

_LATENCY_BUCKETS = (
    0.5,
    1,
    2,
    5,
    10,
    20,
    30,
    45,
    60,
    90,
    120,
    float("inf"),
)

CAPTURE_DURATION_SECONDS = Histogram(
    "mdwb_capture_duration_seconds",
    "Playwright capture duration (viewport sweep + screenshot).",
    buckets=_LATENCY_BUCKETS,
)
OCR_DURATION_SECONDS = Histogram(
    "mdwb_ocr_duration_seconds",
    "Total wall-clock time spent waiting for OCR responses.",
    buckets=_LATENCY_BUCKETS,
)
STITCH_DURATION_SECONDS = Histogram(
    "mdwb_stitch_duration_seconds",
    "Time spent stitching Markdown output.",
    buckets=_LATENCY_BUCKETS,
)
JOB_COMPLETIONS = Counter(
    "mdwb_job_completions_total",
    "Completed jobs partitioned by terminal state.",
    labelnames=("state",),
)
WARNING_COUNTER = Counter(
    "mdwb_capture_warnings_total",
    "Count of capture warnings emitted by heuristics.",
    labelnames=("code",),
)
BLOCKLIST_COUNTER = Counter(
    "mdwb_blocklist_hits_total",
    "Selectors hidden during capture, labeled by selector.",
    labelnames=("selector",),
)
SSE_HEARTBEAT_COUNTER = Counter(
    "mdwb_sse_heartbeat_total",
    "Heartbeats emitted on HTMX/CLI SSE streams (monitors idle gaps).",
)
_DENSITY_BUCKETS = (
    0.001,
    0.005,
    0.01,
    0.02,
    0.05,
    0.1,
    0.2,
    0.5,
    1.0,
    float("inf"),
)
DOM_ASSIST_DENSITY = Histogram(
    "mdwb_dom_assist_density",
    "Assist density (assists per tile) emitted by hybrid recovery.",
    buckets=_DENSITY_BUCKETS,
)
DOM_ASSIST_REASON_RATIO = Histogram(
    "mdwb_dom_assist_reason_ratio",
    "Per reason assist ratio (per tile when available, otherwise share of assists).",
    labelnames=("reason",),
    buckets=_DENSITY_BUCKETS,
)


def observe_manifest_metrics(manifest: Any) -> None:
    """Record duration + warning metrics from a manifest-like payload."""

    capture_ms = _extract_timing(manifest, "capture_ms")
    if capture_ms is not None:
        CAPTURE_DURATION_SECONDS.observe(capture_ms / 1000.0)

    ocr_ms = _extract_timing(manifest, "ocr_ms")
    if ocr_ms is not None:
        OCR_DURATION_SECONDS.observe(ocr_ms / 1000.0)

    stitch_ms = _extract_timing(manifest, "stitch_ms")
    if stitch_ms is not None:
        STITCH_DURATION_SECONDS.observe(stitch_ms / 1000.0)

    for code, count in _iter_warning_counts(manifest):
        WARNING_COUNTER.labels(code=code).inc(count)

    for selector, hits in _iter_blocklist_hits(manifest):
        BLOCKLIST_COUNTER.labels(selector=selector).inc(hits)

    summary = getattr(manifest, "dom_assist_summary", None)
    if summary is None and isinstance(manifest, Mapping):
        summary = manifest.get("dom_assist_summary")
    _observe_dom_assist_summary(summary)


def record_job_completion(state: str) -> None:
    """Increment the job completion counter for a terminal state."""

    JOB_COMPLETIONS.labels(state=state).inc()


def increment_sse_heartbeat() -> None:
    """Track SSE heartbeat emissions so alerting can detect stalls."""

    SSE_HEARTBEAT_COUNTER.inc()


def _observe_dom_assist_summary(summary: Mapping[str, Any] | None) -> None:
    if not isinstance(summary, Mapping):
        return
    density = summary.get("assist_density")
    if isinstance(density, (int, float)):
        DOM_ASSIST_DENSITY.observe(max(0.0, density))
    reason_counts = summary.get("reason_counts")
    if not isinstance(reason_counts, Sequence):
        return
    for entry in reason_counts:
        if not isinstance(entry, Mapping):
            continue
        reason = entry.get("reason")
        ratio = entry.get("ratio")
        if reason is None or not isinstance(ratio, (int, float)):
            continue
        DOM_ASSIST_REASON_RATIO.labels(reason=str(reason)).observe(max(0.0, ratio))


def _extract_timing(manifest: Any, field: str) -> float | None:
    value = getattr(manifest, field, None)
    if value is not None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if isinstance(manifest, Mapping):
        direct = manifest.get(field)
        if direct is not None:
            try:
                return float(direct)
            except (TypeError, ValueError):
                return None
    timings = getattr(manifest, "timings", None)
    if timings is not None:
        nested = getattr(timings, field, None)
        if nested is not None:
            try:
                return float(nested)
            except (TypeError, ValueError):
                return None
        if isinstance(timings, Mapping):
            nested = timings.get(field)
            if nested is not None:
                try:
                    return float(nested)
                except (TypeError, ValueError):
                    return None
    if isinstance(manifest, Mapping):
        timings = manifest.get("timings")
        if isinstance(timings, Mapping):
            nested = timings.get(field)
            if nested is not None:
                try:
                    return float(nested)
                except (TypeError, ValueError):
                    return None
    return None


def _iter_warning_counts(manifest: Any) -> Sequence[Tuple[str, float]]:
    entries = getattr(manifest, "warnings", None)
    if entries is None and isinstance(manifest, Mapping):
        entries = manifest.get("warnings")
    if not entries:
        return []
    results: list[Tuple[str, float]] = []
    for entry in entries:
        code = getattr(entry, "code", None)
        count = getattr(entry, "count", None)
        if code is None and isinstance(entry, Mapping):
            code = entry.get("code")
            count = entry.get("count")
        if code is None:
            continue
        results.append((str(code), float(count) if count is not None else 1.0))
    return results


def _iter_blocklist_hits(manifest: Any) -> Sequence[Tuple[str, float]]:
    hits = getattr(manifest, "blocklist_hits", None)
    if hits is None and isinstance(manifest, Mapping):
        hits = manifest.get("blocklist_hits")
    if not hits:
        return []
    results: list[Tuple[str, float]] = []
    if isinstance(hits, Mapping):
        items = hits.items()
    else:  # pragma: no cover - defensive
        items = []
    for selector, value in items:
        results.append((str(selector), float(value) if value is not None else 1.0))
    return results
