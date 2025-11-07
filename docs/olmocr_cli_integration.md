# olmOCR CLI Integration Notes
Last updated: 2025-11-08 (FuchsiaMountain)

## 1. Newly Imported Assets
- `docs/olmocr_cli_tool_documentation.md` — upstream end-to-end guide that covers the CUDA 12.6 GPU stack, FlashInfer/vLLM tuning, progress/ETA heuristics, and operational runbooks.
- `scripts/setup_olmocr_cuda12.sh` — shell bootstrapper that installs CUDA 12.6 & GCC 12, wires PATH/LD_LIBRARY_PATH, provisions a `.venv`, installs PyTorch 2.8.0+cu126, FlashInfer 0.3.0, `img2pdf`, and runs a CLI smoke test.
- `scripts/contrib/olmocr_cli_upstream.py` — richer Typer-based CLI with:
  - automatic env overrides (CUDA_HOME, GCC/G++, TORCH_NVML filters),
  - config profiles via `~/.olmocr-cli.toml`,
  - `run`/`images` commands with resume support and worker auto-scaling,
  - local vLLM server helpers (`serve`, `daemon`),
  - streaming progress/ETA output plus warning suppression.

## 2. Integration Plan
1. **Documentation** (bd-rn4) — keep `docs/olmocr_cli_tool_documentation.md` as the authoritative deep-dive and surface it from `docs/olmocr_cli.md`. Extend PLAN §9.3 once the plan file unlocks.
2. **Environment Bootstrap** — reference `scripts/setup_olmocr_cuda12.sh` in docs/ops.md & PLAN §19.1 so GPU hosts can one-shot install the stack.
3. **CLI Merge (bd-4dq)** — compare `scripts/contrib/olmocr_cli_upstream.py` with our slim `scripts/olmocr_cli.py`, then either (a) replace the current script, or (b) port targeted features (resume, progress, server reuse). Capture the decision + migration steps in PLAN and bead notes.

### 2.1 Feature Comparison Snapshot

| Area | Current `scripts/olmocr_cli.py` | Upstream `scripts/contrib/olmocr_cli_upstream.py` |
| --- | --- | --- |
| **Environment handling** | Reads `.env` via `python-decouple`; assumes external CUDA setup. | Builds CUDA 12.6 env automatically (`CUDA_HOME`, GCC/G++, warning filters) and supports per-command overrides via TOML config. |
| **Commands** | `show-env`, `run`, `bench`, `demo snapshot/links/stream/events`, DOM utilities. | `run`, `images`, `serve`, `daemon`, rich progress, resume support, server probing, warning filtering. |
| **Concurrency** | Static `--concurrency` arg. | Auto-selects workers + tensor parallel based on GPU availability, throttles when remote queues are busy. |
| **Progress UX** | Basic Rich tables for snapshots/events. | Rich logging with ETA, throughput, queue stats, warning suppression. |
| **Resume** | None (reruns all input). | `--resume/--no-resume` filters already-processed items via `done_flags/`. |
| **Server lifecycle** | Consumes hosted API only. | Can launch/manage local vLLM server (`serve`, `daemon`) and auto-detect running endpoints. |
| **Dependencies** | `decouple`, `typer`, `rich`. | Adds `zstandard`, `tomllib`, ThreadPool conversions, PyTorch env awareness. |

### 2.2 Proposed Merge Direction
1. **Short term**: keep our CLI for API-facing smoke/ops flows, but port two upstream features quickly: (a) nested `{"ocr": {"policy"}}` payloads (already done via bd-co1), and (b) resumable job filtering for reruns.
2. **Medium term**: create a unified CLI that exposes both hosted-API helpers and GPU/vLLM workflows. This likely means promoting `scripts/contrib/olmocr_cli_upstream.py` to the main script and moving the lighter API commands under a `mdwb` subcommand group.
3. **Documentation**: once the merged CLI ships, consolidate CLI docs (Plan §9 + `docs/olmocr_cli.md`) and deprecate the older instructions.

## 3. Open Questions
- Do we need both the lightweight CLI (current script) and the upstream one, or can we converge on a single tool with feature flags?
- Should we vendor the upstream CLI as-is (faster) or rewrite pieces to follow mdwb coding standards (structlog, uv, python-decouple)?
- Which teams will maintain the CUDA bootstrap script—ops only, or shared with the capture team?

## 4. Next Steps
1. Diff the two CLI implementations (structure, deps, UX) and produce a merge proposal.
2. Update PLAN §5/§9 once the document is available so the work is reflected in-line.
3. Share a short how-to in Agent Mail when the merged CLI lands so ops & capture know where the new docs/scripts live.
