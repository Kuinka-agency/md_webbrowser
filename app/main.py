"""Entry point for the FastAPI application."""

from fastapi import FastAPI

app = FastAPI(title="Markdown Web Browser")


@app.get("/health", tags=["health"])  # placeholder route until real handlers land
async def healthcheck() -> dict[str, str]:
    """Return a simple status useful for smoke tests."""
    return {"status": "ok"}
