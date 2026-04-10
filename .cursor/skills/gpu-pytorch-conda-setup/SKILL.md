---
name: gpu-pytorch-conda-setup
description: Sets up and validates a Conda Python environment where PyTorch-GPU is the primary stack, using the correct PyTorch wheel index (e.g. cu128 for CUDA 12.8), ordered pip installs when secondary GPU stacks (e.g. Paddle) use different indexes, and Windows-specific import and runtime checks. Use when creating or reproducing GPU conda environments, fixing multi-index pip installs, aligning PyTorch with a host CUDA Toolkit version, or verifying torch.cuda after install.
---

# GPU PyTorch-Conda setup and test

## Goal

**PyTorch-GPU is the core runtime.** Other GPU libraries (e.g. PaddlePaddle) are secondary: they may use different pip indexes and CUDA wheel generations; install and validate them without breaking PyTorch.

## Hard rule: one Conda `pip:` block cannot express multiple indexes

`conda env create -f environment.yml` merges listed `pip: -r` files into **one** `pip install` invocation. The last `--index-url` wins, so packages that need another mirror (e.g. Paddle vs `download.pytorch.org`) **will not resolve**.

**Pattern that works:**

1. `environment.yml` declares only **base Conda deps** (e.g. `python=3.12`, `pip`). Keep YAML comments **ASCII-only** on Windows to avoid `charmap` decode errors when Conda reads the file.
2. Run **sequential** `pip install` steps from the repo root: a shell script (e.g. `scripts/setup_conda_env.ps1` on Windows) or explicit commands in order.

## Install order (PyTorch-GPU centric)

1. **Secondary GPU stack first** (if required by the project), from its own index — e.g. Paddle `paddlepaddle-gpu` from the official Paddle `cu120` index. Prefer a **direct** `pip install ... --index-url <paddle>` line rather than only `-r` if the mirror is slow (retries may otherwise fail fast).
2. **cuDNN pip wheels** tied to that secondary stack when the project pins them (e.g. `nvidia-cudnn-cu11`).
3. **PyTorch-GPU** — core step: install `torch`, `torchvision`, `torchaudio` from the PyTorch index that matches the **target CUDA generation**, e.g. for host **CUDA Toolkit 12.8** use **`https://download.pytorch.org/whl/cu128`** (not cu126 unless you intentionally standardize on that wheel set). Pin versions if reproducibility matters: `pip index versions torch --index-url https://download.pytorch.org/whl/cu128`.
4. **Application requirements** (`requirements.txt`): frameworks that depend on `torch` (e.g. Ultralytics) and the rest. Must **not** re-pin `torch` to a conflicting index in the same file.

**Toolkit vs wheels:** The host CUDA Toolkit version (e.g. 12.8) is mainly for development (`nvcc`). Inference uses **runtimes bundled inside wheels**. Align **PyTorch** with the intended generation via the **cu12x** index; ensure the **NVIDIA driver** supports that CUDA generation.

## Pin files (optional but clear)

- `requirements-torch-cu128.txt` — `--index-url` for cu128 + unpinned or pinned `torch` / `torchvision` / `torchaudio`.
- Separate small files for Paddle / cuDNN if you want repeatable one-liners without duplicating URLs in docs.

## Verification (PyTorch-first)

Run with the env’s **Python executable** (see Windows notes below):

```bash
python -c "import torch; print(torch.__version__); print('cuda:', torch.cuda.is_available())"
```

If the project also uses Paddle/OCR stacks, **do not** verify with `import paddle, torch` in **one** process on Windows: loading Paddle first can pull older CUDA DLLs and break PyTorch’s `shm.dll` (`WinError 127`). Verify in **separate** short commands, or ensure application code imports **`torch` before `paddle`** (or a documented `gpu_bootstrap` path fix).

Optional stack checks after PyTorch passes:

```bash
python -c "from ultralytics import YOLO; print('ultralytics OK')"
```

## Windows gotchas

- **`conda run -n env python -c "..."`**: can trigger **Application Control** (e.g. `WinError 4551`) blocking `torch.dll` while the same env works when invoking `python.exe` directly. Prefer activating the env and calling `python`, or the full path to `envs/<name>/python.exe`.
- **Import order:** `torch` before `paddle` when both are needed in one process.
- **YAML:** avoid non-ASCII comments in `environment.yml` on Windows Conda.

## Minimal checklist

- [ ] Base env: `conda env create -f environment.yml` (python + pip only if using the split script pattern).
- [ ] Sequential pip: secondary GPU → cuDNN (if any) → **PyTorch-GPU (correct cu12x index)** → `requirements.txt`.
- [ ] Verify: `torch.cuda.is_available()` True with expected `torch.__version__` (+cu128 suffix when using that index).
- [ ] If Paddle is present: separate import test or torch-first import policy in app code.

## Repo reference (this project)

- `environment.yml` — base Conda env.
- `scripts/setup_conda_env.ps1` — ordered installs after env creation.
- `requirements-torch-cu128.txt`, `requirements-paddle-gpu.txt`, `requirements-cudnn.txt`, `requirements.txt` — split requirements by phase.
