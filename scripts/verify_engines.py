"""Đối chiếu model .pt (PyTorch) với .engine (TensorRT) trên ảnh thật + đo tốc độ.

    python scripts/verify_engines.py                    # tự tải ảnh thật từ MinIO
    python scripts/verify_engines.py --frames DIR --crops DIR
    python scripts/verify_engines.py --target dinov2

Mục đích: engine FP16 có thể lệch kết quả. Với Re-ID, `visual_match_threshold` trong DB
đang là 0.93 nên embedding lệch nhiều là rủi ro thật — script này đo cụ thể:
  · YOLO   : số box, IoU cặp box khớp, lệch conf, class id, ms/frame
  · DINOv2 : cosine từng crop, cosine thấp nhất, ms/crop (batch 1 và batch 8)
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

# Giống môi trường app lúc chạy (xem app/utils/ai/gpu_bootstrap.py): engine chỉ dùng được
# khi NVIDIA_TF32_OVERRIDE lúc chạy trùng lúc build.
os.environ.setdefault('NVIDIA_TF32_OVERRIDE', '0')


# ------------------------------------------------------------------ ảnh đầu vào
def download_images(prefix: str, dest: Path, limit: int) -> int:
    """Tải ảnh thật từ MinIO (bucket media) để kiểm chứng trên dữ liệu thật."""
    os.environ.setdefault('AWS_ENDPOINT_URL', 'http://127.0.0.1:9100')
    from app.services.storage.s3_service import get_s3_client

    client = get_s3_client()
    dest.mkdir(parents=True, exist_ok=True)
    keys: list[str] = []
    token = None
    while len(keys) < limit:
        kwargs = dict(Bucket='media', Prefix=prefix, MaxKeys=1000)
        if token:
            kwargs['ContinuationToken'] = token
        page = client.list_objects_v2(**kwargs)
        keys += [
            obj['Key']
            for obj in page.get('Contents', [])
            if obj['Key'].lower().endswith(('.jpg', '.jpeg', '.png'))
        ]
        token = page.get('NextContinuationToken')
        if not page.get('IsTruncated'):
            break

    saved = 0
    for key in keys[:limit]:
        target = dest / Path(key).name
        if target.is_file():
            saved += 1
            continue
        target.write_bytes(client.get_object(Bucket='media', Key=key)['Body'].read())
        saved += 1
    return saved


def load_images(directory: Path, limit: int) -> list:
    import cv2

    files = sorted(p for p in directory.rglob('*') if p.suffix.lower() in ('.jpg', '.jpeg', '.png'))
    images = []
    for path in files[:limit]:
        image = cv2.imread(str(path))
        if image is not None and image.size:
            images.append((path, image))
    return images


# ------------------------------------------------------------------------ YOLO
def _iou(a, b) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = max(0, a[2] - a[0]) * max(0, a[3] - a[1])
    area_b = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _predict(model, image, conf: float, imgsz: int):
    result = model.predict(source=image, conf=conf, imgsz=imgsz, verbose=False, device=0)[0]
    boxes, confs, classes = [], [], []
    detected = result.boxes
    if detected is None:
        return boxes, confs, classes
    for box in detected:
        boxes.append([float(v) for v in box.xyxy[0].cpu().numpy()])
        confs.append(float(box.conf[0].cpu().item()))
        classes.append(int(box.cls[0].cpu().item()))
    return boxes, confs, classes


def _match_boxes(reference, other, *, iou_threshold: float = 0.5) -> list[tuple[int, int, float]]:
    """Ghép box theo IoU giảm dần (không ghép theo thứ tự — thứ tự có thể khác nhau)."""
    candidates = []
    for index, left in enumerate(reference):
        for other_index, right in enumerate(other):
            value = _iou(left, right)
            if value >= iou_threshold:
                candidates.append((value, index, other_index))
    candidates.sort(reverse=True)

    used_left: set[int] = set()
    used_right: set[int] = set()
    pairs: list[tuple[int, int, float]] = []
    for value, index, other_index in candidates:
        if index in used_left or other_index in used_right:
            continue
        used_left.add(index)
        used_right.add(other_index)
        pairs.append((index, other_index, value))
    pairs.sort()
    return pairs


def _compare_yolo(model_pt, model_engine, images, *, conf: float, imgsz: int) -> dict:
    """So .pt vs .engine theo từng ảnh: ghép box bằng IoU, tách box chỉ có ở một bên."""
    matched_ious: list[float] = []
    matched_conf_deltas: list[float] = []
    only_pt_conf: list[float] = []
    only_engine_conf: list[float] = []
    class_mismatch: list[str] = []
    total_pt = total_engine = 0

    for path, image in images:
        pt_boxes, pt_confs, pt_classes = _predict(model_pt, image, conf, imgsz)
        en_boxes, en_confs, en_classes = _predict(model_engine, image, conf, imgsz)
        total_pt += len(pt_boxes)
        total_engine += len(en_boxes)

        pairs = _match_boxes(pt_boxes, en_boxes)
        paired_pt = {index for index, _, _ in pairs}
        paired_en = {index for _, index, _ in pairs}
        for index, other_index, value in pairs:
            matched_ious.append(value)
            matched_conf_deltas.append(abs(pt_confs[index] - en_confs[other_index]))
            if pt_classes[index] != en_classes[other_index]:
                class_mismatch.append(f"{path.name[:28]}: pt={pt_classes[index]} engine={en_classes[other_index]}")
        only_pt_conf += [pt_confs[i] for i in range(len(pt_boxes)) if i not in paired_pt]
        only_engine_conf += [en_confs[i] for i in range(len(en_boxes)) if i not in paired_en]

    return {
        'images': len(images),
        'conf': conf,
        'total_pt': total_pt,
        'total_engine': total_engine,
        'matched_ious': matched_ious,
        'matched_conf_deltas': matched_conf_deltas,
        'only_pt_conf': only_pt_conf,
        'only_engine_conf': only_engine_conf,
        'class_mismatch': class_mismatch,
    }


def _report_yolo(result: dict) -> bool:
    import statistics

    ious = result['matched_ious']
    deltas = result['matched_conf_deltas']
    only_pt = result['only_pt_conf']
    only_engine = result['only_engine_conf']
    total = max(1, result['total_pt'])

    print(f"  → {result['images']} ảnh (conf={result['conf']}) · box: pt={result['total_pt']} "
          f"engine={result['total_engine']} · khớp {len(ious)} (IoU≥0.5)")
    if ious:
        print(f"  → cặp khớp: IoU thấp nhất {min(ious):.4f} / trung bình {statistics.fmean(ious):.4f} · "
              f"lệch conf lớn nhất {max(deltas):.4f} / trung bình {statistics.fmean(deltas):.4f}")

    def describe(label: str, values: list[float]) -> None:
        if not values:
            return
        near = sum(1 for value in values if value < result['conf'] + 0.05)
        print(f"  → chỉ có ở {label}: {len(values)} box · conf {min(values):.3f}–{max(values):.3f} "
              f"({near} box sát ngưỡng {result['conf']})")

    describe('.pt', only_pt)
    describe('.engine', only_engine)
    if result['class_mismatch']:
        print(f"  → class khác nhau: {result['class_mismatch'][:3]}")

    unmatched = len(only_pt) + len(only_engine)
    match_ratio = len(ious) / total
    ok = unmatched == 0 and min(ious, default=0.0) > 0.99 and not result['class_mismatch']
    if ok:
        print("  ✓ engine khớp .pt (cùng số box, cùng class)")
    else:
        print(f"  · khớp {match_ratio * 100:.1f}% box; lệch {unmatched} box — "
              "xem phép kiểm tra ảnh vuông bên dưới để biết lệch do đâu")
    return ok


def _square_padded(images):
    """Đệm mỗi ảnh thành hình vuông (nền xám 114) — cùng tỉ lệ nên letterbox 2 đường giống nhau."""
    import numpy as np

    squared = []
    for path, image in images:
        height, width = image.shape[:2]
        side = max(height, width)
        canvas = np.full((side, side, 3), 114, np.uint8)
        canvas[:height, :width] = image
        squared.append((path, canvas))
    return squared


def verify_yolo_square(images, *, conf: float, imgsz: int) -> bool:
    """Đối chiếu khi ảnh đã vuông: engine phải khớp .pt gần như tuyệt đối.

    `.pt` letterbox theo hình chữ nhật tối thiểu (vd 800×960) còn engine tĩnh dùng đúng
    960×960, nên ảnh không vuông lệch nhau vài pixel. Ảnh vuông loại bỏ khác biệt đó, phần
    còn lại mới là sai số thật của engine.
    """
    from ultralytics import YOLO

    from app.utils.port_config_runtime import effective_model_path

    source = Path(effective_model_path())
    engine = source.with_suffix('.engine')
    if not (source.is_file() and engine.is_file()):
        return False

    squared = _square_padded(images)
    result = _compare_yolo(YOLO(str(source)), YOLO(str(engine)), squared, conf=conf, imgsz=imgsz)
    print(f"  (kiểm tra ảnh vuông {squared[0][1].shape[0]}px, conf={conf})")
    return _report_yolo(result)


def verify_yolo(images, *, conf: float, imgsz: int, diagnostic_conf: float = 0.25) -> bool:
    from ultralytics import YOLO

    from app.utils.port_config_runtime import effective_model_path

    source = Path(effective_model_path())
    engine = source.with_suffix('.engine')
    if not source.is_file():
        print(f"  ✗ không thấy {source}")
        return False
    if not engine.is_file():
        print(f"  ✗ chưa có engine {engine.name} — chạy `make engines` trước")
        return False

    print(f"  .pt    : {source.name} ({source.stat().st_size / 1e6:.0f} MB)")
    print(f"  .engine: {engine.name} ({engine.stat().st_size / 1e6:.0f} MB)")
    model_pt = YOLO(str(source))
    model_engine = YOLO(str(engine))
    print(f"  class names: pt={model_pt.names} engine={model_engine.names}")

    result = _compare_yolo(model_pt, model_engine, images, conf=conf, imgsz=imgsz)
    if result['total_pt'] == 0 and conf > 0.25:
        # Ảnh thật (tàu ở xa) có thể không vượt ngưỡng conf đang cấu hình. Hạ ngưỡng để có
        # box mà so sánh — box/conf phải giống nhau ở MỌI ngưỡng nên phép so vẫn đúng.
        print(f"  · conf={conf} không có box nào → so lại ở conf=0.25")
        result = _compare_yolo(model_pt, model_engine, images, conf=0.25, imgsz=imgsz)
    ok = _report_yolo(result)

    # Chạy thêm ở ngưỡng thấp để biết phần lệch là do ngưỡng conf hay do engine tính khác.
    if not ok:
        if result['conf'] > diagnostic_conf:
            print(f"  (chẩn đoán) so lại ở conf={diagnostic_conf}:")
            _report_yolo(_compare_yolo(model_pt, model_engine, images, conf=diagnostic_conf, imgsz=imgsz))
        # Ảnh vuông => letterbox 2 đường giống nhau => chỉ còn sai số thật của engine.
        ok = verify_yolo_square(images, conf=conf, imgsz=imgsz)

    conf = float(result['conf'])

    def speed(model, label: str) -> float:
        for _, image in images[:2]:
            _predict(model, image, conf, imgsz)
        started = time.perf_counter()
        for _, image in images:
            _predict(model, image, conf, imgsz)
        elapsed = (time.perf_counter() - started) / max(1, len(images))
        print(f"  {label:8} {elapsed * 1000:.1f} ms/ảnh (imgsz={imgsz}, conf={conf})")
        return elapsed

    t_pt = speed(model_pt, '.pt')
    t_engine = speed(model_engine, '.engine')
    print(f"  → nhanh hơn: {t_pt / t_engine:.2f}x")
    return ok


# ---------------------------------------------------------------------- DINOv2
def _cosine(a, b) -> float:
    import numpy as np

    a = a.reshape(-1)
    b = b.reshape(-1)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


def verify_dinov2(crops, *, image_size: int, batch: int) -> bool:
    import numpy as np

    from app.core.config import settings
    from app.services.ai.visual_embedding_extractor import VisualEmbeddingExtractor

    engine_files = sorted(Path('models/dinov2').glob('*.engine'))
    if not engine_files:
        print("  ✗ chưa có engine DINOv2 trong models/dinov2/ — chạy `make engines` trước")
        return False
    engine_path = str(engine_files[0])

    def build(model_path: str, prefer_engine: bool):
        original = settings.VISUAL_PREFER_ENGINE
        settings.VISUAL_PREFER_ENGINE = prefer_engine
        try:
            return VisualEmbeddingExtractor(
                model_path=model_path,
                backbone=settings.VISUAL_BACKBONE,
                device='cuda:0',
                image_size=image_size,
                embedding_dim=settings.VISUAL_EMBEDDING_DIM,
            )
        finally:
            settings.VISUAL_PREFER_ENGINE = original

    baseline = build('', False)
    engine = build(engine_path, True)
    print(f"  baseline backend: {baseline.backend}  ·  dim={baseline.embedding_dim}")
    print(f"  engine   backend: {engine.backend}  ·  dim={engine.embedding_dim}")
    if not engine.backend.startswith('trt'):
        print("  ✗ engine không được dùng — kiểm tra lại resolver")
        return False

    images = [image for _, image in crops]
    cosines: list[float] = []
    for image in images:
        left = baseline.extract(image)
        right = engine.extract(image)
        if left is None or right is None:
            continue
        cosines.append(_cosine(left, right))

    cosines_arr = np.array(cosines) if cosines else np.array([0.0])
    print(f"  → {len(cosines)} crop · cosine trung bình={cosines_arr.mean():.5f} "
          f"thấp nhất={cosines_arr.min():.5f}")

    def speed(extractor, label: str) -> None:
        extractor.extract_batch(images[:batch])
        started = time.perf_counter()
        for start in range(0, len(images), batch):
            extractor.extract_batch(images[start : start + batch])
        batches = max(1, (len(images) + batch - 1) // batch)
        elapsed = (time.perf_counter() - started) / batches
        print(f"  {label:16} {elapsed * 1000:.1f} ms/batch (batch={batch}, {len(images)} crop)")

    speed(baseline, f'.pt batch={batch}')
    speed(engine, f'.engine batch={batch}')

    threshold = 0.999
    ok = cosines_arr.min() >= threshold
    print(f"  {'✓ embedding khớp' if ok else f'✗ có crop lệch < {threshold} — cân nhắc giữ .pt'}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description='Đối chiếu .pt vs .engine')
    parser.add_argument('--target', choices=['yolo', 'dinov2', 'all'], default='all')
    parser.add_argument('--frames', type=Path, default=Path('/tmp/dock-verify/frames'))
    parser.add_argument('--crops', type=Path, default=Path('/tmp/dock-verify/crops'))
    parser.add_argument('--frame-limit', type=int, default=12)
    parser.add_argument('--crop-limit', type=int, default=48)
    parser.add_argument('--yolo-crops', type=int, default=40,
                        help='số crop tàu dùng thêm cho YOLO (crop chắc chắn có tàu để so box)')
    parser.add_argument('--conf', type=float, default=None,
                        help='ngưỡng conf khi so sánh (mặc định: conf hiệu lực trong DB)')
    parser.add_argument('--diagnostic-conf', type=float, default=0.25,
                        help='ngưỡng thấp để chẩn đoán khi có box lệch')
    parser.add_argument('--batch', type=int, default=8)
    args = parser.parse_args()

    from app.core.config import settings
    from app.utils.port_config_runtime import get_port_float, get_port_int

    imgsz = int(get_port_int('yolo_imgsz', 960))
    conf_floor = args.conf if args.conf is not None else float(get_port_float('conf', settings.CONF))
    results: list[bool] = []

    if args.target in ('yolo', 'all'):
        print('\n[YOLO]')
        frames = load_images(args.frames, args.frame_limit)
        if not frames:
            print(f"  · chưa có ảnh trong {args.frames} — tải từ MinIO…")
            download_images('detections/', args.frames, args.frame_limit)
            frames = load_images(args.frames, args.frame_limit)
        # Crop tàu bổ sung: ảnh toàn cảnh thường không có box nào ở conf đang cấu hình.
        extra_crops = load_images(args.crops, args.yolo_crops)
        if not extra_crops:
            download_images('vessels/', args.crops, args.yolo_crops)
            extra_crops = load_images(args.crops, args.yolo_crops)
        images = frames + extra_crops
        if len(images) < 2:
            print("  ✗ không đủ ảnh thật để so sánh")
            results.append(False)
        else:
            print(f"  so sánh trên {len(frames)} ảnh toàn cảnh + {len(extra_crops)} crop tàu")
            results.append(verify_yolo(images, conf=conf_floor, imgsz=imgsz, diagnostic_conf=args.diagnostic_conf))

    if args.target in ('dinov2', 'all'):
        print('\n[DINOv2]')
        crops = load_images(args.crops, args.crop_limit)
        if not crops:
            print(f"  · chưa có ảnh trong {args.crops} — tải từ MinIO…")
            download_images('vessels/', args.crops, args.crop_limit)
            crops = load_images(args.crops, args.crop_limit)
        if len(crops) < 4:
            print("  ✗ không đủ crop thật để so sánh")
            results.append(False)
        else:
            results.append(verify_dinov2(crops, image_size=settings.VISUAL_IMAGE_SIZE, batch=args.batch))

    print('\n' + ('✓ Tất cả khớp.' if all(results) else '✗ Có mục lệch — xem chi tiết ở trên.'))
    return 0 if all(results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
