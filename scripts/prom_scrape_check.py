#!/usr/bin/env python3
"""Quick health check for the Prometheus metrics endpoint."""

from __future__ import annotations

import sys
from typing import Optional

import httpx

from scripts import mdwb_cli


def main() -> None:
    settings = mdwb_cli._resolve_settings(None)  # reuse CLI env loader
    base_port = settings.base_url.rstrip("/").split(":")[-1]
    exporter_port = mdwb_cli.config("PROMETHEUS_PORT", default=base_port)
    urls = [
        f"{settings.base_url.rstrip('/')}/metrics",
        f"http://localhost:{exporter_port}/metrics",
    ]
    client = httpx.Client(timeout=5)
    for url in urls:
        try:
            response = client.get(url)
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            print(f"❌ metrics scrape failed: {url} ({exc})")
            sys.exit(1)
        else:
            print(f"✅ metrics scrape ok: {url}")
    client.close()


if __name__ == "__main__":
    main()
