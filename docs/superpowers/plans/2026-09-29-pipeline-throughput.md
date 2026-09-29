# Tối ưu throughput pipeline nhận diện — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Giảm CPU mỗi frame của pipeline nhận diện từ ~137 ms xuống ~54 ms (P1) và cho phép hạ tiếp xuống ~17 ms bằng cờ `detect_scale` (P2, mặc định tắt), không đổi chất lượng OCR/overlay.

**Architecture:** Giữ nguyên luồng dữ liệu. Sửa chỗ lãng phí kỹ thuật trong CLAHE (float32 → uint8), bỏ bản copy full-res thừa khi không consumer nào dùng overlay; thêm telemetry fps/frame. (Vẽ overlay ở tỉ lệ đích: **hoãn**, xem Trạng thái thực thi.) P2 tách một "không gian toạ độ detect" có tỉ lệ cấu hình được, quy đổi box về toạ độ full-res tại **một** điểm duy nhất.

**Tech Stack:** Python 3.12, OpenCV (cv2), NumPy, Ultralytics + TensorRT engine, FastAPI, pytest, conda env `bason-dock`.

**Spec:** `docs/superpowers/specs/2026-09-29-pipeline-throughput-design.md`

## Trạng thái thực thi (cập nhật cuối đợt)

Các checkbox bên dưới là **kế hoạch gốc**, không phải hồ sơ tiến độ — hồ sơ tiến độ nằm ở
`.superpowers/sdd/2026-09-29-pipeline-throughput/progress.md` (kèm mọi ruling khi lệch kế hoạch).

| Task | Kết quả | Ghi chú lệch kế hoạch |
|---|---|---|
| 0 Nhánh + tài liệu | xong | nhánh `feature/pipeline-throughput`, không đụng `main` |
| 1 Hàm so khớp + harness | xong | `box_compare.py` đặt ở `server/app/utils/ai/` (pytest rootdir là `server/`, không import được `scripts/`); commit kèm `Makefile` vốn chưa được track |
| 2 CLAHE uint8 | xong | có thêm phần nối cờ runtime (spec §8 yêu cầu DB > env > default) |
| 3 Bỏ copy thừa + overlay | **một nửa** | chỉ làm phần guard "chỉ dựng overlay khi có consumer"; phần vẽ ở tỉ lệ đích (~1.4 ms/frame) **hoãn** |
| 4 Telemetry fps/frame | xong | thêm `process_ms_per_frame` khi sửa theo review |
| 5 `detect_scale` + `crop_pad_ratio` | xong | mặc định 1.0/0.05, chỉ hoạt động khi bật |
| 6 Nghiệm thu | xong | xem bảng số bên dưới |

**Số nghiệm thu (đo lại sau review, trên cấu hình hiệu lực):**

- `make test` 322 pass · `make check` 32 PASS/0 FAIL · `make verify-engines` "Tất cả khớp".
- `make ab-detect` (baseline = CLAHE gray-world OFF đúng như DB):
  - `clahe-uint8`: 8→8 box, IoU min **1.0000**, 61→63 ms/frame → đường mới **không đổi gì** khi gray-world tắt.
  - `detect-scale 0.5`: 8→8 box, IoU min **0.9704**, 0 box lệch, 67→**23 ms/frame** ✓ (cổng 0.95).
  - `grayworld-fast`: 8→8 box, IoU min **0.9727**, 0 box lệch, 66→82 ms/frame (+16 ms để bật gray-world).
- Trong bộ nhớ (4 frame thật 2560×1440): CLAHE gray-world OFF **28.4 ms**; gray-world ON bản cũ float32 **125.4 ms** vs bản uint8 **40.6 ms** (tiết kiệm ~85 ms/frame).
- Chạy thật 2 camera: **5.0 fps/camera** đúng bằng `record_fps=5` trong DB, cả khi `CLAHE_FAST=false` → pipeline **không** bị chặn bởi CPU mà bởi cấu hình; `process_ms_per_frame` ~70 ms.

**Tiêu chí "≥ 20 fps/camera" ở dòng Global Constraints không dùng được** (bị `record_fps=5`
chặn) — xem spec §9 và §12; muốn fps cao hơn phải nâng `record_fps` (quyết định sản phẩm) và
xử lý trần mới ở `GroupFrameHub`.

## Global Constraints

- Không đổi hành vi mặc định: `detect_scale = 1.0`, `CLAHE_FAST = true` (chỉ khác phần lãng phí), `crop_pad_ratio = 0.05` chỉ áp dụng khi `detect_scale < 1.0`.
- Cấu hình đọc theo thứ tự **DB > env > default** qua `app/utils/port_config_runtime.py` (DB thắng). Khoá mới: `clahe_fast`, `detect_scale`, `crop_pad_ratio`.
- Toạ độ full-res (`raw_frame`) là chuẩn cho tracker, ngưỡng lọc box, crop OCR/embedding, overlay, media. Quy đổi từ hệ detect chỉ được xảy ra một lần, ngay sau `predict_boxes`.
- Commit theo Conventional Commits, **không commit thẳng `main`** — làm trên nhánh `feature/pipeline-throughput`.
- Mọi thay đổi hành vi phải tắt được bằng cờ cấu hình (không cần sửa code để lùi).
- Test chạy bằng `make test` (pytest trong `server/`); kiểm tra hệ thống bằng `make check`, `make verify-engines`, `make bench`, `make ab-detect`.
- Cổng chất lượng A/B: P1 — cùng số box, 0 box lệch, IoU min ≥ 0.98, conf lệch max ≤ 0.03; P2 — IoU min ≥ 0.95, conf lệch max ≤ 0.05.
- Ngưỡng hiệu năng: CPU/frame đường detection giảm ≥ 2× **khi gray-world bật** (đo: 166 → 64 ms/frame; khi gray-world tắt, CLAHE_FAST không đổi gì); backend < 60 % CPU khi 2 camera; fps/camera = `record_fps` cấu hình (DB đang là 5) chứ không phải ≥ 20 — xem spec §9.

## Review Focus

- **Hợp đồng toạ độ**: mọi consumer (tracker, lọc min-size, crop OCR/embedding, overlay, media) chỉ được thấy toạ độ full-res; `detect_scale` không rò rỉ ra ngoài `_process_frame`.
- **Đường lùi**: `CLAHE_FAST=false` phải cho kết quả **bitwise** giống bản float32 hiện tại; `detect_scale=1.0` không được gọi `cv2.resize` cho detection.
- **Không vẽ đè lên frame nguồn**: sau `_process_frame`, `raw_frame` phải không bị sửa (nếu không, box sẽ lọt vào ảnh OCR/media).
- **Chi phí mỗi frame**: không thêm cấp phát lớn/pass dữ liệu mới trong vòng lặp; telemetry chỉ dùng bộ đếm số nguyên.
- **Biên**: frame rỗng/1 px, box ngoài biên, `detect_scale` biên (1.0, 0.5), ảnh không liên tục (non-contiguous), track bị khoá identity.

## File Structure

| File | Trách nhiệm | Trạng thái |
|---|---|---|
| `server/app/services/ai/clahe_preprocessor.py` | CLAHE + cân bằng sáng; thêm đường uint8 `fast` và giữ đường tham chiếu float32 | sửa |
| `server/app/utils/ai/box_scale.py` | Hàm thuần: quy đổi box theo tỉ lệ, nới crop có kẹp biên | mới |
| `server/app/services/ai/frame_stats.py` | Bộ đếm frame + fps theo camera (thread-safe, clock tiêm được) | mới |
| `server/app/services/ai/per_camera_pipeline.py` | Vòng lặp mỗi frame: detection frame, bỏ copy thừa khi không cần overlay, crop có pad, ghi telemetry | sửa |
| `server/app/services/pipeline_service.py` | Đọc cfg runtime (3 khoá mới), sở hữu `FrameStats`, log 30 s, thêm trường vào status | sửa |
| `server/app/core/config.py` | `CLAHE_FAST`, `DETECT_SCALE`, `CROP_PAD_RATIO` | sửa |
| `server/.env` | 3 khoá mới kèm chú thích | sửa |
| `server/app/utils/ai/box_compare.py` | Hàm so khớp box dùng chung (IoU, ghép cặp, tổng hợp) — đặt trong `server/` để pytest import được | mới |
| `scripts/ab_detect.py` | Harness A/B đường detection trên frame thật + kết luận ĐẠT/KHÔNG | mới |
| `Makefile` | `make ab-detect` | sửa |
| `server/app/tests/test_clahe_preprocessor.py` | Test đường fast vs tham chiếu | mới |
| `server/app/tests/test_box_scale.py` | Test quy đổi/nới box | mới |
| `server/app/tests/test_frame_stats.py` | Test đếm frame/fps | mới |
| `server/app/tests/test_pipeline_overlay_usage.py` | Test chỉ dựng overlay khi có consumer + `raw_frame` không bị vẽ đè (**thay** cho `test_overlay_scaling.py` vì phần vẽ ở tỉ lệ đích đã hoãn) | mới |

## Task 0: Nhánh làm việc + commit tài liệu

**Deliverable:** nhánh `feature/pipeline-throughput` tồn tại, spec + plan đã được commit trên nhánh đó (không đụng `main`).

- [ ] Tạo nhánh: `git checkout -b feature/pipeline-throughput`
- [ ] Kiểm tra nhánh: `git branch --show-current` → in ra `feature/pipeline-throughput`
- [ ] Stage riêng 2 file tài liệu: `git add docs/superpowers/specs/2026-09-29-pipeline-throughput-design.md docs/superpowers/plans/2026-09-29-pipeline-throughput.md`
- [ ] Commit: `docs(ai): spec + kế hoạch tối ưu throughput pipeline nhận diện`
- [ ] Xác nhận không có file code nào lọt vào commit: `git show --stat --oneline HEAD`

## Task 1: Hàm so khớp box dùng chung + harness A/B

**Deliverable:** `make ab-detect` chạy được, in bảng so sánh đường hiện tại vs đường ứng viên trên frame thật và tự kết luận ĐẠT/KHÔNG; exit code 0/1.

- [ ] Viết `scripts/box_compare.py` với:
  - `iou_matrix(box: np.ndarray, boxes: np.ndarray) -> np.ndarray` (box là mảng 4 phần tử xyxy)
  - `match_boxes(a_boxes, a_conf, b_boxes, b_conf, iou_thr=0.5) -> tuple[list[float], list[float], int, int]` trả `(ious, conf_deltas, only_a, only_b)`, ghép cặp tham lam theo IoU cao nhất, mỗi box dùng một lần
  - `summarize(n_a, n_b, ious, conf_deltas, only_a, only_b, *, iou_gate, conf_gate) -> dict` trả các khoá `boxes_a`, `boxes_b`, `matched`, `iou_min`, `iou_mean`, `conf_max`, `only_a`, `only_b`, `passed`, `reasons`
- [ ] Viết test `server/app/tests/test_box_compare.py`: 2 box trùng khít → `iou_min == 1.0`, `passed` True; 2 box lệch hoàn toàn → `only_a == 1`, `only_b == 1`, `passed` False; box dùng một lần (2 box A cùng khớp 1 box B → chỉ 1 cặp khớp)
- [ ] Chạy: `make test` → test mới pass
- [ ] Viết `scripts/ab_detect.py`:
  - `--frames-dir` (mặc định `/tmp/opt-test/boats`), `--capture N` (chụp N frame mới từ camera đang bật nếu thư mục trống, dùng `app.utils.ai.rtsp_capture.open_rtsp`)
  - `--candidate {clahe-uint8,no-grayworld,detect-scale}`, `--detect-scale 0.5`, `--conf` (mặc định `get_port_float('conf', 0.75)`), `--iou-gate 0.98`, `--conf-gate 0.03`, `--json`
  - Đường mốc = `preprocess_frame_clahe(frame, cfg, fast=False)`; đường ứng viên theo `--candidate`; box của `detect-scale` được nhân `1/scale` trước khi so
  - In 1 dòng kết quả mỗi ứng viên + `✓ ĐẠT`/`✗ KHÔNG ĐẠT`; exit 1 nếu không đạt
- [ ] Thêm target Makefile:
  ```
  ab-detect:
  	@$(PYX); python scripts/ab_detect.py $(AB_ARGS)
  ```
  và thêm `ab-detect` vào `.PHONY` + dòng help
- [ ] Chạy thật: `make ab-detect AB_ARGS="--candidate clahe-uint8 --iou-gate 0.98"` (khi đó `fast=True` và `fast=False` còn giống nhau nên phải ĐẠT với IoU ≈ 1.0) → xác nhận harness hoạt động đúng
- [ ] Chạy `make test` và `make verify-engines` (không hồi quy)
- [ ] Commit: `test(ai): harness A/B detection cho đường tiền xử lý (make ab-detect)`

## Task 2: CLAHE uint8 (P1a)

**Deliverable:** `preprocess_frame_clahe` mặc định dùng đường uint8 nhanh ~4×, giữ nguyên hình học, có cờ `CLAHE_FAST=false` quay lại bản float32 bitwise.

- [ ] Thêm test `server/app/tests/test_clahe_preprocessor.py`:
  - `test_fast_gray_world_disabled_is_bitwise_identical`: ảnh gradient + nhiễu, `enable_gray_world=False` → `preprocess_frame_clahe(img, cfg, fast=True)` bằng đúng `fast=False`
  - `test_rollback_flag_uses_reference`: với `settings.CLAHE_FAST = False`, gọi không truyền `fast` → kết quả bằng đúng `fast=False` (bitwise)
  - `test_fast_close_to_reference_with_gray_world`: `enable_gray_world=True` → mean abs diff ≤ 2.0 mức uint8 và ≥ 99 % pixel lệch ≤ 4
  - `test_dtype_shape_preserved`: ảnh 3 kênh uint8, cả ảnh non-contiguous (`img[:, ::-1]`) → đầu ra cùng shape/dtype/contiguous
  - `test_empty_frame_passthrough`: `np.zeros((0,0,3), np.uint8)` → trả về chính nó
- [ ] Chạy `make test` → các test mới **fail** (chưa có `fast`)
- [ ] Sửa `server/app/services/ai/clahe_preprocessor.py`:
  - `ClahePreprocessConfig` thêm trường `fast: bool = True`
  - `preprocess_frame_clahe(frame_bgr, config=None, *, fast: bool | None = None)`; `fast is None` → lấy `config.fast`
  - Tách phần dùng chung: `_apply_clahe_lab(frame_uint8, cfg)` (BGR2LAB → split → CLAHE L → merge → LAB2BGR)
  - Đường tham chiếu giữ nguyên thuật toán cũ: `_gray_world_balance_reference(frame) -> np.ndarray` (float32, y hệt bản hiện tại, kể cả `astype(np.uint8)` cuối)
  - Đường nhanh: `_gray_world_balance_fast(frame) -> np.ndarray` dùng `cv2.mean(frame)[:3]`, `scale_i = g / max(mean_i, 1.0)`, `cv2.convertScaleAbs(np.ascontiguousarray(frame[:, :, i]), alpha=scale_i)`, `cv2.merge`
  - Đường tham chiếu nhận frame float32 trả về từ `_gray_world_balance_reference` như hiện tại (giữ đúng hành vi cũ, kể cả việc BGR2LAB chạy trên float32)
- [ ] Chạy `make test` → pass toàn bộ (272 + test mới)
- [ ] A/B trên frame thật: `make ab-detect AB_ARGS="--candidate clahe-uint8 --iou-gate 0.98 --conf-gate 0.03"` → in `✓ ĐẠT`
- [ ] Đo tốc độ: chạy lại harness với `--json`, ghi số ms/frame trước/sau vào phần báo cáo cuối (không tạo file .md)
- [ ] Thêm `CLAHE_FAST: bool = True` vào `server/app/core/config.py` + `CLAHE_FAST=true` kèm chú thích trong `server/.env`
- [ ] Chạy `make test` → pass
- [ ] Commit: `perf(ai): CLAHE chạy uint8 nhanh 4x, giữ nguyên hình học (CLAHE_FAST)`

## Task 3: Bỏ copy thừa + overlay ở tỉ lệ đích (P1b)

**Deliverable:** `_process_frame` không copy full-res khi không có consumer overlay, vẽ overlay ở tỉ lệ đích; `raw_frame` không bị sửa.

- [ ] Đọc `app/utils/ai/overlay.py` (hàm `draw_ship_detection_overlay` và đoạn `resize_scale != 1.0`) và `draw_berth_state_bbox_overlays`, `draw_boundary_lines` để chốt cách truyền tỉ lệ (giữ nguyên chữ ký cũ, thêm tham số `scale: float = 1.0` khi cần)
- [ ] Thêm test `server/app/tests/test_overlay_scaling.py`:
  - `test_overlay_output_size_follows_scale`: frame 800×400, `scale=0.5` → ảnh ra 400×200
  - `test_box_drawn_at_scaled_coordinates`: track có box biết trước `(100, 50, 300, 150)`, `scale=0.5` → pixel tại `(51, 26)` (viền box đã scale, sai số ±1 px) mang màu của track; pixel ngoài box giữ nguyên màu nền
  - `test_source_frame_not_modified`: so `raw_frame.copy()` trước/sau lời gọi vẽ → bằng nhau (bitwise)
- [ ] Chạy `make test` → test mới fail
- [ ] Sửa `server/app/services/ai/per_camera_pipeline.py`:
  - Tính `needs_overlay = bool(self.config.enable_preview_stream or self._on_overlay_media_sample or self._on_boundary_media_sample or record_queues)` **trước** khi vẽ
  - Nếu `needs_overlay` False → bỏ toàn bộ phần tạo `annotated`/overlay
  - Nếu True → tạo **một** buffer: `overlay_frame = cv2.resize(raw_frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)` khi `scale != 1.0`, rồi vẽ trực tiếp lên đó với toạ độ đã nhân `scale` (không vẽ lên `raw_frame`, không copy thêm)
  - `scale = self.config.resize_scale` (đang dùng cho overlay/media) — giữ nguyên giá trị 0.5 như hiện tại
- [ ] Chạy `make test` → pass
- [ ] Kiểm tra bằng mắt: lưu 1 ảnh overlay trước và sau thay đổi trên cùng frame + cùng track (script nhỏ trong `/tmp`), so vị trí box hai ảnh lệch ≤ 2 px ở tỉ lệ đích
- [ ] Commit: `perf(ai): bỏ copy full-res thừa và vẽ overlay ở tỉ lệ đích`

## Task 4: Telemetry fps/frame (P1c)

**Deliverable:** `/api/v1/pipeline/status` trả `frames_processed` và `fps_per_camera`; log 30 s một lần; chi phí mỗi frame chỉ là tăng bộ đếm.

- [ ] Thêm test `server/app/tests/test_frame_stats.py`:
  - `test_counts_and_fps_with_injected_clock`: clock giả tăng 0.04 s mỗi lần gọi, 25 lần `record(1)` → `fps(1) ≈ 25.0` (sai số 5 %), `totals()[1] == 25`
  - `test_fps_none_before_two_samples`
  - `test_thread_safety_smoke`: 4 thread × 200 `record` → tổng đúng 800
  - `test_snapshot_keys_are_camera_ids`
- [ ] Chạy `make test` → fail
- [ ] Viết `server/app/services/ai/frame_stats.py`: `FrameStats(clock=time.monotonic, window_sec=60.0)` với `record(camera_id)`, `fps(camera_id) -> float | None`, `totals() -> dict[int, int]`, `snapshot() -> dict[int, float]`; giữ deque timestamp theo camera trong cửa sổ `window_sec`
- [ ] Chạy `make test` → pass
- [ ] Sửa `server/app/services/pipeline_service.py`: tạo `self._frame_stats = FrameStats()`; truyền vào `PerCameraPipeline` (tham số mới `frame_stats=`); log mỗi 30 s `logger.info('fps theo camera: %s', ...)` trong vòng monitor sẵn có; bổ sung 2 trường `frames_processed`, `fps_per_camera` vào payload `GET /pipeline/status`
- [ ] Sửa `server/app/services/ai/per_camera_pipeline.py`: gọi `self._frame_stats.record(camera_id)` ở đầu `_process_frame` (chỉ khi `frame_stats is not None`)
- [ ] Chạy `make test` → pass; `make check` → 32 PASS
- [ ] Restart app và đọc status: `make restart` rồi `curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/v1/pipeline/status` → thấy `fps_per_camera` có giá trị (kỳ vọng 2-3 fps trước P1, tăng mạnh sau P1)
- [ ] Commit: `feat(ai): telemetry fps/frame cho từng camera`

## Task 5: `detect_scale` + `crop_pad_ratio` (P2, mặc định tắt)

**Deliverable:** bật `detect_scale=0.5` thì CLAHE+detection chạy ở 1280×720, box quy về full-res, crop OCR/embedding được nới; mặc định 1.0 giữ nguyên hành vi.

- [ ] Thêm test `server/app/tests/test_box_scale.py`:
  - `test_scale_boxes_roundtrip`: box `[[100, 50, 300, 150]]`, scale 0.5 rồi 2.0 → sai số ≤ 1e-6
  - `test_scale_boxes_empty`: mảng rỗng `(0, 4)` → trả về mảng rỗng cùng dtype
  - `test_pad_box_clamped_to_frame`: box sát biên `(0, 0, 10, 10)`, ratio 0.5, frame 100×100 → `(0, 0, 15, 15)`
  - `test_pad_box_ratio_zero_is_identity`
- [ ] Chạy `make test` → fail
- [ ] Viết `server/app/utils/ai/box_scale.py`: `scale_boxes(boxes, factor) -> np.ndarray` (giữ dtype float32), `pad_box(box, ratio, width, height) -> tuple[int, int, int, int]` (kẹp `[0, width]`/`[0, height]`)
- [ ] Chạy `make test` → pass
- [ ] Thêm `DETECT_SCALE: float = 1.0`, `CROP_PAD_RATIO: float = 0.05` vào `server/app/core/config.py` + 2 dòng tương ứng trong `server/.env`
- [ ] Sửa `pipeline_service._load_runtime_config`: `'detect_scale': self._to_float(cfg_map.get('detect_scale',''), float(settings.DETECT_SCALE))`, `'crop_pad_ratio': self._to_float(cfg_map.get('crop_pad_ratio',''), float(settings.CROP_PAD_RATIO))`, và truyền vào `PerCameraPipeline`
- [ ] Sửa `per_camera_pipeline.py`:
  - `det_frame = raw_frame if scale == 1.0 else cv2.resize(raw_frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)`
  - `processed = preprocess_frame_clahe(det_frame, self._clahe_config)`
  - sau `predict_boxes`: `if scale != 1.0: boxes_list = scale_boxes(boxes_list, 1.0 / scale)` — **điểm quy đổi duy nhất**, trước `filter_boxes_by_min_size`
  - trong `_enrich_track`: khi `scale != 1.0` thay `clamp_box(...)` bằng `pad_box(track.box, crop_pad_ratio, width, height)`; khi `scale == 1.0` giữ nguyên `clamp_box` như hiện tại
  - thêm `detect_scale` vào payload status (để nhìn là biết chế độ)
- [ ] Thêm test `test_detect_scale_default_off`: dựng `PerCameraPipeline` với cấu hình mặc định và monkeypatch `cv2.resize` đếm số lần gọi → 0 lần cho detection (chứng minh mặc định không đổi hành vi)
- [ ] Chạy `make test` → pass
- [ ] A/B cổng P2: `make ab-detect AB_ARGS="--candidate detect-scale --detect-scale 0.5 --iou-gate 0.95 --conf-gate 0.05"` → `✓ ĐẠT`
- [ ] Commit: `feat(ai): detect_scale + crop_pad_ratio cho detection (mặc định tắt)`

## Task 6: Nghiệm thu

**Deliverable:** số đo trước/sau và xác nhận không hồi quy; báo cáo trong chat.

- [ ] `make test` → tất cả pass (272 + test mới)
- [ ] `make check` → 32 PASS · 0 FAIL
- [ ] `make verify-engines` → `✓ Tất cả khớp.`
- [ ] `make ab-detect AB_ARGS="--candidate clahe-uint8"` → ĐẠT (P1) và ghi lại `ms/frame` trước/sau
- [ ] `make bench` → ghi lại số CPU/VRAM (so với baseline 2026-09-29)
- [ ] A/B app thật 60 s: `make stop`, `make start`, lấy mẫu CPU/VRAM/GPU, đọc `fps_per_camera` từ status → so với baseline (114.3 % CPU, 23.3 % GPU, 2.5-3 fps/camera)
- [ ] Chạy `detect_scale=0.5` (đặt qua DB, không sửa .env) → đo lại 60 s + `make ab-detect` → rồi trả `detect_scale` về 1.0
- [ ] Cập nhật `git status`, liệt kê commit trên nhánh; báo cáo số liệu và đề xuất bước tiếp theo (merge/tạo PR)
