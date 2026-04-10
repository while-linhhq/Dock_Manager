# GPU-enabled image: CUDA 12.8 runtime + Python 3.12
FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120

# Install Python 3.12 + system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common ca-certificates \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-dev \
    python3.12-venv \
    libpq-dev \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && apt-get purge -y python3-blinker || true \
    && rm -rf /var/lib/apt/lists/*

# Set python3.12 as default and bootstrap pip
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.12 1 \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1 \
    && curl -sS https://bootstrap.pypa.io/get-pip.py | python3.12 \
    && pip install --upgrade pip setuptools wheel

WORKDIR /app

COPY requirements.txt .

# Step 1: PaddlePaddle GPU (cu120 wheel — runs fine under CUDA 12.x)
RUN pip install "paddlepaddle-gpu==2.6.2.post120" \
    --index-url https://www.paddlepaddle.org.cn/packages/stable/cu120/ \
    --extra-index-url https://pypi.org/simple

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
