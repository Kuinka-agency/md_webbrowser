#!/usr/bin/env bash
# End-to-end setup script for the CUDA 12.6 + FlashInfer 0.3.0 olmOCR environment.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CUDA_HOME="${CUDA_HOME:-/usr/local/cuda-12.6}"
VENV_PATH="${REPO_ROOT}/.venv"

echo "[olmocr-setup] Updating apt indices and ensuring CUDA 12.6 toolkit..."
sudo apt-get update
sudo apt-get install -y cuda-toolkit-12-6 gcc-12 g++-12

if [[ ! -x "$CUDA_HOME/bin/nvcc" ]]; then
  echo "[olmocr-setup] Expected nvcc under $CUDA_HOME but it was not found." >&2
  exit 1
fi

echo "[olmocr-setup] Pointing /usr/bin/nvcc and /usr/local/cuda* at CUDA 12.6..."
sudo update-alternatives --install /usr/local/cuda cuda "$CUDA_HOME" 100 || true
sudo update-alternatives --install /usr/local/cuda-12 cuda-12 "$CUDA_HOME" 100 || true
sudo update-alternatives --install /usr/bin/nvcc nvcc "$CUDA_HOME/bin/nvcc" 100 || true

export CUDA_HOME
export PATH="$CUDA_HOME/bin:${PATH}"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64:${LD_LIBRARY_PATH:-}"
export CC=/usr/bin/gcc-12
export CXX=/usr/bin/g++-12
export CUDAHOSTCXX=/usr/bin/g++-12
export TORCH_CUDA_ARCH_LIST=${TORCH_CUDA_ARCH_LIST:-8.9}

echo "[olmocr-setup] Creating virtualenv at $VENV_PATH (if missing)..."
python3 -m venv "$VENV_PATH"
source "$VENV_PATH/bin/activate"
python -m pip install --upgrade pip uv typer rich

echo "[olmocr-setup] Installing PyTorch 2.8.0 + CUDA 12.6 wheels..."
uv pip install --upgrade --force-reinstall \
  'torch==2.8.0+cu126' 'torchaudio==2.8.0+cu126' 'torchvision==0.23.0+cu126' \
  --extra-index-url https://download.pytorch.org/whl/cu126

python -m pip install --force-reinstall --no-deps flashinfer-python==0.3.0
uv pip install --upgrade 'numpy==2.2.2'
python -m pip install --upgrade img2pdf

if [[ ! -f "$REPO_ROOT/scripts/olmocr_cli.py" ]]; then
  echo "[olmocr-setup] Typer CLI not found. Please run scripts/olmocr_cli.py creation step first." >&2
else
  echo "[olmocr-setup] Running smoke test via Typer CLI..."
  python "$REPO_ROOT/scripts/olmocr_cli.py" run --workspace "$REPO_ROOT/localworkspace" --pdf "$REPO_ROOT/olmocr-sample.pdf"
fi

echo "[olmocr-setup] Completed. Use scripts/olmocr_cli.py show-env to verify runtime settings."
