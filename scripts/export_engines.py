"""Xuất model AI sang TensorRT ``.engine`` để chạy nhẹ và nhanh hơn.

    python scripts/export_engines.py                 # cả YOLO + DINOv2
    python scripts/export_engines.py --target yolo
    python scripts/export_engines.py --force         # build lại từ đầu

Engine TensorRT gắn cứng GPU arch (vd SM86) + phiên bản TensorRT + CUDA, KHÔNG bê
sang máy khác được. Vì vậy file .engine không commit (xem .gitignore) và runtime luôn
có đường lùi về .pt (xem resolve_yolo_weights / _resolve_engine_path).

PaddleOCR không có định dạng .engine — nó dùng run_mode=trt_fp16 của PaddleX và tự
cache engine con, xem PADDLE_USE_TENSORRT trong .env.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SERVER = REPO / "server"
sys.path.insert(0, str(SERVER))
os.chdir(SERVER)

# App có import paddle, và paddle đặt NVIDIA_TF32_OVERRIDE=0 cho cả tiến trình. TensorRT
# (Myelin) bắt buộc giá trị này lúc BUILD phải trùng lúc CHẠY, nếu không
# create_execution_context() trả None -> engine không dùng được trong app. Vì vậy build
# engine với đúng TF32=0. Xem thêm app/utils/ai/gpu_bootstrap.py.
os.environ.setdefault('NVIDIA_TF32_OVERRIDE', '0')


def _fmt_size(path: Path) -> str:
    mb = path.stat().st_size / 1024 / 1024
    return f"{mb:.0f} MB"


def _effective_imgsz() -> int:
    from app.utils.port_config_runtime import get_port_int

    return int(get_port_int('yolo_imgsz', 960))


def _effective_image_size() -> int:
    from app.core.config import settings
    from app.utils.port_config_runtime import get_port_int

    return int(get_port_int('visual_image_size', settings.VISUAL_IMAGE_SIZE))


# --------------------------------------------------------------------------- YOLO
def export_yolo(*, imgsz: int, half: bool, force: bool, suffix: str = '') -> int:
    # Ultralytics tự `pip install` gói còn thiếu khi export (đã từng nâng numpy lên 2.x làm
    # vỡ ABI của cv2/paddle). Chặn lại: thiếu gì thì báo lỗi để cài có ý thức.
    os.environ.setdefault('YOLO_AUTOINSTALL', 'false')

    from ultralytics import YOLO

    from app.utils.port_config_runtime import effective_model_path

    source = Path(effective_model_path())
    if source.suffix.lower() != '.pt':
        print(f"  ✗ model_path hiện tại không phải .pt: {source} (cần .pt làm nguồn để export)")
        return 1
    if not source.is_file():
        print(f"  ✗ không thấy file nguồn: {source}")
        return 1

    target = source.with_name(source.stem + suffix + '.engine')
    if target.is_file() and not force:
        print(f"  · đã có {target.name} ({_fmt_size(target)}) — dùng --force để build lại")
        return 0

    # Ultralytics luôn ghi ra '<tên>.engine' (không có hậu tố). Khi export kèm --suffix mà
    # engine mặc định đang tồn tại thì phải cất tạm, nếu không nó bị ghi đè rồi bị move đi.
    default_target = source.with_suffix('.engine')
    stashed: Path | None = None
    if default_target != target and default_target.is_file():
        stashed = default_target.with_name(default_target.name + '.stash')
        default_target.replace(stashed)

    print(f"  ▸ YOLO: {source.name} → {target.name} | imgsz={imgsz} half={half}")
    started = time.time()
    try:
        model = YOLO(str(source))
        exported = model.export(
            format='engine',
            imgsz=imgsz,
            half=half,
            device=0,
            dynamic=False,
            batch=1,
            workspace=4,
            verbose=False,
        )
    finally:
        if stashed is not None and stashed.is_file() and not default_target.exists():
            stashed.replace(default_target)
            print(f"  · đã phục hồi {default_target.name}")
    elapsed = time.time() - started

    produced = Path(str(exported))
    if produced.resolve() != target.resolve() and produced.is_file():
        produced.replace(target)
    if not target.is_file():
        print(f"  ✗ export xong nhưng không thấy {target}")
        return 1
    print(f"  ✓ {target.name} ({_fmt_size(target)}) sau {elapsed:.0f}s")
    return 0


# ------------------------------------------------------------------------- DINOv2
def _onnx_matches_torch(model, onnx_path: Path, *, batch: int, image_size: int) -> float:
    """So cosine giữa output torch và output ONNX (chạy CPU) trước khi build TRT."""
    import numpy as np
    import onnxruntime as ort
    import torch

    sample = torch.randn(batch, 3, image_size, image_size)
    with torch.no_grad():
        reference = model(sample.cuda()).float().cpu().numpy()

    session = ort.InferenceSession(str(onnx_path), providers=['CPUExecutionProvider'])
    got = session.run(None, {session.get_inputs()[0].name: sample.numpy()})[0]

    reference = reference.reshape(batch, -1)
    got = got.reshape(batch, -1)
    cos = [
        float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))
        for a, b in zip(reference, got)
    ]
    return float(np.mean(cos))


def export_dinov2(
    *,
    image_size: int,
    batch_min: int,
    batch_opt: int,
    batch_max: int,
    half: bool,
    workspace_gb: int,
    force: bool,
) -> int:
    import torch

    from app.core.config import settings
    from app.services.ai.visual_embedding_extractor import _load_timm_backbone, _resolve_weights_path
    from app.utils.port_config_runtime import model_file

    try:
        import tensorrt as trt
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ chưa cài TensorRT: {exc}")
        return 1

    backbone = settings.VISUAL_BACKBONE
    weights = _resolve_weights_path(backbone)
    target = Path(model_file('dinov2', f'{backbone}.engine'))
    onnx_path = target.with_suffix('.onnx')
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.is_file() and not force:
        print(f"  · đã có {target.name} ({_fmt_size(target)}) — dùng --force để build lại")
        return 0

    print(f"  ▸ DINOv2: backbone={backbone} weights={weights or '(timm pretrained/HF)'}")
    model, resolved = _load_timm_backbone(backbone, image_size=image_size, weights_path=weights)
    if model is None:
        print(f"  ✗ không nạp được backbone {backbone}")
        return 1
    model.eval().to('cuda')

    if resolved != backbone:
        target = Path(model_file('dinov2', f'{resolved}.engine'))
        onnx_path = target.with_suffix('.onnx')
        print(f"  · backbone thực tế: {resolved} → {target.name}")

    print(f"    export ONNX (batch động 1..{batch_max}, {image_size}x{image_size})…")
    started = time.time()
    dummy = torch.randn(batch_max, 3, image_size, image_size, device='cuda')
    torch.onnx.export(
        model,
        dummy,
        str(onnx_path),
        input_names=['input'],
        output_names=['embedding'],
        dynamic_axes={'input': {0: 'batch'}, 'embedding': {0: 'batch'}},
        opset_version=17,
        do_constant_folding=True,
    )
    print(f"    ONNX {onnx_path.name} ({_fmt_size(onnx_path)})")

    cosine = _onnx_matches_torch(model, onnx_path, batch=min(2, batch_max), image_size=image_size)
    print(f"    kiểm tra ONNX vs torch: cosine trung bình = {cosine:.6f}")
    if cosine < 0.9999:
        print("  ✗ ONNX lệch quá nhiều so với torch — dừng trước khi build TRT")
        return 1

    print(f"    build engine TensorRT (fp16={half}, workspace={workspace_gb}GB)…")
    logger = trt.Logger(trt.Logger.WARNING)
    builder = trt.Builder(logger)
    try:
        flags = 1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH)
    except Exception:  # TRT 10+ mặc định đã là explicit batch
        flags = 0
    network = builder.create_network(flags)
    parser = trt.OnnxParser(network, logger)
    if not parser.parse_from_file(str(onnx_path)):
        for index in range(parser.num_errors):
            print(f"  ✗ parser: {parser.get_error(index)}")
        return 1

    config = builder.create_builder_config()
    config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, workspace_gb * (1 << 30))
    if half:
        config.set_flag(trt.BuilderFlag.FP16)
    # Engine FP16 không cần TF32; tắt hẳn để không phụ thuộc NVIDIA_TF32_OVERRIDE lúc chạy.
    try:
        config.clear_flag(trt.BuilderFlag.TF32)
    except Exception:  # TRT cũ không có flag này
        pass
    profile = builder.create_optimization_profile()
    profile.set_shape(
        'input',
        (batch_min, 3, image_size, image_size),
        (batch_opt, 3, image_size, image_size),
        (batch_max, 3, image_size, image_size),
    )
    config.add_optimization_profile(profile)

    serialized = builder.build_serialized_network(network, config)
    if serialized is None:
        print("  ✗ build engine thất bại")
        return 1
    target.write_bytes(bytes(serialized))

    elapsed = time.time() - started
    print(f"  ✓ {target.name} ({_fmt_size(target)}) sau {elapsed:.0f}s")
    print(f"    (giữ {onnx_path.name} để đối chiếu; có thể xoá nếu không cần)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description='Xuất model AI sang TensorRT .engine')
    parser.add_argument('--target', choices=['yolo', 'dinov2', 'all'], default='all')
    parser.add_argument('--imgsz', type=int, default=None, help='YOLO input (mặc định: yolo_imgsz trong DB)')
    parser.add_argument('--image-size', type=int, default=None, help='DINOv2 input (mặc định: cấu hình)')
    parser.add_argument('--batch-min', type=int, default=1)
    parser.add_argument('--batch-opt', type=int, default=4)
    parser.add_argument('--batch-max', type=int, default=8)
    parser.add_argument('--fp32', dest='half', action='store_false', default=True)
    parser.add_argument('--workspace', type=int, default=4, help='GB workspace cho builder')
    parser.add_argument('--suffix', default='', help="thêm hậu tố vào tên engine (vd _fp32) để so sánh A/B")
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()

    from app.services.ai.trt_engine import tensorrt_available

    if not tensorrt_available():
        print('✗ Chưa cài TensorRT. Cài: pip install "tensorrt-cu12>=10,<11"')
        return 1

    import tensorrt as trt

    print(f"TensorRT {trt.__version__}  ·  numpy {__import__('numpy').__version__}")
    imgsz = args.imgsz or _effective_imgsz()
    image_size = args.image_size or _effective_image_size()

    failures = 0
    if args.target in ('yolo', 'all'):
        print('\n[YOLO]')
        failures += export_yolo(imgsz=imgsz, half=args.half, force=args.force, suffix=args.suffix)
    if args.target in ('dinov2', 'all'):
        print('\n[DINOv2]')
        failures += export_dinov2(
            image_size=image_size,
            batch_min=args.batch_min,
            batch_opt=args.batch_opt,
            batch_max=args.batch_max,
            half=args.half,
            workspace_gb=args.workspace,
            force=args.force,
        )

    print('\n' + ('✓ Xong.' if not failures else f'✗ {failures} mục lỗi.'))
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
