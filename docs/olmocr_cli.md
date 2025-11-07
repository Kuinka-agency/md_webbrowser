# olmOCR CLI Usage & Reproduction Guide
_Last updated: 2025-11_

This CLI standardizes remote/local OCR runs for smoke, latency spot-checks, and reproducible bug reports.

## Why a CLI?
- Ensures every run logs **model policy**, **tile geometry**, **concurrency**, and **CfT/Playwright versions** the same way as the web app.
- Makes “re-run with different OCR policy” trivial without touching the server.

## Commands

### 1) Inspect environment
````

uv run scripts/olmocr_cli.py show-env

```
- Prints OCR server, HTTP/2 enabled, model policy, token-bucket settings, CfT/Playwright versions.

### 2) Run OCR for one URL
```

uv run scripts/olmocr_cli.py run 
--url [https://example.com/article](https://example.com/article) 
--tiles-long-side 1288 --overlap 120 
--concurrency 6 --http2 true 
--ocr.server $OLMOCR_SERVER --ocr.key $OLMOCR_API_KEY --ocr.model olmOCR-2-7B-1025-FP8 
--out-dir benchmarks/runs/$(date +%Y%m%d_%H%M%S)

```
- Uses viewport sweep; encodes tiles via **pyvips**; posts with HTTP/2. 

### 3) Latency micro-bench
```

uv run scripts/olmocr_cli.py bench 
--url-file benchmarks/urls/medium.txt 
--repeats 3 --shuffle 
--report benchmarks/weekly_summary.json

```

## Exit Codes
- `0` success, `10` partial (some tiles terminal-failed), `20` upstream unavailable.

## Error Policy
- Retry 408/429/5xx (exponential backoff + jitter); treat other 4xx as terminal per tile. 

## Model Policies
- The CLI reads `docs/models.yaml`. Default policy **olmOCR‑2‑7B‑1025‑FP8** has longest side 1288 px and FP8 preferred on server. See AI2 documentation and model card. 

## Repro Bundles
- Each run writes: `artifact/tiles/*.png`, `out.md`, `links.json`, `manifest.json`.
- Always attach the bundle in bug reports; **never delete** artifacts without explicit written approval.
```

---

## `docs/models.yaml` (template)

```yaml
# OCR Model Policies (load at startup)
# Each key defines operational constraints for capture/tiling/requests.

olmOCR-2-7B-1025-FP8:
  provider: "ai2"
  display_name: "olmOCR 2 (7B, FP8)"
  long_side_px: 1288
  fp8_preferred: true
  max_tiles_in_flight: 8
  prompt_template: "olmocr_v4"
  notes: "Default remote model; best quality at ≤1288px longest side."
  refs:
    - "hf:ai2-olm/olmOCR-2-7B-1025"  # model card
    - "ai2:olmocr2-blog"             # release blog

olmOCR-2-7B-1025:
  provider: "ai2"
  display_name: "olmOCR 2 (7B, FP16)"
  long_side_px: 1288
  fp8_preferred: false
  max_tiles_in_flight: 6
  prompt_template: "olmocr_v4"

# Optional alternates (keep disabled by default; parity-tested in benches)
GOT-OCR-2:
  provider: "open"         # fill in when wired
  display_name: "GOT-OCR 2"
  long_side_px: 1280
  fp8_preferred: false
  max_tiles_in_flight: 6
  prompt_template: "generic_ocr"
  disabled: true
  refs:
    - "paper:got-ocr-2"

TextHawk2:
  provider: "open"
  display_name: "TextHawk2"
  long_side_px: 1280
  fp8_preferred: false
  max_tiles_in_flight: 6
  prompt_template: "generic_ocr"
  disabled: true
  refs:
    - "paper:texthawk2"