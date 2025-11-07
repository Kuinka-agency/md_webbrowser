# Architecture & Operational Best Practices (Markdown Web Browser)
_Last updated: 2025-11_

## Objectives
- Deterministically convert arbitrary URLs into high-fidelity Markdown for agent ingestion.
- Preserve provenance and reproducibility across browser, tiler, and OCR steps.
- Keep the pipeline observable and debuggable under real-world load.

## Golden Invariants
- **Screenshot-first** (not print/PDF), with **viewport-sweep chunking** for tall pages.
- **Model-aligned scaling**: every tile’s longest side **≤ 1288 px** for olmOCR‑2. 
- **Reproducible browser**: run **Chrome for Testing** (CfT), pin revision, log CfT label + exact build in `manifest.json`. 
- **Async, bounded I/O**: HTTP/2 multiplexing to OCR, token‑bucket rate limit, retries with jitter. 

## High-Level Dataflow

```

URL → Playwright (CfT, viewport=1280×2000, dpr=2, reduced-motion)
→ Viewport sweep (chunk screenshots, settle, no full_page on tall)
→ pyvips tiler (overlap≈120px, downscale to ≤1288 long side)
→ OCR client (HTTP/2, token-bucket, retries) → Markdown segments
→ Stitcher (overlap de-dup, DOM-guided heading normalization,
guarded hyphenation, table seam rules)
→ out.md (+ provenance comments)
→ links.json (anchors/forms/headings/landmarks/meta)
→ manifest.json (browser/versions/policy/timings)

```

### Browser Capture
- **CfT + Playwright**: Prefer CfT for reproducible builds. Record `cft_channel`, `cft_build`, `playwright_version`. 
- **Stability**:
  - `deviceScaleFactor=2`, `colorScheme="light"`, `emulate_media(reduced_motion="reduce")`. 
  - If you also use Playwright Test in smoke suites, its `toHaveScreenshot(animations: 'disabled')` helps freeze visuals; pipeline capture itself should rely on CSS/JS motion suppression, not test-only APIs. 
- **Tall pages**:
  - Use **viewport sweeps** with settle checks; avoid `full_page=True` on very tall pages to sidestep Chrome raster limits that cause truncation/OOM. Start chunking around **~12k px** total height. 
- **Overlay minimization**:
  - Combine a request‑level adblock engine (EasyList/EasyPrivacy + cookie filters) with CSS selector hides for sticky/fixed elements. (See `docs/blocklist.md`.) 

### Tiling & Imaging
- **pyvips** for crop/resize/encode — fastest/lowest memory at large sizes; PNG lossless for OCR (non‑interlaced). 
- **Geometry**: overlap ≈120 px; pre‑downscale each slice so longest side ≤1288 px; record cssY offset, DPR, hashes.
- **Hashes**: internal cache key via `xxh3_128`; provenance via SHA‑256 stored in manifest.

### OCR I/O
- **HTTP/2** `httpx.AsyncClient(http2=True)` to multiplex many small tile requests to the same host. 
- **Rate limit** via token‑bucket per host; retry 408/429/5xx with exponential backoff + jitter; 4xx (non‑429) are terminal per tile. 
- **Model policy** in `docs/models.yaml` controls long‑side px, parallelism, FP8 preference, and prompt template. Default: `olmOCR-2-7B-1025-FP8`. 

### Stitching
- Overlap de‑dup using RapidFuzz on trailing/leading line windows; fall back to difflib only when needed. 
- DOM‑guided heading normalization (fix H1→H4 drift).
- Guard hyphenation fix outside code/math fences; table seam logic prefers duplicate header collapse over risky merges.

### DOM Harvest
- Capture anchors/forms/headings/meta plus **ARIA landmarks** (role=main/nav/etc.), language and direction. Agents use this to prioritize content over chrome. (Use MDN’s IntersectionObserver and landmarks semantics to decide what to fetch next in infinite/virtualized lists.) 

### Caching & Re-runs
- Conditional HEAD/GET with `If-None-Match`/`If-Modified-Since` before recapture. If **304**, reuse last run. 

### Observability
- Expose `/metrics` via **prometheus-fastapi-instrumentator**; export p50/p95 per stage, tiles/sec, 429/5xx rates. Add OTel FastAPI tracing for end‑to‑end spans. 

## Deliverables per run
- `artifact/tiles/tile_XXXX.png`
- `out.md` with `<!-- source: tile_i, y=..., sha256=..., scale=... -->`
- `links.json` (anchors/forms/headings/meta/landmarks)
- `manifest.json` (CfT label+build, DPR, viewport, policies, timings, hashes)

## Gotchas (and our mitigations)
- **Raster limits on tall pages** → viewport sweeps. 
- **Animated UIs** → reduced‑motion + CSS disables; test‑time `animations:'disabled'` for smoketests. 
- **Consent overlays** → adblock engine + CSS hide + “retry sweep if height shrinks” heuristic. 