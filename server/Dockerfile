# GPU-enabled image: CUDA 12.8 runtime + Python 3.12 (Ubuntu 24.04)
# 24.04 ships GStreamer 1.24 whose nvcodec plugin exposes cudaconvertscale
# (GPU colour-convert). 22.04 ships 1.20 which lacks it, forcing CPU convert.
FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility,video

# System deps + Python 3.12 (default on 24.04, no PPA needed) + GStreamer NVDEC stack.
# gstreamer1.0-plugins-bad ships libgstnvcodec.so (nvh264dec/nvh265dec/cudaconvertscale/cudadownload).
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    python3.12 \
    python3.12-dev \
    python3.12-venv \
    libpq-dev \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    libgstreamer1.0-0 \
    libgstreamer-plugins-base1.0-0 \
    cuda-nvrtc-12-8 \
    && apt-get purge -y python3-blinker || true \
    && rm -rf /var/lib/apt/lists/*

# nvcodec's cudaconvertscale JIT-compiles its kernel via libnvrtc and dlopen()s the
# UNVERSIONED name "libnvrtc.so"; the runtime package only ships libnvrtc.so.12.
# Without this symlink the element is silently dropped and we fall back to CPU convert.
# NOTE: cannot assert with `gst-inspect cudaconvertscale` here — the nvcodec cuda*
# elements only register when a CUDA device is present, and `docker build` has no GPU.
# Verified at runtime instead (entrypoint / rtsp_capture available() check).
RUN NVRTC=$(ldconfig -p | awk '/libnvrtc\.so\.12/{print $NF; exit}') \
    && ln -sf "$NVRTC" "$(dirname "$NVRTC")/libnvrtc.so" \
    && echo "$(dirname "$NVRTC")" > /etc/ld.so.conf.d/cuda-nvrtc.conf \
    && ldconfig \
    && test -e "$(dirname "$NVRTC")/libnvrtc.so" \
    && echo "OK libnvrtc.so symlink created"

# Set python3.12 as default and bootstrap pip
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.12 1 \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1 \
    && curl -sS https://bootstrap.pypa.io/get-pip.py | python3.12 \
    && pip install --upgrade pip setuptools wheel

WORKDIR /app

COPY requirements.txt requirements-paddle-gpu.txt ./

# Step 1: PaddlePaddle GPU (cu126 wheel, paddle 3.3.0 — has set_optimization_level for paddlex 3.3)
RUN pip install -r requirements-paddle-gpu.txt

# Step 2: PyTorch GPU (CUDA 12.8 / cu128 wheel index)
RUN pip install torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cu128

# Step 3: FastAPI server deps + remaining AI libraries
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8080

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
