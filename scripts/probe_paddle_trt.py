"""Kiểm tra khả thi: PaddleOCR 3.7 + TensorRT fp16 trên wheel paddlepaddle-gpu 3.3.0.

Chạy:  python scripts/probe_paddle_trt.py
Script tự lấy LD_LIBRARY_PATH/LD_PRELOAD từ app (gpu_bootstrap) rồi exec lại chính nó,
đúng như cách OCR worker được spawn.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SERVER = REPO / "server"
sys.path.insert(0, str(SERVER))
os.chdir(SERVER)


def reexec_with_app_env() -> None:
    """Mô phỏng đúng OCR worker: app patch env rồi mới spawn tiến trình con.

    LD_LIBRARY_PATH/LD_PRELOAD chỉ có tác dụng lúc exec, nên phải exec lại chính mình
    thay vì set os.environ trong tiến trình đang chạy.
    """
    from app.utils.ai.gpu_bootstrap import prepare_paddle_subprocess_env

    patch = prepare_paddle_subprocess_env()
    env = os.environ.copy()
    env.update(patch)
    env["PROBE_CHILD"] = "1"
    print("  patch env từ app:")
    for key, value in patch.items():
        print(f"    {key}={str(value)[:150]}")
    os.execve(sys.executable, [sys.executable, __file__], env)

import cv2  # noqa: E402
import numpy as np  # noqa: E402

DET_DIR = "models/paddle_ocr/PP-OCRv6_medium_det"
REC_DIR = "models/paddle_ocr/PP-OCRv6_medium_rec"


def sample_images(limit: int = 8) -> list[tuple[str, np.ndarray]]:
    """Ảnh thật đúng cỡ production (crop tàu ~320px) — ảnh lớn có thể vượt profile TRT."""
    images: list[tuple[str, np.ndarray]] = []
    for directory in (Path("/tmp/dock-verify/crops"), SERVER / "snapshot"):
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.jpg"))[:limit]:
            img = cv2.imread(str(path))
            if img is not None and img.size:
                images.append((path.name, img))
        if images:
            break

    if not images:
        img = np.full((240, 900, 3), 255, np.uint8)
        cv2.putText(img, "TAU BQ 12345", (30, 150), cv2.FONT_HERSHEY_SIMPLEX, 3.2, (0, 0, 0), 6)
        print("  (không có ảnh thật → dùng ảnh tổng hợp 240x900)")
        images.append(("synthetic", img))
    return images


def build(use_tensorrt: bool):
    """Dựng PaddleOCR trực tiếp (không qua adapter) để không bị fallback che mất lỗi."""
    from paddleocr import PaddleOCR

    kwargs = dict(
        lang="en",
        device="gpu:0",
        enable_mkldnn=False,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        text_detection_model_dir=DET_DIR,
        text_recognition_model_dir=REC_DIR,
    )
    if use_tensorrt:
        kwargs["use_tensorrt"] = True
        kwargs["precision"] = "fp16"
    t0 = time.time()
    ocr = PaddleOCR(**kwargs)
    return ocr, time.time() - t0


def main() -> int:
    if not os.environ.get("PROBE_CHILD"):
        reexec_with_app_env()
        return 1

    import traceback

    import numpy as np

    print(f"numpy={np.__version__}")
    from app.utils.ai.paddle_ocr_adapter import run_ocr_lines

    images = sample_images()
    print(f"  {len(images)} ảnh: {[name[:22] for name, _ in images[:4]]}… shape={images[0][1].shape}")

    results = {}
    for label, flag in (("paddle-fp32", False), ("trt-fp16", True)):
        print(f"\n=== {label} ===")
        try:
            ocr, init_sec = build(flag)
            t0 = time.time()
            texts: list[str] = []
            for _, img in images:
                lines = run_ocr_lines(ocr, img)
                texts += [str(line[1][0]) for line in lines if len(line) > 1]
            predict_sec = time.time() - t0
            print(f"  OK init={init_sec:.1f}s · {len(images)} ảnh/{predict_sec:.2f}s "
                  f"({predict_sec / len(images) * 1000:.0f} ms/ảnh) · {len(texts)} dòng")
            print(f"  text: {texts[:6]}")
            results[label] = dict(ok=True, init=init_sec, predict=predict_sec, texts=texts)
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL {type(exc).__name__}: {str(exc)[:400]}")
            traceback.print_exc()
            results[label] = dict(ok=False, error=f"{type(exc).__name__}: {str(exc)[:200]}")

    print("\n=== KẾT LUẬN ===")
    trt = results["trt-fp16"]
    base = results["paddle-fp32"]
    print(f"  TensorRT fp16 khả dụng: {'CÓ' if trt.get('ok') else 'KHÔNG'}")
    if trt.get("ok") and base.get("ok"):
        speed = base["predict"] / max(trt["predict"], 1e-6)
        print(f"  nhanh hơn: {speed:.2f}x (fp32 {base['predict']:.2f}s → trt {trt['predict']:.2f}s)")
        same = sorted(trt["texts"]) == sorted(base["texts"])
        print(f"  text giống fp32: {'CÓ' if same else 'KHÁC'}")
        if not same:
            print(f"    fp32 : {sorted(base['texts'])[:8]}")
            print(f"    trt  : {sorted(trt['texts'])[:8]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
