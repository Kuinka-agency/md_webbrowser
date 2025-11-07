"""Pydantic DTOs shared across endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class JobCreateRequest(BaseModel):
    """Payload clients submit to kick off a capture job."""

    url: str = Field(description="Target URL to capture")
    profile_id: str | None = Field(default=None, description="Browser profile identifier")


class JobSnapshotResponse(BaseModel):
    """Lightweight job view for polling and SSE streaming."""

    id: str
    state: str
    url: str
