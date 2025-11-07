# Configuration & Secrets (Decouple-first)
_Last updated: 2025-11_

All settings come from `.env` via **python-decouple**. Never read env vars directly and never overwrite `.env`.

```python
from decouple import Config as DecoupleConfig, RepositoryEnv
decouple_config = DecoupleConfig(RepositoryEnv(".env"))
API_BASE_URL = decouple_config("API_BASE_URL", default="http://localhost:8000")
````

## Required Keys

| Key                | Purpose                               | Example                 | Manifest Echo           |
| ------------------ | ------------------------------------- | ----------------------- | ----------------------- |
| `OLMOCR_SERVER`    | Base URL for OCR service              | `https://…`             | `ocr.server`            |
| `OLMOCR_API_KEY`   | Token for hosted OCR                  | `sk-…`                  | `ocr.provider="remote"` |
| `OLMOCR_MODEL`     | Default model policy key              | `olmOCR-2-7B-1025-FP8`  | `ocr.model`             |
| `OCR_LOCAL_URL`    | vLLM/SGLang local endpoint (optional) | `http://127.0.0.1:8001` | `ocr.provider="local"`  |
| `CACHE_ROOT`       | Root for content-addressed cache      | `.cache`                | `cache.root`            |
| `HTTP2_ENABLE`     | Enable HTTP/2 to OCR host             | `true`                  | `net.http2=true`        |
| `OCR_MAX_INFLIGHT` | Upper bound for tile concurrency      | `8`                     | `ocr.max_inflight`      |
| `RATE_BUCKET_QPS`  | Token-bucket target rate per host     | `6`                     | `net.rate.bucket_qps`   |
| `CFT_CHANNEL`      | CfT channel (e.g. `Stable`)           | `Stable`                | `browser.cft_channel`   |
| `CFT_BUILD`        | Exact CfT build                       | `130.0.6723.69`         | `browser.cft_build`     |

**HTTP/2** is strongly recommended when posting many tiles to the same host. Enable in the OCR client using `httpx.AsyncClient(http2=True)`.

## Recommended Defaults

* Viewport `1280×2000`, `deviceScaleFactor=2`, `colorScheme="light"`, `reduced_motion="reduce"`.
* Chunked capture threshold `total_scroll_height > 12000` → switch from single full-page to sweep.
* Tiling: overlap `≈120 px`, longest side `≤1288 px` for OCR.

## Conditional Requests (Cache)

Always attempt conditional HEAD/GET with `ETag`/`Last-Modified` before a fresh capture. On **304**, reuse the last run’s artifacts.

## Observability

* Expose `/metrics` with **prometheus-fastapi-instrumentator** (p50/p95 per stage, 429s, 5xx).
* Add OpenTelemetry FastAPI instrumentation for traces across NAVIGATING/SCROLLING/CAPTURING/TILING/OCR/STITCHING.