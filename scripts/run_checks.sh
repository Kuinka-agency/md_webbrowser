#!/usr/bin/env bash

# Run the mandatory verification suite (ruff, ty, Playwright smoke).
# Additional args override the default Playwright target.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

check_libvips() {
  if [[ "${SKIP_LIBVIPS_CHECK:-0}" == "1" ]]; then
    echo "→ libvips preflight skipped (SKIP_LIBVIPS_CHECK=1)"
    return
  fi
  if uv run python - >/dev/null 2>&1 <<'PY'
import pyvips  # noqa
PY
  then
    return
  fi
  cat <<'EOF'
ERROR: libvips/pyvips is not available in this environment.
Install the system package (e.g., `sudo apt-get install libvips` on Debian/Ubuntu)
before running scripts/run_checks.sh so the tiler tests can import pyvips.
EOF
  exit 1
}

if [[ $# -gt 0 ]]; then
  PLAYWRIGHT_TARGETS=("$@")
else
  PLAYWRIGHT_TARGETS=("tests/smoke_capture.spec.ts")
fi

run_step() {
  local label="$1"
  shift
  echo "→ ${label}"
  "$@"
  echo
}

check_libvips

run_step "ruff check" uv run ruff check --fix --unsafe-fixes
run_step "ty check" uvx ty check
run_step "pytest" uv run pytest \
  tests/test_mdwb_cli_events.py \
  tests/test_mdwb_cli_webhooks.py \
  tests/test_mdwb_cli_fetch.py \
  tests/test_mdwb_cli_artifacts.py \
  tests/test_agent_scripts.py \
  tests/test_olmocr_cli_config.py \
  tests/test_check_env.py \
  tests/test_show_latest_smoke.py \
  tests/test_metrics.py \
  tests/test_api_webhooks.py

if [[ -n "${PLAYWRIGHT_BIN:-}" ]]; then
  run_step "playwright" "${PLAYWRIGHT_BIN}" "${PLAYWRIGHT_TARGETS[@]}"
elif uv run playwright --help | grep -q "test"; then
  run_step "playwright" uv run playwright test "${PLAYWRIGHT_TARGETS[@]}"
else
  echo "→ playwright"
  echo "WARN: Playwright CLI missing 'test' subcommand; skipping smoke run."
  echo "      Install the Node-based Playwright runner or provide PLAYWRIGHT_BIN to enable this step."
  echo
fi

if [[ "${MDWB_CHECK_METRICS:-0}" == "1" ]]; then
  METRICS_TIMEOUT="${CHECK_METRICS_TIMEOUT:-5.0}"
  run_step "metrics" uv run python scripts/check_metrics.py --timeout "$METRICS_TIMEOUT"
fi
