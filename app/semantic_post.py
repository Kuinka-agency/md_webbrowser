"""Optional semantic post-processing pass that cleans Markdown via an LLM."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Awaitable, Callable, Mapping
from urllib.parse import urlparse
import asyncio
import logging
import time

import httpx

from app.settings import SemanticPostSettings

LOGGER = logging.getLogger(__name__)

RequestFn = Callable[[str, dict[str, Any], dict[str, str], float], Awaitable[Mapping[str, Any]]]


class SemanticPostResult:
    """Return value describing the semantic correction stage."""

    __slots__ = ("markdown", "summary")

    def __init__(self, markdown: str, summary: dict[str, Any] | None) -> None:
        self.markdown = markdown
        self.summary = summary


async def apply_semantic_post(
    *,
    markdown: str,
    manifest: Any,
    job_id: str,
    settings: SemanticPostSettings,
    requester: RequestFn | None = None,
) -> SemanticPostResult:
    """Run the optional semantic fixer if it's enabled and properly configured."""

    if not settings.enabled:
        return SemanticPostResult(markdown, None)

    requester = requester or _post_semantic_payload
    summary: dict[str, Any] | None = None
    if not settings.endpoint:
        summary = _build_summary(
            status="skipped",
            settings=settings,
            provider=_provider_label(settings.endpoint),
            reason="missing_endpoint",
        )
        return SemanticPostResult(markdown, summary)

    if not markdown.strip():
        summary = _build_summary(
            status="skipped",
            settings=settings,
            provider=_provider_label(settings.endpoint),
            reason="empty_markdown",
        )
        return SemanticPostResult(markdown, summary)

    if settings.max_chars and len(markdown) > settings.max_chars:
        summary = _build_summary(
            status="skipped",
            settings=settings,
            provider=_provider_label(settings.endpoint),
            reason="exceeds_max_chars",
            extra={"max_chars": settings.max_chars, "observed_chars": len(markdown)},
        )
        return SemanticPostResult(markdown, summary)

    payload = {
        "job_id": job_id,
        "markdown": markdown,
        "model": settings.model,
        "manifest": _manifest_excerpt(manifest),
    }
    headers = {
        "Content-Type": "application/json",
    }
    if settings.api_key:
        headers["Authorization"] = settings.api_key

    provider = _provider_label(settings.endpoint)
    start = time.perf_counter()
    try:
        response = await requester(settings.endpoint, payload, headers, settings.timeout_ms / 1000.0)
    except Exception as exc:  # pragma: no cover - network surface
        LOGGER.warning("Semantic post-processing failed for %s: %s", job_id, exc)
        summary = _build_summary(
            status="error",
            settings=settings,
            provider=provider,
            error=str(exc),
        )
        return SemanticPostResult(markdown, summary)

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    new_markdown = _coerce_markdown(response.get("markdown"))
    if new_markdown is None:
        summary = _build_summary(
            status="error",
            settings=settings,
            provider=provider,
            error="missing_markdown",
            extra={"response": _safe_excerpt(response)},
        )
        return SemanticPostResult(markdown, summary)

    applied = new_markdown != markdown
    summary = _build_summary(
        status="success",
        settings=settings,
        provider=provider,
        latency_ms=elapsed_ms,
        applied=applied,
        delta_chars=len(new_markdown) - len(markdown),
        extra={
            "model": response.get("model") or settings.model,
            "token_usage": response.get("token_usage") or response.get("usage"),
            "reason": response.get("reason"),
            "notes": response.get("notes"),
        },
    )
    return SemanticPostResult(new_markdown, summary)


async def _post_semantic_payload(
    endpoint: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: float,
) -> Mapping[str, Any]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(endpoint, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()


def _build_summary(
    *,
    status: str,
    settings: SemanticPostSettings,
    provider: str,
    reason: str | None = None,
    error: str | None = None,
    latency_ms: int | None = None,
    applied: bool | None = None,
    delta_chars: int | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "enabled": settings.enabled,
        "status": status,
        "provider": provider,
    }
    if settings.model:
        summary["configured_model"] = settings.model
    if reason:
        summary["reason"] = reason
    if latency_ms is not None:
        summary["latency_ms"] = latency_ms
    if applied is not None:
        summary["applied"] = applied
    if delta_chars is not None:
        summary["delta_chars"] = delta_chars
    if error:
        summary["error"] = error[:300]
    if extra:
        for key, value in extra.items():
            if value is not None:
                summary[key] = value
    return summary


def _manifest_excerpt(manifest: Any) -> Mapping[str, Any] | None:
    if manifest is None:
        return None
    payload: Mapping[str, Any] | None = None
    if is_dataclass(manifest):
        payload = asdict(manifest)
    elif isinstance(manifest, Mapping):
        payload = manifest
    if not payload:
        return None
    excerpt: dict[str, Any] = {}
    for key in ("url", "tiles_total", "warnings", "dom_assist_summary", "blocklist_hits", "validation_failures"):
        value = payload.get(key)
        if value not in (None, "", []):
            excerpt[key] = value
    if "environment" in payload and isinstance(payload["environment"], Mapping):
        env = payload["environment"]
        excerpt["environment"] = {
            "cft_label": env.get("cft_label"),
            "cft_version": env.get("cft_version"),
            "browser_transport": env.get("browser_transport"),
            "ocr_model": env.get("ocr_model"),
        }
    return excerpt or None


def _coerce_markdown(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _provider_label(endpoint: str | None) -> str:
    if not endpoint:
        return "semantic-post"
    parsed = urlparse(endpoint)
    return parsed.hostname or parsed.netloc or "semantic-post"


def _safe_excerpt(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: value.get(key) for key in list(value.keys())[:5]}
    return value

