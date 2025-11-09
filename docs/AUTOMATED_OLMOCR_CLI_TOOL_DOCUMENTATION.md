# Automated olmOCR CLI Tool Documentation

## 1. Environment Baseline
- **GPU stack**: dual RTX 4090 cards, CUDA 12.6 toolkit, driver 566.36 (CUDA 12.7 runtime), GCC/G++ 12 forced via `CC`, `CXX`, `CUDAHOSTCXX`.
- **Python/venv**: project-local `.venv` managed with `uv` + `pip`; Typer + Rich handle CLI UX.
- **Inference stack**: PyTorch 2.8.0+cu126, FlashInfer 0.3.0 (falls back to FlashAttention kernels if present), vLLM 0.10.2 serving `allenai/olmOCR-2-7B-1025-FP8`.
- **Helpers**: `pdftoppm` for PDF rasterisation, `img2pdf` for PNG/JPG ingestion, HuggingFace cache under `~/.cache/huggingface`.
- **Logs**: `olmocr-pipeline-debug.log` aggregates both pipeline + vLLM streams (now filtered so only signal appears on the console; the raw log still has everything).

## 2. End-to-end setup script (`scripts/setup_olmocr_cuda12.sh`)
1. Installs CUDA 12.6 toolkit + GCC 12 via apt, updates alternatives, exports CUDA env vars.
2. Creates/activates `.venv`, upgrades `pip`, installs `uv`, `typer`, `rich`.
3. Installs PyTorch 2.8.0+cu126 triplet via `uv pip`, pins FlashInfer 0.3.0 + NumPy 2.2.2.
4. Installs `img2pdf` (pulls `pikepdf`, `lxml`) so image manifests convert on the fly.
5. Runs a smoke test through the CLI (`python scripts/olmocr_cli.py run --workspace ./localworkspace --pdf ./olmocr-sample.pdf`).
6. Reminds you to double-check the env via `scripts/olmocr_cli.py show-env`.

_Expect the first run to take ~10–15 minutes while CUDA packages download and FlashInfer builds; reruns skip already-installed bits._

## 3. Typer CLI Overview (`scripts/olmocr_cli.py`)
| Command | Purpose | Common Flags |
| --- | --- | --- |
| `show-env` | Display the CUDA/GCC overrides the CLI exports before spawning subprocesses. | _none_ |
| `run` | General PDF/mixed batch runner. Handles directory expansion, manifesting, server auto-detect, warning filtering, resume, and live progress with ETA. | `--workspace`, repeated `--pdf`, `--markdown/--no-markdown`, `--workers`, `--tensor-parallel-size`, `--server-url`, `--server-model`, `--extra-args`, `--resume/--no-resume`, `--visible-gpus` |
| `images` | Convenience wrapper for a folder of PNG/JPG/JPEG files. Builds manifests, runs the pipeline, then copies `.md` files next to each image. | `--workspace`, `--tensor-parallel-size`, `--server-url`, `--workers`, `--extra-args`, `--preconvert/--no-preconvert`, `--resume/--no-resume`, `--visible-gpus` |
| `serve` | Launch a persistent vLLM server with the tuned CUDA env so subsequent runs skip warm-up. | `--model`, `--tensor-parallel-size`, `--port`, `--gpu-memory-utilization`, `--extra-args` |
| `daemon` | Watchdog that keeps a local vLLM server alive in the background (auto-starts if it dies) so you never need a dedicated terminal. | `--port`, `--tensor-parallel-size`, `--poll-interval`, `--extra-args` |

### 3.1 Runtime behavior
- **Env exports**: `_build_env()` prepends `.venv/bin` and `CUDA_HOME/bin` to `PATH`, sets `VIRTUAL_ENV`, forces GCC 12, and silences pynvml/torch warnings (`PYTHONWARNINGS`, `TORCH_NVML_BASED_WARNING_DISABLE`).
- **Server reuse + load hints**: `run`/`images` first honor `--server-url` (or `OLMOCR_SERVER_URL`). If reachable, they reuse it immediately. Otherwise they ping the default `http://localhost:30024/v1`. When a server responds, the CLI fetches `/metrics` and prints the current running/waiting request counts; if the remote queue is already long, it automatically throttles local `--workers` to avoid piling on and warns you about the reduced fan-out.
- **WSL guardrails**: On WSL, tensor-parallel defaults to 1 (NCCL frequently crashes with TP>1). If you explicitly request TP=2 and it fails, the CLI automatically retries once at TP=1 so the run still succeeds.
- **Noise filtering**: Console output now suppresses hundreds of redundant warnings (“Attempt N: please wait…”, pynvml deprecation text, deprecated flags, WSL pin_memory notices, NCCL record-stream chatter). You’ll see a single summary when vLLM is ready (e.g., “vLLM server warmed up after ~62s”) plus the relevant pipeline events.
- **Live progress**: Whenever the pipeline prints “Queue remaining: X”, the CLI calculates processed count, throughput, and ETA, e.g., `Progress: 7/11 done | elapsed 1m12s | ETA 18s`. This is especially useful on image batches where conversions happen up front.
- **Image fast-path**: The `images` command now pre-converts all PNG/JPG files to PDFs in parallel (using `img2pdf`) under `workspace/.converted/…` before the pipeline starts. This shaves a big chunk off wall-clock time because the slowest part (“Converting … from image to PDF format…”) happens once in a thread pool instead of serially inside the worker loop. Disable via `preconvert = false` in the config if you ever need the old behavior.
- **Graceful resume (`--resume/--no-resume`)**: Both `run` and `images` default to resuming work when the workspace already contains `done_flags/`. The CLI reads `work_index_list.csv.zstd`, determines which paths have completed hashes, and filters them out _before_ launching the pipeline. That means reruns (after an abort or partial batch) skip wasteful setup such as manifest generation and image pre-conversion. Pass `--no-resume` or set `resume = false` in the config if you deliberately want to reprocess inputs.
- **GPU affinity (`--visible-gpus`)**: When driving multiple local GPUs, pass `--visible-gpus "0"` (or comma-separated IDs) to pin a run to specific cards. This sets `CUDA_VISIBLE_DEVICES` inside the subprocess without mutating your shell env, and it’s also configurable in `~/.olmocr-cli.toml` via `visible_gpus = "0"`.

### 3.2 Persistent server workflow
1. **Fire-and-forget daemon**: `python scripts/olmocr_cli.py daemon --tensor-parallel-size 1`. This command runs a watchdog loop that pings `http://localhost:30024/v1` every few seconds and auto-starts `vllm serve` whenever the endpoint isn’t healthy. Hit Ctrl+C to stop; the daemon handles restarts if the model crashes.
2. Prefer native Linux? Run `daemon --tensor-parallel-size 2` to keep both 4090s busy; on WSL the daemon auto-falls back to TP=1 when NCCL fails.
3. Once the daemon (or a manual `serve`) is running, any `run`/`images` invocation instantly detects the live endpoint, skips the model reload, and finishes in ~20–30 seconds (actual OCR time only).
4. If the managed server should live elsewhere, set `OLMOCR_SERVER_URL` or pass `--server-url` so the client commands know which endpoint to reuse.

### 3.3 Config profiles (`~/.olmocr-cli.toml`)
You can skip repetitive flags by dropping defaults into `~/.olmocr-cli.toml` (override the path via `OLMOCR_CLI_CONFIG`). The file supports `[global]` plus per-command sections (`[run]`, `[images]`, etc.). Example:

```toml
[global]
workers = 16
server_url = "http://localhost:30024/v1"
visible_gpus = "0"

[run]
tensor_parallel_size = 1
extra_args = "--max-page-retries 6 --max-model-len 12288"
resume = true

[images]
workers = 10
tensor_parallel_size = 1
preconvert = true
preconvert_workers = 6
resume = true
```

Rules:
- CLI flags always win; config values are only used when the option is omitted.
- `global` entries apply to every command; command-specific sections override `global` for that command.
- Keys currently honored: `workers`, `tensor_parallel_size`, `server_url`, `extra_args`, and `server_model`.
- Global keys can also set `visible_gpus` (string) so every command pins itself to specific CUDA devices.
- Image-specific fields: `preconvert` (bool), `preconvert_workers` (int), and `resume` (bool) control the PNG→PDF thread pool and resume behavior.

### 3.4 Packaging & install
The CLI is now pip-installable. From the repo root run:

```bash
pip install .  # or `pipx install .` for isolation
```

This exposes an `olmocr` console script globally, so you can run `olmocr run …`, `olmocr images …`, etc., from any directory (it invokes the same Typer app defined in `scripts/olmocr_cli.py`). The package metadata lives in `pyproject.toml`; bump the `version` field when publishing new releases.

## 4. Worked Example – PDF Batch (`olmocr-sample.pdf`)
```bash
python scripts/olmocr_cli.py run \
    --workspace ./localworkspace \
    --pdf olmocr-sample.pdf \
    --markdown \
    --workers 20
```
Highlights (2025‑11‑07 02:18:56 UTC run):
- Tensor parallel auto-selected 1 (second GPU was tied up by the desktop).
- FlashInfer confirmed (`Using Flash Attention backend on V1 engine.`).
- Metrics: **166.87 s**, **5,358 input / 3,429 output tokens**, **3 pages** (all attempt 0), ~32 input tokens/s.
- Markdown at `localworkspace/markdown/olmocr-sample.md`; raw JSONL under `localworkspace/results/`.
- Progress messages appeared as soon as the queue shrank, so you can tell whether the run is waiting on vLLM or actively processing.

## 5. Worked Example – Image Folder (`test_images/`)
```bash
# persistent server already running via `olmocr_cli.py serve`
python scripts/olmocr_cli.py images test_images \
    --workspace ./localworkspace/images-test \
    --workers 12
```
Outcome:
- Manifest written to `localworkspace/images-test/.manifests/test_images.txt` (11 PNG/JPG files).
- CLI reused the live server, so total runtime dropped to ~25 s (no warm-up). Progress lines counted down from `Progress: 0/11…` to `11/11` with ETA updates.
- Markdown files copied next to each source image (`test_images/*.md`), with their source text stored in `localworkspace/images-test/results/output_<hash>.jsonl`.
- Final metrics for the faster run: **~25 s wall**, **≈3.6 k input / 122 output tokens**, zero retries.

## 6. Batch & GPU Tuning Tips
- **Dual 4090s**: Use `olmocr_cli.py serve --tensor-parallel-size 2` on native Linux to keep both GPUs busy. On WSL, NCCL is unstable with TP>1; leave it at 1 or pass `NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1` if you experiment.
- **Workers**: `--workers 12` is ideal for image batches; PDFs often handle 20. If you point at a remote shared server, consider lowering workers to avoid 429s (the CLI will surface `/metrics` load warnings in a future iteration).
- **Resume**: If a batch is interrupted, rerun the same command; the internal queue (`done_flags/`) ensures finished work isn’t repeated.
- **Custom args**: Use `--extra-args "--max-page-retries 4 --max-model-len 12288"` to tweak pipeline behavior without editing code.

## 7. Artifact Map
| Path | Description |
| --- | --- |
| `olmocr-pipeline-debug.log` | Full pipeline + vLLM log (append-only). Search for `FINAL METRICS SUMMARY` or `Work done` to find completed runs. |
| `localworkspace/` | Default PDF workspace; contains `markdown/`, `results/`, `done_flags/`, `worker_locks/`. |
| `localworkspace/images-test/` | Image workspace; `.manifests`, `results/`, etc. mirrored here. |
| `test_images/*.md` | Markdown mirrors copied next to each PNG/JPG after `images` completes. |
| `scripts/setup_olmocr_cuda12.sh` | One-shot environment bootstrap (CUDA + venv). |
| `scripts/olmocr_cli.py` | CLI entry point (now with `serve`, server auto-detect, filtered logs, live progress). |
| `TODO_olmocr.md` | Backlog of future CLI improvements (daemon, doctor command, profiles, etc.). |

## 8. Troubleshooting Checklist
1. **vLLM never becomes ready** – ensure `.venv/bin` precedes system `PATH` (already handled) and that `vllm` is installed inside `.venv`. Run `python scripts/olmocr_cli.py show-env` to verify exports.
2. **Still seeing warning spam** – confirm you’re invoking via the CLI (which sets the warning filters). If you run `python -m olmocr.pipeline` manually, export `PYTHONWARNINGS` and `TORCH_NVML_BASED_WARNING_DISABLE=1` yourself.
3. **Want both GPUs but NCCL fails** – run on native Linux or start `olmocr_cli.py serve --tensor-parallel-size 2` in a clean shell (no GUI workload on GPU1). If NCCL still errors, the CLI automatically retries at TP=1 so the batch finishes.
4. **img2pdf missing** – rerun `scripts/setup_olmocr_cuda12.sh` or `python -m pip install img2pdf` inside the venv.
5. **Remote server 429s** – pass `--server-url` + `--workers 4` to throttle client-side load; the CLI will soon inspect `/metrics` to warn automatically.
6. **Need extra resilience** – use `--extra-args "--max-page-retries 6 --max-attempts 3"` or lower `--workers` when hitting flaky PDFs.

## 9. Performance Snapshot
| Scenario | Command | Duration | Tokens (in/out) | Notes |
| --- | --- | --- | --- | --- |
| PDF batch (`olmocr-sample.pdf`) | `python scripts/olmocr_cli.py run --workspace ./localworkspace --pdf olmocr-sample.pdf --markdown --workers 20` | 166.87 s | 5,358 / 3,429 | TP auto→1 (GPU1 busy). Markdown in `localworkspace/markdown/`. |
| PNG folder (`test_images/`) – persistent server | `python scripts/olmocr_cli.py images test_images --workspace ./localworkspace/images-test --workers 12` | ~25 s | 3,564 / 122 | Reused running `serve`, so no warm-up. Markdown mirrored next to each PNG. |

## 10. Next Steps & Future Work
- **Daemonized server**: consider wrapping `olmocr_cli.py serve` in a systemd service or tmux session so the fast-path is always available.
- **Health check (`doctor`)**: planned addition to validate CUDA/NCCL/FlashInfer/img2pdf in one shot.
- **Config profiles**: future support for `~/.olmocr-cli.toml` to persist defaults (workers, server URL, etc.).
- **Packaging**: eventual goal is a proper `olmocr` console entry point via `pip install .` for easier distribution.

For now, the combination of `serve` + auto-detect + filtered progress output should make day-to-day usage fast, quiet, and predictable.
