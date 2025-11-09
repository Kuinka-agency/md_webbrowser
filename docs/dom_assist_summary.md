# DOM Assist Summary Metrics

## Overview
Hybrid text recovery (bd-805) now emits DOM-assist summaries everywhere (manifest JSON, SSE snapshots, CLI diag/warnings, and warning logs). This document details the schema so dashboards and downstream consumers can stay aligned.

## Summary Schema
- `count`: total assists performed during stitching.
- `reasons`: sorted list of unique reasons observed.
- `reason_counts`: list of `{reason, count, ratio}` entries. `ratio` is assists per tile when `tiles_total` is known, otherwise assists per total assists.
- `assist_density`: `count / tiles_total` when the tile count is available; omitted otherwise.
- `tiles_total`: total number of tiles for the run (when available) to support normalized alerting.
- `sample`: `{tile_index, line, reason, dom_text}` for quick inspection in CLI/UI logs.

All fields are optional but present when the underlying data exists. Manifest snapshots now include this block even when the raw `dom_assists` list is trimmed or unavailable (cache hits, SSE snapshots, etc.).

## Consumers
- SSE + UI manifest tab: displays counts, density, ratio table, and sample text.
- CLI (`mdwb diag`, `mdwb warnings tail`): prints the same summary and reason histogram.
- Warning logs: persists the summary alongside blocklist/sweep data so historical analysis has the same view.
- Prometheus metrics: `mdwb_dom_assist_density` (histogram, no labels) captures assists per tile; `mdwb_dom_assist_reason_ratio{reason="..."}` records per-reason ratios using the same buckets. Dashboards can alert on spikes in either metric.

## Roadmap
- Prometheus metrics: export `assist_density` and per-reason ratios so dashboards can alert on spikes.
- Ops dashboards: add panels that highlight dom_assist density trends per category/job type.
