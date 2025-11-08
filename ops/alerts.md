# Ops Alerts

Prometheus (see `docs/ops.md`) now exports capture/ocr/stitch histograms, warning/blocklist counters,
job completion totals, and SSE heartbeat counters. Configure alert rules as follows:

## Capture/OCR Latency
- **HighCaptureLatencyDocs** – trigger when `histogram_quantile(0.95, sum(rate(mdwb_capture_duration_seconds_bucket[5m])) by (le))`
  exceeds **25s** for 10 consecutive minutes.
- **HighOcrLatencyApps** – trigger when `histogram_quantile(0.95, sum(rate(mdwb_ocr_duration_seconds_bucket[5m])) by (le))`
  exceeds **45s** for 10 consecutive minutes.
- Include manifest links from the most recent `/jobs/{id}` in the alert payload so on-call can replay quickly.

## Job Failure Rate
- **JobFaultRate** – fire when `sum(rate(mdwb_job_completions_total{state="FAILED"}[5m]))`
  exceeds `0.2` jobs/minute while DONE rate remains below 1 job/minute.
- Auto-annotate with the last five failure job IDs (pull from `/jobs` API) so responders can inspect manifests/tiles.

## Overlay / Warning Spikes
- **WarningFlood** – fire when `sum(increase(mdwb_capture_warnings_total[15m])) by (code)` exceeds 20 for any code.
- **BlocklistSpike** – fire when `sum(increase(mdwb_blocklist_hits_total[15m])) by (selector)` exceeds 30 for any selector.
- For both, include the selector/code and top affected domains so blocklist updates can be prioritized.

## SSE / NDJSON Health
- **SSEHeartbeatsStalled** – trigger when `rate(mdwb_sse_heartbeat_total[5m])` drops below `0.1` for 5 minutes, indicating `/jobs/{id}/stream` or `/events` feeds stalled.
- Action: tail the relevant `/events` endpoint via `mdwb events <job-id> --follow` and restart the API pod if heartbeats do not resume.

## Alert Workflow
1. Grafana alerts route to PagerDuty “mdwb-capture” service.
2. First responder acknowledges within 5 minutes and posts a status blurb + job IDs / manifest paths in Agent Mail threads (`dm9`, `7sx`, `ug0` as appropriate).
3. After mitigation, update `docs/ops.md` if new selectors or runbooks were required, and log the incident under `docs/incidents/`.
