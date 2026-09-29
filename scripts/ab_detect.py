"""A/B đường tiền xử lý detection trước khi đổi mặc định.

So **đường đang chạy** (CLAHE float32 full-res) với **đường ứng viên** trên frame
thật, in số box khớp, IoU, lệch conf, chênh lệch ms/frame và tự kết luận ĐẠT/KHÔNG
theo cổng cho trước (mặc định IoU min ≥ 0.98, conf lệch ≤ 0.03).

    python scripts/ab_detect.py                          # dùng frame trong /tmp/opt-test/boats
    python scripts/ab_detect.py --capture 8              # tự chụp 8 frame từ camera đang bật
    python scripts/ab_detect.py --candidate detect-scale --detect-scale 0.5 --iou-gate 0.95
    python scripts/ab_detect.py --json

Exit code 0 khi mọi ứng viên ĐẠT, 1 khi có ứng viên KHÔNG ĐẠT.
"""
from __future__ import annotations

import argparse
import inspect
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault('NVIDIA_TF32_OVERRIDE', '0')

REPO = Path(__file__).resolve().parents[1]
SERVER = REPO / 'server'
sys.path.insert(0, str(SERVER))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from app.utils.ai.box_compare import match_boxes, summarize  # noqa: E402
from app.utils.port_config_runtime import (  # noqa: E402
    effective_device,
    effective_model_path,
    get_port_bool,
    get_port_float,
    get_port_int,
)

FRAME_SUFFIXES = ('.png', '.jpg', '.jpeg')
CANDIDATES = ('clahe-uint8', 'no-grayworld', 'grayworld-fast', 'detect-scale')


def _build_clahe_config(enable_gray_world: bool | None = None):
    from app.services.ai.clahe_preprocessor import ClahePreprocessConfig

    config = ClahePreprocessConfig(
        clip_limit=get_port_float('clahe_clip_limit', 3.0),
        tile_grid_size=get_port_int('clahe_tile_size', 8),
        enable_gray_world=get_port_bool('clahe_enable_gray_world', True),
    )
    if enable_gray_world is None:
        return config
    return ClahePreprocessConfig(
        clip_limit=config.clip_limit,
        tile_grid_size=config.tile_grid_size,
        enable_gray_world=enable_gray_world,
    )


def _resolve_weights(model_path: str) -> tuple[str, str]:
    """Chọn engine TRT nếu có, ngược lại dùng .pt.

    Ưu tiên `resolve_yolo_weights` của app khi có (đường chạy thật); nếu bản checkout
    chưa có hàm đó thì tự dò `.engine` cạnh file `.pt` để harness vẫn chạy được.
    """
    try:
        from app.utils.ai.yolo_detector import resolve_yolo_weights
    except ImportError:
        resolve_yolo_weights = None
    if resolve_yolo_weights is not None:
        weights, kind = resolve_yolo_weights(model_path)
        return str(weights), str(kind)
    stem, ext = os.path.splitext(model_path)
    engine = f'{stem}.engine'
    if ext.lower() == '.engine' or not os.path.isfile(engine):
        return model_path, (ext.lstrip('.').lower() or 'pt')
    return engine, 'engine'


def _distinct_frames(frames: list[np.ndarray]) -> int:
    """Số frame thật sự khác nhau (cùng một ảnh copy nhiều bản chỉ tính 1)."""
    import hashlib

    seen = set()
    for frame in frames:
        small = cv2.resize(frame, (64, 64), interpolation=cv2.INTER_AREA)
        seen.add(hashlib.sha1(small.tobytes()).hexdigest())
    return len(seen)


def _call_clahe(frame: np.ndarray, config, fast: bool) -> np.ndarray:
    """Gọi CLAHE với cờ ``fast`` nếu bản hiện tại đã hỗ trợ (trước Task 2 thì chưa)."""
    from app.services.ai.clahe_preprocessor import preprocess_frame_clahe

    if 'fast' in inspect.signature(preprocess_frame_clahe).parameters:
        return preprocess_frame_clahe(frame, config, fast=fast)
    return preprocess_frame_clahe(frame, config)


def _load_frames(frames_dir: Path, capture: int) -> list[np.ndarray]:
    paths = sorted(p for p in frames_dir.glob('*') if p.suffix.lower() in FRAME_SUFFIXES)
    frames = [cv2.imread(str(p)) for p in paths]
    frames = [f for f in frames if f is not None and f.size > 0]
    if frames or capture <= 0:
        return frames

    from sqlalchemy import text

    from app.db.session import SessionLocal
    from app.utils.ai import rtsp_capture

    from app.utils.ai.gpu_bootstrap import init_cuda_library_path

    init_cuda_library_path('pre')
    with SessionLocal() as db:
        rows = db.execute(
            text('select id, rtsp_url from cameras where is_active is true order by id')
        ).all()
    for cam_id, url in rows:
        if len(frames) >= capture:
            break
        try:
            cap = rtsp_capture.open_rtsp(url)
        except Exception as exc:  # pragma: no cover - phụ thuộc camera thật
            print(f'  camera {cam_id}: không mở được ({exc})', file=sys.stderr)
            continue
        try:
            got = 0
            deadline = time.time() + 8.0
            while got < max(1, capture // max(1, len(rows))) and time.time() < deadline:
                ok, frame = cap.read()
                if not ok or frame is None:
                    time.sleep(0.1)
                    continue
                frames.append(frame)
                got += 1
        finally:
            cap.release()
        print(f'  camera {cam_id}: lấy {got} frame', file=sys.stderr)
    return frames


def _detect(model, frame: np.ndarray, *, conf: float, imgsz: int, device: str):
    result = model.predict(source=frame, conf=conf, imgsz=imgsz, verbose=False, device=device)[0]
    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        return np.zeros((0, 4), dtype=np.float32), np.zeros((0,), dtype=np.float32)
    return boxes.xyxy.cpu().numpy().astype(np.float32), boxes.conf.cpu().numpy().astype(np.float32)


def _candidate_frames(name: str, frame: np.ndarray, config, detect_scale: float):
    """Trả về (ảnh đưa vào detector, hệ số quy box về toạ độ gốc)."""
    if name == 'clahe-uint8':
        return _call_clahe(frame, config, True), 1.0
    if name == 'no-grayworld':
        return _call_clahe(frame, _build_clahe_config(False), True), 1.0
    if name == 'grayworld-fast':
        # Đáng bật gray-world không: bản cũ float32 quá đắt, bản uint8 mới rẻ hơn nhiều.
        return _call_clahe(frame, _build_clahe_config(True), True), 1.0
    if name == 'detect-scale':
        small = cv2.resize(frame, None, fx=detect_scale, fy=detect_scale, interpolation=cv2.INTER_AREA)
        return _call_clahe(small, config, True), 1.0 / detect_scale
    raise SystemExit(f'Ứng viên không hợp lệ: {name}')


def main() -> int:
    parser = argparse.ArgumentParser(description='A/B đường tiền xử lý detection')
    parser.add_argument('--frames-dir', default='/tmp/opt-test/boats', help='thư mục frame .png/.jpg')
    parser.add_argument('--capture', type=int, default=0, help='số frame cần chụp nếu thư mục trống')
    parser.add_argument('--candidate', default='clahe-uint8', help=f'các ứng viên, phẩy ngăn cách: {",".join(CANDIDATES)}')
    parser.add_argument('--detect-scale', type=float, default=0.5, help='tỉ lệ cho ứng viên detect-scale')
    parser.add_argument('--conf', type=float, default=None, help='ngưỡng conf (mặc định theo DB)')
    parser.add_argument('--imgsz', type=int, default=None, help='kích thước suy luận (mặc định theo DB)')
    parser.add_argument('--iou-gate', type=float, default=0.98, help='IoU min tối thiểu để ĐẠT')
    parser.add_argument('--conf-gate', type=float, default=0.03, help='lệch conf max cho phép')
    parser.add_argument('--json', action='store_true', help='chỉ in JSON')
    args = parser.parse_args()

    candidates = [c.strip() for c in args.candidate.split(',') if c.strip()]
    for name in candidates:
        if name not in CANDIDATES:
            raise SystemExit(f'Ứng viên không hợp lệ: {name} (chọn trong {", ".join(CANDIDATES)})')

    conf = float(args.conf) if args.conf is not None else get_port_float('conf', 0.75)
    imgsz = int(args.imgsz) if args.imgsz is not None else get_port_int('yolo_imgsz', 960)
    device = effective_device()
    config = _build_clahe_config()
    frames = _load_frames(Path(args.frames_dir), args.capture)
    if not frames:
        raise SystemExit(f'Không có frame nào trong {args.frames_dir} (dùng --capture N để chụp từ camera)')

    from ultralytics import YOLO

    model_path = effective_model_path()
    if not os.path.isabs(model_path):
        # Cấu hình lưu đường dẫn tương đối theo server/ (app luôn chạy với cwd=server).
        model_path = str(SERVER / model_path)
    weights, weights_kind = _resolve_weights(model_path)
    model = YOLO(weights)

    def _run_baseline(src):
        started = time.perf_counter()
        boxes, confs = _detect(model, _call_clahe(src, config, False), conf=conf, imgsz=imgsz, device=device)
        return boxes, confs, (time.perf_counter() - started) * 1000.0

    def _run_candidate(src):
        started = time.perf_counter()
        image, factor = _candidate_frames(name, src, config, args.detect_scale)
        boxes, confs = _detect(model, image, conf=conf, imgsz=imgsz, device=device)
        return boxes * factor, confs, (time.perf_counter() - started) * 1000.0

    report: dict[str, dict] = {}
    for name in candidates:
        totals = {'n_a': 0, 'n_b': 0, 'only_a': 0, 'only_b': 0}
        ious: list[float] = []
        conf_deltas: list[float] = []
        base_ms = cand_ms = 0.0
        # Warmup: tránh tính phí "first touch" cho đường chạy trước.
        _run_baseline(frames[0])
        _run_candidate(frames[0])
        for index, frame in enumerate(frames):
            # Đổi thứ tự mỗi frame để độ trễ không bị thiên lệch về đường chạy trước.
            if index % 2 == 0:
                base_boxes, base_conf, base_dt = _run_baseline(frame)
                cand_boxes, cand_conf, cand_dt = _run_candidate(frame)
            else:
                cand_boxes, cand_conf, cand_dt = _run_candidate(frame)
                base_boxes, base_conf, base_dt = _run_baseline(frame)
            base_ms += base_dt
            cand_ms += cand_dt

            frame_ious, frame_deltas, only_a, only_b = match_boxes(
                base_boxes, base_conf, cand_boxes, cand_conf
            )
            ious += frame_ious
            conf_deltas += frame_deltas
            totals['n_a'] += len(base_boxes)
            totals['n_b'] += len(cand_boxes)
            totals['only_a'] += only_a
            totals['only_b'] += only_b

        summary = summarize(
            totals['n_a'],
            totals['n_b'],
            ious,
            conf_deltas,
            totals['only_a'],
            totals['only_b'],
            iou_gate=args.iou_gate,
            conf_gate=args.conf_gate,
        )
        summary['ms_per_frame_baseline'] = base_ms / len(frames)
        summary['ms_per_frame_candidate'] = cand_ms / len(frames)
        summary['candidate'] = name
        report[name] = summary

    if args.json:
        print(json.dumps({
            'frames': len(frames),
            'weights': str(weights),
            'weights_kind': weights_kind,
            'conf': conf,
            'imgsz': imgsz,
            'device': device,
            'iou_gate': args.iou_gate,
            'conf_gate': args.conf_gate,
            'results': report,
        }, ensure_ascii=False, indent=2))
    else:
        from app.utils.port_config_runtime import load_port_config_map

        if not load_port_config_map():
            print('  ⚠ Không đọc được port_configs trong DB → đang dùng mặc định .env,')
            print('    KHÔNG phải cấu hình hiệu lực. Chạy qua `make ab-detect` (tự cd server).')
        distinct = _distinct_frames(frames)
        gray_note = 'ON' if config.enable_gray_world else 'OFF'
        print(
            f'{len(frames)} frame ({distinct} khác nhau) · model {Path(str(weights)).name}'
            f' · imgsz={imgsz} conf={conf} device={device}'
            f' · đường hiện tại: CLAHE gray-world={gray_note} (bản cũ float32)'
        )
        if distinct < 4:
            print('  ⚠ quá ít frame khác nhau — kết quả chỉ mang tính tham khảo')
        print(f'cổng: IoU min ≥ {args.iou_gate} · conf lệch ≤ {args.conf_gate}')
        for name, row in report.items():
            verdict = '✓ ĐẠT' if row['passed'] else f"✗ KHÔNG ĐẠT ({', '.join(row['reasons'])})"
            print(
                f"  {name:14} box {row['boxes_a']}→{row['boxes_b']} · khớp {row['matched']}"
                f" · IoU min {row['iou_min']:.4f} TB {row['iou_mean']:.4f}"
                f" · conf lệch max {row['conf_max']:.4f}"
                f" · lệch {row['only_a'] + row['only_b']}"
                f" · {row['ms_per_frame_baseline']:.0f}→{row['ms_per_frame_candidate']:.0f} ms/frame"
                f' · {verdict}'
            )

    if any('empty_scene' in row['reasons'] for row in report.values()):
        print('  ✗ Bến trống: cả hai đường đều không có box → A/B không kết luận được.')
        print('    Hãy chọn frame có tàu (--frames-dir) hoặc chờ có tàu rồi --capture N.')
    return 0 if all(row['passed'] for row in report.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
