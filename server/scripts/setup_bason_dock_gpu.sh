#!/usr/bin/env bash
# Rebuild bason-dock: Python 3.12 + Paddle GPU 3 + PyTorch cu124 + app deps.
set -eo pipefail

ENV_NAME="${CONDA_ENV_NAME:-bason-dock}"
SERVER_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PADDLE_INDEX="${PADDLE_INDEX:-https://www.paddlepaddle.org.cn/packages/stable/cu126/}"
TORCH_INDEX="${TORCH_INDEX:-https://download.pytorch.org/whl/cu124}"

source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "$ENV_NAME"

echo "==> Python -> 3.12"
conda install -y python=3.12 pip

PY="$CONDA_PREFIX/bin/python"
PIP="$CONDA_PREFIX/bin/pip"
echo "==> Active: $($PY --version) @ $PY"

echo "==> Remove legacy Paddle / OCR wheels"
"$PIP" uninstall -y paddleocr paddlepaddle paddlepaddle-gpu paddlepaddle-gpu 2>/dev/null || true

echo "==> Install Paddle GPU 3"
"$PIP" install --no-cache-dir \
  --index-url "$PADDLE_INDEX" \
  --extra-index-url https://pypi.org/simple \
  "paddlepaddle-gpu==3.3.0"

echo "==> Install PaddleOCR 3"
"$PIP" install --no-cache-dir "paddleocr>=3.3.0,<4"

echo "==> Install PyTorch cu124"
"$PIP" install --no-cache-dir \
  --index-url "$TORCH_INDEX" \
  torch torchvision

echo "==> Install application requirements (no paddle pins)"
"$PIP" install --no-cache-dir "numpy==1.26.4" "pillow>=10.0.0"
sed '/^paddleocr/d' "$SERVER_DIR/requirements.txt" > /tmp/req-no-paddleocr.txt
"$PIP" install --no-cache-dir -r /tmp/req-no-paddleocr.txt

echo "==> Cleanup orphan python lib if present"
if [[ -d "$CONDA_PREFIX/lib/python3.11" && "$($PY -c 'import sys; print(sys.version_info[:2])')" == "(3, 12)" ]]; then
  rm -rf "$CONDA_PREFIX/lib/python3.11" "$CONDA_PREFIX/include/python3.11"
  echo "removed lib/python3.11"
fi

echo "==> Versions"
"$PIP" show paddlepaddle-gpu paddleocr torch | rg '^(Name|Version):'

echo "==> Verify torch CUDA"
"$PY" -c "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available())"

echo "==> Verify Paddle GPU (isolated)"
"$PY" -c "
from paddleocr import PaddleOCR
import numpy as np
ocr = PaddleOCR(lang='en', device='gpu:0', use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False)
img = np.zeros((64, 128, 3), dtype=np.uint8)
r = ocr.predict(img)
print('paddleocr predict ok', type(r), len(r) if hasattr(r, '__len__') else 1)
"

echo "DONE setup"
