#!/usr/bin/env python3
"""Đo tài nguyên thật (VRAM · RAM · CPU · độ trễ) của từng model: bản gốc vs engine TensorRT.

Mỗi biến thể chạy trong một tiến trình riêng (``--variant``) để số liệu bộ nhớ quy đúng cho
model đó — TensorRT và PyTorch không nhả VRAM về driver khi huỷ đối tượng, chạy chung một
tiến trình là sai số ngay.

    python scripts/bench_models.py                  # đo tất cả rồi in bảng so sánh
    python scripts/bench_models.py --target yolo    # chỉ YOLO
    python scripts/bench_models.py --variant yolo:pt  # chạy 1 biến thể (dùng nội bộ)
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SERVER = REPO / "server"
sys.path.insert(0, str(SERVER))
os.chdir(SERVER)

# Giống môi trường app lúc chạy — engine chỉ dùng được khi TF32 khớp lúc build.
os.environ.setdefault('NVIDIA_TF32_OVERRIDE', '0')

SAMPLES_DIR = Path('/tmp/dock-verify')
VARIANTS = ('yolo:pt', 'yolo:engine', 'dinov2:pt', 'dinov2:engine')


# ------------------------------------------------------------------ đo tài nguyên
class ResourceSampler:
    """Lấy mẫu VRAM (theo PID) + CPU hệ thống trong lúc chạy."""

    def __init__(self) -> None:
        import psutil
        from pynvml import (
            nvmlDeviceGetComputeRunningProcesses,
            nvmlDeviceGetHandleByIndex,
            nvmlInit,
        )

        nvmlInit()
        self._handle = nvmlDeviceGetHandleByIndex(0)
        self._running = nvmlDeviceGetComputeRunningProcesses
        self._process = psutil.Process()
        self._psutil = psutil
        self.peak_vram_mb = 0.0
        self.cpu_percent: list[float] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def vram_mb(self) -> float:
        for proc in self._running(self._handle):
            if proc.pid == self._process.pid:
                return proc.usedGpuMemory / 1024 / 1024
        return 0.0

    def rss_mb(self) -> float:
        return self._process.memory_info().rss / 1024 / 1024

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.peak_vram_mb = max(self.peak_vram_mb, self.vram_mb())
            self.cpu_percent.append(self._psutil.cpu_percent(interval=None))
            time.sleep(0.05)

    def start(self) -> None:
        self._psutil.cpu_percent(interval=None)  # mồi mẫu đầu
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)


def _load_images(prefix: str, limit: int) -> list:
    import cv2
    import numpy as np

    folder = SAMPLES_DIR / prefix
    paths = sorted(folder.glob('*.jpg')) + sorted(folder.glob('*.png'))
    images = []
    for path in paths[:limit]:
        image = cv2.imread(str(path))
        if image is not None:
            images.append(image)
    if images:
        return images

    # Không có ảnh thật thì dùng ảnh tổng hợp cùng kích thước điển hình của pipeline.
    rng = np.random.default_rng(0)
    shape = (720, 1280, 3) if prefix == 'frames' else (264, 320, 3)
    return [rng.integers(0, 255, shape, dtype=np.uint8) for _ in range(limit)]


# ------------------------------------------------------------------ biến thể
def run_yolo(use_engine: bool, *, iterations: int, imgsz: int, conf: float) -> dict:
    from ultralytics import YOLO

    from app.utils.port_config_runtime import effective_model_path

    source = Path(effective_model_path())
    model_path = str(source.with_suffix('.engine')) if use_engine else str(source)
    if use_engine and not Path(model_path).is_file():
        raise SystemExit(f'chưa build engine: {model_path} — chạy: make engines')

    images = _load_images('frames', 4) + _load_images('crops', 20)
    sampler = ResourceSampler()
    rss_before = sampler.rss_mb()
    model = YOLO(model_path)
    model.predict(source=images[0], conf=conf, imgsz=imgsz, verbose=False, device=0)  # warmup
    rss_loaded = sampler.rss_mb()

    for _ in range(2):  # warmup thêm cho TRT/cuDNN chọn kernel
        model.predict(source=images[0], conf=conf, imgsz=imgsz, verbose=False, device=0)

    sampler.start()
    cpu0 = time.process_time()
    wall0 = time.perf_counter()
    for index in range(iterations):
        model.predict(source=images[index % len(images)], conf=conf, imgsz=imgsz,
                      verbose=False, device=0)
    wall = time.perf_counter() - wall0
    cpu = time.process_time() - cpu0
    time.sleep(0.2)
    sampler.stop()

    return {
        'variant': f'yolo:{"engine" if use_engine else "pt"}',
        'model': Path(model_path).name,
        'size_mb': round(Path(model_path).stat().st_size / 1024 / 1024, 1),
        'iterations': iterations,
        'latency_ms': round(wall / iterations * 1000, 2),
        'cpu_ms_per_iter': round(cpu / iterations * 1000, 2),
        'process_cpu_percent': round(cpu / wall * 100, 1),
        'system_cpu_percent': round(statistics.fmean(sampler.cpu_percent or [0.0]), 1),
        'vram_peak_mb': round(sampler.peak_vram_mb, 1),
        'rss_before_load_mb': round(rss_before, 1),
        'rss_loaded_mb': round(rss_loaded, 1),
    }


def run_dinov2(use_engine: bool, *, iterations: int, batch: int) -> dict:
    import numpy as np

    from app.core.config import settings
    from app.services.ai.visual_embedding_extractor import VisualEmbeddingExtractor

    backbone = str(getattr(settings, 'VISUAL_BACKBONE', 'vit_base_patch14_dinov2'))
    if use_engine:
        settings.VISUAL_PREFER_ENGINE = True
    else:
        # Tắt hẳn engine để chắc chắn đo đường timm (không phụ thuộc engine có sẵn hay không).
        settings.VISUAL_PREFER_ENGINE = False
        settings.VISUAL_ENGINE_PATH = ''

    images = _load_images('crops', 48)
    sampler = ResourceSampler()
    rss_before = sampler.rss_mb()
    extractor = VisualEmbeddingExtractor(
        model_path='',
        backbone=backbone,
        device='cuda:0',
        image_size=int(getattr(settings, 'VISUAL_IMAGE_SIZE', 224) or 224),
        embedding_dim=int(getattr(settings, 'VISUAL_EMBEDDING_DIM', 768) or 768),
    )
    rounded = (len(images) // batch) * batch
    batches = [images[i : i + batch] for i in range(0, rounded, batch)]

    for image in batches[0]:  # warmup: TRT chọn kernel, timm cấp phát bộ nhớ
        extractor.extract(image)
    rss_loaded = sampler.rss_mb()

    sampler.start()
    cpu0 = time.process_time()
    wall0 = time.perf_counter()
    for index in range(iterations):
        for image in batches[index % len(batches)]:
            extractor.extract(image)
    wall = time.perf_counter() - wall0
    cpu = time.process_time() - cpu0
    time.sleep(0.2)
    sampler.stop()

    total = iterations * batch
    return {
        'variant': f'dinov2:{"engine" if use_engine else "pt"}',
        'model': extractor.backend,
        'size_mb': None,
        'iterations': total,
        'latency_ms': round(wall / total * 1000, 2),
        'cpu_ms_per_iter': round(cpu / total * 1000, 2),
        'process_cpu_percent': round(cpu / wall * 100, 1),
        'system_cpu_percent': round(statistics.fmean(sampler.cpu_percent or [0.0]), 1),
        'vram_peak_mb': round(sampler.peak_vram_mb, 1),
        'rss_before_load_mb': round(rss_before, 1),
        'rss_loaded_mb': round(rss_loaded, 1),
    }


def run_child(variant: str, iterations: int, imgsz: int, conf: float, batch: int) -> None:
    family, kind = variant.split(':')
    if family == 'yolo':
        result = run_yolo(kind == 'engine', iterations=iterations, imgsz=imgsz, conf=conf)
    else:
        result = run_dinov2(kind == 'engine', iterations=iterations, batch=batch)
    print('BENCH_JSON ' + json.dumps(result), flush=True)


# ------------------------------------------------------------------ báo cáo
FIELDS = (
    ('latency_ms', 'độ trễ (ms/ảnh)', 'thấp hơn tốt'),
    ('cpu_ms_per_iter', 'CPU/ảnh (ms)', 'thấp hơn tốt'),
    ('process_cpu_percent', 'CPU tiến trình (%)', 'thấp hơn tốt'),
    ('system_cpu_percent', 'CPU toàn máy (%)', 'tham khảo'),
    ('vram_peak_mb', 'VRAM đỉnh (MB)', 'thấp hơn tốt'),
    ('rss_loaded_mb', 'RAM tiến trình (MB)', 'thấp hơn tốt'),
)


def report(results: list[dict]) -> int:
    for group in ('yolo', 'dinov2'):
        pairs = [r for r in results if r['variant'].startswith(group)]
        if len(pairs) != 2:
            continue
        base, engine = pairs
        print(f"\n\033[1m{group.upper()}\033[0m  ·  {base['model']} → {engine['model']}")
        print(f"  {'chỉ số':22} {'bản gốc':>12} {'engine':>12} {'thay đổi':>12}")
        for key, label, _hint in FIELDS:
            old, new = base[key], engine[key]
            if old in (None, 0) or new is None:
                continue
            delta = (new - old) / old * 100
            color = '\033[32m' if delta < -1 else ('\033[31m' if delta > 1 else '\033[2m')
            print(f'  {label:22} {old:>12.1f} {new:>12.1f} {color}{delta:>+11.1f}%\033[0m')
    print()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description='Đo VRAM/RAM/CPU của model gốc vs engine TensorRT')
    parser.add_argument('--target', choices=('yolo', 'dinov2', 'all'), default='all')
    parser.add_argument('--variant', help='chạy 1 biến thể trong tiến trình riêng (nội bộ)')
    parser.add_argument('--iterations', type=int, default=30)
    parser.add_argument('--imgsz', type=int, default=None, help='mặc định theo cấu hình hiệu lực')
    parser.add_argument('--conf', type=float, default=None)
    parser.add_argument('--batch', type=int, default=8, help='batch cho DINOv2')
    args = parser.parse_args()

    from app.utils.port_config_runtime import get_port_float, get_port_int

    imgsz = args.imgsz or get_port_int('yolo_imgsz', 960)
    conf = args.conf if args.conf is not None else get_port_float('conf', 0.75)

    if args.variant:
        run_child(args.variant, args.iterations, imgsz, conf, args.batch)
        return 0

    variants = [v for v in VARIANTS if args.target == 'all' or v.startswith(args.target)]
    print(f'▸ Đo {len(variants)} biến thể · imgsz={imgsz} conf={conf} batch={args.batch} '
          f'iterations={args.iterations}')
    results: list[dict] = []
    for variant in variants:
        print(f'  · {variant} …', flush=True)
        proc = subprocess.run(
            [sys.executable, __file__, '--variant', variant, '--iterations', str(args.iterations),
             '--imgsz', str(imgsz), '--conf', str(conf), '--batch', str(args.batch)],
            capture_output=True, text=True,
        )
        line = next((ln for ln in proc.stdout.splitlines() if ln.startswith('BENCH_JSON ')), None)
        if line is None:
            print(f'  ✗ {variant} lỗi:\n{proc.stdout[-1500:]}\n{proc.stderr[-1500:]}')
            continue
        results.append(json.loads(line[len('BENCH_JSON '):]))

    return report(results)


if __name__ == '__main__':
    raise SystemExit(main())
