# Tối ưu throughput pipeline nhận diện (CLAHE + vòng lặp frame)

- Ngày: 2026-09-29
- Trạng thái: chờ duyệt spec
- Phạm vi đã chốt với chủ dự án: **P1 (bắt buộc) + P2 (tuỳ chọn, opt-in)**
- Cổng chất lượng đã chốt: P1 phải đạt IoU ≥ 0.98 và conf lệch ≤ 0.03 so với hiện tại trên frame thật; P2 chỉ được bật khi tự đo đạt IoU ≥ 0.95.

## 1. Bối cảnh và số đo baseline

Đo trên app đang chạy (2 camera nhóm 7, luồng 2560×1440 h265, engine TensorRT đã bật), ngày 2026-09-29:

| Chỉ số | Giá trị đo |
|---|---|
| CPU backend (10 s) | **114.3 %** (5 thread nóng: 34.1 / 33.9 / 16.1 / 13.1 / 12.6 %) |
| CPU 2 tiến trình decode | 13.6 % + 12.9 % |
| GPU util | 23.3 % |
| VRAM toàn app | 1218 MB (backend 428 · OCR 454 · decode 2×168) |
| OCR worker khi bãi trống | ~0 % (idle) |
| fps/camera suy ra (SAI — xem §9) | ~~≈ 2.5-3 fps~~ — suy diễn từ ngân sách CPU. Đo thật sau này: **5.0 fps/camera**, đúng bằng `record_fps=5` trong DB; nguồn RTSP thật đo được 19.9 fps |

Ngân sách từng bước (frame thật 2560×1440, engine imgsz=960):

| Bước | Chi phí đo được |
|---|---|
| `preprocess_frame_clahe` full-res | **133.9 ms** |
| copy frame full-res | 2.29 ms (×2-3 lần/frame) |
| letterbox → 960 | 0.47 ms |
| `cv2.resize` 2560×1440 → 1280×720 | 0.27 ms |
| JPEG encode 1280×720 q82 | 6.42 ms (đã có thread riêng, có giới hạn fps) |
| H2D 11 MB / 2.7 MB | 2.86 ms / 0.64 ms |
| GPU: H2D + resize 960 + /255 + fp16 | 3.42 ms (full) · 1.18 ms (half) |

Kết luận: máy **nghẽn CPU ở CLAHE**, không nghẽn GPU. GPU còn dư 3/4 công suất.

## 2. Mục tiêu / phi mục tiêu

Mục tiêu:
1. Giảm CPU mỗi frame để pipeline chạy tới fps cấu hình (và tới fps luồng nếu nâng `record_fps`) và còn dư máy cho nhiều camera hơn trên cùng GPU.
2. Không đổi chất lượng OCR và ảnh overlay/media.
3. Đo được: có telemetry fps/frame để lần sau không phải suy luận.

Phi mục tiêu (không làm trong spec này):
- Chuyển tiền xử lý lên GPU / zero-copy tensor vào engine (đo chỉ lợi ~1-2 ms/frame, phải bỏ đường `predict` của ultralytics ⇒ rủi ro không tương xứng).
- TensorRT cho PaddleOCR (đang bị bug converter của Paddle 3.3.0).
- NVENC cho ghi video (đang `record_enable=false`).
- Gộp batch nhiều camera vào một lần suy luận.
- Đổi `output_scale` của GStreamer (hạ độ phân giải ngay ở luồng decode): tiết kiệm thêm ~2-3 ms/frame nhưng sẽ làm crop OCR mất chi tiết vì OCR đang cắt từ `raw_frame` full-res. Muốn làm thì phải làm P2 trước rồi đo lại chất lượng OCR.

## 3. Nguyên nhân gốc

`ClahePreprocessor._gray_world_balance()` chuyển **cả frame sang float32** (44 MB cho frame 2560×1440) chỉ để tính mean 3 kênh rồi nhân lại và hạ về uint8. Đo lại phân rã `preprocess_frame_clahe` (20 vòng, frame camera 2560×1440):

| Bước | Chi phí | Ghi chú |
|---|---|---|
| `_gray_world_balance` float32 (astype + reshape-mean + scale + clip + astype) | **83.5 ms** | **80 % tổng thời gian** |
| `LAB2BGR` uint8 | 3.63 ms | |
| `split` | 2.07 ms | |
| `BGR2LAB` uint8 | 1.93 ms | (đường float32 mất 19.1 ms nhưng **không** nằm trên đường chạy thật) |
| `CLAHE.apply` kênh L | 1.30 ms | thuật toán thật rất rẻ |
| `merge` | 0.49 ms | |
| **Tổng** | **≈ 104 ms** (dao động 104-137 ms tuỳ tải máy) | |

Tức ~80 % thời gian nằm ở bước cân bằng sáng chọn kiểu dữ liệu sai, không phải thuật toán. CLAHE chỉ cấp cho **một** nơi dùng: lời gọi `preprocess_frame_clahe` trong `per_camera_pipeline._process_frame` → `detector.predict_boxes` (ở HEAD là dòng 363). OCR crop, overlay, media đều dùng `raw_frame` gốc, nên sửa CLAHE **không** ảnh hưởng OCR/overlay.

**Số trên chỉ đúng khi `clahe_enable_gray_world = true`.** Cấu hình production đang đặt
`clahe_enable_gray_world = false` trong `port_configs` (khớp `PROD_CFG` của
`fine-tune/yolo/eval_clahe_ab.py`) — khi đó bước cân bằng sáng bị bỏ hoàn toàn và `fast`
**không đổi gì**. Đo lại trên 4 frame thật 2560×1440:

| Cấu hình | Bản cũ float32 | Bản uint8 (`fast`) |
|---|---|---|
| gray-world **OFF** (đang chạy) | 28.4 ms | 28.4 ms (y hệt) |
| gray-world **ON** | 125.4 ms | **40.6 ms** (−85 ms/frame) |

Nghĩa là P1 là việc **có điều kiện**: nó không tăng tốc cấu hình đang chạy, mà làm cho việc
bật gray-world trở nên rẻ (từ +97 ms xuống +12 ms mỗi frame) — xem §9 và §12.

## 4. Phương án đã cân nhắc

| | Phương án | Đo được | Quyết định |
|---|---|---|---|
| P1 | Sửa CLAHE sang uint8 (giữ nguyên hình học) + bỏ copy thừa + telemetry (phần overlay ở tỉ lệ đích **hoãn**) | gray-world ON: CLAHE 104→30.6 ms, `--candidate clahe-uint8` IoU min **0.9950**, **166→64 ms/frame**. gray-world OFF (cấu hình thật): IoU min **1.0000**, 61→63 ms/frame (không đổi) | **làm** |
| P2 | Hạ CLAHE+detection xuống `detect_scale` (mặc định 1.0) | CLAHE ở 1280×720 = 4.37 ms; A/B: 8/8 box, IoU min 0.9630, conf lệch max 0.0283; ~124→17 ms/frame | **làm, opt-in** |
| P3 | Đẩy tiền xử lý lên GPU, zero-copy vào engine | tiết kiệm ~1-2 ms/frame sau khi có P1 | loại (YAGNI) |
| — | Bỏ gray-world | IoU min 0.9705 | loại (dưới gate, lại mất cân bằng sáng) |

Ghi chú về bằng chứng: phép A/B ở trên chạy trên **4 frame thật khác nhau có tàu** (lấy từ camera 4, 5, 6, 7 — mỗi frame được lưu 2 lần nên thành 8 file). Trước khi nghiệm thu P1/P2 phải chạy lại trên **≥8 frame khác nhau** theo cổng ở mục 9.

## 5. Thiết kế P1

1. `app/services/ai/clahe_preprocessor.py`
   - `_gray_world_balance` chuyển sang uint8: `cv2.mean()` lấy mean 3 kênh, scale từng kênh bằng `cv2.convertScaleAbs` (giữ nguyên công thức `g / max(mean, 1.0)`, kẹp 0-255 như cũ).
   - `preprocess_frame_clahe` giữ `BGR2LAB`/`LAB2BGR` trên **uint8**; nhánh `enable_adaptive_threshold` giữ nguyên hành vi.
   - Cờ `CLAHE_FAST` (mặc định `true`): khi `false` quay lại đúng bản float32 hiện tại (đường lùi không cần sửa code).
   - Giữ nguyên API: `ClahePreprocessConfig`, chữ ký `preprocess_frame_clahe(frame, config)`.
2. `app/services/ai/per_camera_pipeline.py`
   - Bỏ `annotated = raw_frame.copy()` khi không có consumer nào cần overlay ở frame đó; chỉ tạo buffer overlay **một lần** khi preview/media/record đang bật.
   - Vẽ overlay ở **đúng tỉ lệ đích** (`resize_scale`): **HOÃN** — đo được chỉ ~1.4 ms/frame, phải sửa toạ độ/font/offset của 3 hàm vẽ; đợt này chỉ thêm guard bỏ hẳn phần vẽ khi không consumer nào cần.
   - Bản copy full-res cho payload OCR **vẫn giữ** (`frame.copy()` khi đẩy job OCR): hàng đợi chạy ở thread khác nên không thể dùng chung buffer với vòng lặp camera. Chi phí ~2.3 ms/frame, chấp nhận.
3. `app/services/pipeline_service.py`
   - Đếm `frames_processed` / `frames_dropped` (nếu đo được) theo camera, log mỗi 30 s, và bổ sung trường **thêm** vào `GET /api/v1/pipeline/status` (`frames_processed`, `fps_per_camera`). Chỉ dùng bộ đếm, không thêm việc nặng mỗi frame.
4. `app/utils/ai/gpu_probe.py`: không đổi trong P1.

## 6. Thiết kế P2 (opt-in)

- Cấu hình mới `detect_scale` (DB `detect_scale`, env `DETECT_SCALE`, mặc định **1.0** = hành vi hiện tại).
- Khi `detect_scale < 1.0`: `detect_frame = cv2.resize(raw_frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)` → CLAHE → detector.
- Box trả về được quy về toạ độ `raw_frame` bằng **một** hàm duy nhất, gọi ngay sau `predict_boxes` (trước `filter_boxes_by_min_size`, `dedup_overlapping_boxes`, tracker, `_enrich_track`, overlay) để mọi ngưỡng px và mọi consumer giữ nguyên đơn vị full-res.
- Khi `detect_scale < 1.0`, crop cho OCR/embedding được nới thêm `crop_pad_ratio` (mặc định 0.05, chỉ áp dụng khi scale < 1.0) để bù box lệch vài px, tránh cắt lẹm biển số. Box nới được tính **một lần** trong pipeline rồi dùng cho cả `_enrich_track`, queue OCR và queue visual (`_queue_boxes`) — nếu chỉ nới ở embedding thì hai đường embedding sẽ lệch nhau.
- `detect_scale` xuất hiện trong `/pipeline/status` để nhìn là biết đang chạy chế độ nào.

## 7. Hợp đồng toạ độ (bất biến của thiết kế)

- `raw_frame`: toạ độ full-res — dùng cho tracker, ngưỡng lọc box, `_enrich_track` (crop OCR/embedding), overlay, media. **Không đổi.**
- `detect_frame`: toạ độ theo `detect_scale` — chỉ tồn tại từ lúc resize đến lúc `predict_boxes` trả về.
- Quy đổi đúng **một điểm** trong `_process_frame`; không nơi nào khác được biết `detect_scale`.
- Kiểm thử bắt buộc: với `detect_scale = 0.5`, box sau quy đổi phải nằm trong biên frame và khớp box của `detect_scale = 1.0` trong dung sai A/B.

## 8. Cấu hình mới

| Khoá | Kiểu | Mặc định | Ý nghĩa |
|---|---|---|---|
| `CLAHE_FAST` | bool | `true` | dùng bản CLAHE uint8; `false` = bản float32 cũ |
| `detect_scale` | float | `1.0` | tỉ lệ frame đưa vào CLAHE+detector; `0.5` = nhanh nhất |
| `crop_pad_ratio` | float | `0.05` | nới crop OCR/embedding khi `detect_scale < 1.0` |

Cả ba đọc qua `port_config_runtime` (DB thắng env) như các khoá hiện có.

## 9. Kiểm thử và cổng nghiệm thu

Công cụ mới: `scripts/ab_detect.py` + `make ab-detect` — lấy N frame thật (từ camera đang bật hoặc từ thư mục frame đã lưu), chạy **đường hiện tại** vs **đường ứng viên**, in số box, IoU khớp, lệch conf, số box lệch, và kết luận ĐẠT/KHÔNG theo gate. Hàm so khớp nằm ở `server/app/utils/ai/box_compare.py` (đặt trong `server/` để pytest import được; `scripts/verify_engines.py` chưa được commit nên không dùng lại được — ghi nhận là nợ kỹ thuật của luồng model/engine).

Harness chạy qua `make ab-detect` (tự `cd server`) để đọc đúng `.env` + DB; nếu không đọc được
`port_configs` thì nó **cảnh báo** và in rõ baseline đang giả định gray-world ON/OFF. Đường
baseline là bản CLAHE float32 cũ, đo có warmup và **đổi thứ tự mỗi frame** để không thiên lệch
đường chạy trước; số frame **khác nhau** được đếm riêng (8 bản copy của 1 frame không tính là 8).

Cổng:
- **P1**: trên ≥8 frame thật **khác nhau** có tàu (≥2 camera), ở cả `conf=0.75` và `conf=0.25`: cùng số box, 0 box lệch, IoU min ≥ 0.98, conf lệch max ≤ 0.03. Hai đường cùng 0 box ⇒ reason `empty_scene` ⇒ **KHÔNG ĐẠT** (bến trống không chứng minh được gì).
- **P1 hiệu năng**: CPU/frame của đường detection giảm ≥ 2× **khi gray-world bật** (đo bằng harness: 166 → 64 ms/frame ✓). Ở cấu hình đang chạy (gray-world tắt trong DB) hai đường **y hệt nhau**: IoU min 1.0000, 61 → 63 ms/frame — P1 là việc có điều kiện, xem §3.
- **fps/camera (sửa lại so với bản đầu)**: pipeline đạt đúng `record_fps` cấu hình, **5.0 fps/camera** với 2 camera; tiêu chí "≥ 20 fps/camera" ở bản đầu **sai** vì `FrameReaderThread` chặn theo `1/record_fps`. Bằng chứng: đặt `CLAHE_FAST=false` (đường CLAHE cũ, đắt gấp 4) vẫn đạt 5.0 fps/camera → pipeline **không** bị chặn bởi CPU ở mức cấu hình này, và suy luận "baseline ~2.5-3 fps" trong bản đầu là suy diễn từ ngân sách CPU, **không phải số đo**. Khi nâng thử `record_fps=15`: CPU 140 % → 433 % nhưng fps/camera **vẫn ~5** → trần tiếp theo nằm ở coordinator của `GroupFrameHub`, không phải detector.
- **P2**: cùng số box, IoU min ≥ 0.95, conf lệch max ≤ 0.05, và `detect_scale` vẫn mặc định 1.0 (không đổi hành vi nếu không bật). Đo theo cấu hình hiệu lực: 8→8 box, IoU min **0.9704**, conf lệch max 0.0166, 0 box lệch, **67 → 23 ms/frame** ✓.
- **Không hồi quy**: `make test` 322 pass, `make check` 32/32, `make verify-engines` đạt, `make ab-detect` chạy được trên bản checkout sạch (đã kiểm bằng `git archive HEAD`).
- **Overlay**: phần vẽ ở tỉ lệ đích **hoãn** (xem §5.2) nên không có test toạ độ theo tỉ lệ đích; thay vào đó `test_pipeline_overlay_usage.py` khẳng định overlay chỉ được dựng khi có consumer (preview/ghi hình/track CONFIRMED cho callback media) và `raw_frame` không bị vẽ đè.

## 10. Đo nghiệm thu

1. Baseline: chạy `make bench` + A/B app thật 60 s (CPU/VRAM/GPU) — đã có số ngày 2026-09-29.
2. Sau P1: lặp lại đúng hai phép đo đó, ghi số CPU/frame, CPU backend, fps/camera.
3. Sau P2 (bật thử `detect_scale=0.5`): lặp lại, kèm `make ab-detect` để xác nhận gate.
4. Báo cáo số trước/sau trong chat; không tạo file .md tóm tắt thay đổi.

## 11. Rủi ro, giảm thiểu, đường lùi

| Rủi ro | Giảm thiểu |
|---|---|
| gray-world uint8 làm pixel lệch nhẹ | Chỉ xảy ra khi gray-world bật (cấu hình production đang tắt nên IoU min 1.0000); khi bật, A/B đo IoU min 0.9950 (gate 0.98). `CLAHE_FAST=false` quay lại bản cũ tức thì |
| Bỏ copy gây vẽ đè lên frame nguồn (box lọt vào ảnh OCR/media) | Chỉ vẽ lên buffer mới tạo một lần; unit test khẳng định `raw_frame` không bị sửa sau `_process_frame` |
| `detect_scale < 1.0` làm box lệch, cắt lẹm biển số | Mặc định 1.0; gate 0.95; `crop_pad_ratio`; cảnh báo trong status/log khi bật |
| Telemetry thêm chi phí mỗi frame | Chỉ tăng bộ đếm số nguyên; log định kỳ 30 s, không format chuỗi mỗi frame |
| Đổi overlay sang vẽ ở tỉ lệ đích làm nét vẽ khác trước | **Hoãn, không làm trong đợt này**: đo được chỉ ~1.4 ms/frame nhưng phải sửa toạ độ/font/offset của 3 hàm vẽ; Task 3 chỉ thêm guard bỏ overlay khi không có consumer nên nét vẽ không đổi |

Đường lùi tổng thể: mọi thay đổi hành vi đều nằm sau cờ cấu hình (`CLAHE_FAST`, `detect_scale`, `crop_pad_ratio`), tắt cờ là về hành vi hiện tại mà không cần sửa code; ngoài ra revert commit trên nhánh `feature/*`.

## 12. Việc tiếp theo (phát hiện khi nghiệm thu, chưa làm)

Số đo ở `record_fps=15` cho thấy trần fps hiện tại không còn ở detector mà ở vòng lặp khung:

1. **CLAHE chạy ở full-res rồi bị letterbox thu nhỏ** — ở cấu hình production (gray-world
   tắt) CLAHE vẫn tốn **28.4 ms/frame** (4 frame thật 2560×1440) trong khi detector chỉ nhận
   ảnh 960×544; phần chi tiết CLAHE tạo ra bị chính bước resize xoá đi. Làm CLAHE **sau** khi
   thu nhỏ về kích thước detector (~0.2 MP thay vì 3.7 MP) ước tính còn ~4 ms/frame, tức bỏ
   được ~24 ms/frame (~1/3 ngân sách frame hiện tại ~70 ms) — cần A/B vì CLAHE ở hai độ phân
   giải cho kết quả không giống nhau (cổng IoU ≥ 0.98 như P1).
2. **Reader đọc rồi vứt frame** — `MultiFrameReaderThread.run()` đọc frame ở đầu vòng lặp rồi `continue` khi chưa tới nhịp phát (`multi_frame_reader.py:167-172`), không sleep; hub lại đặt `reader_fps = 2 × record_fps` nên ở `record_fps=15` mỗi reader kéo ~20 fps từ nguồn và vứt ~2/3. Bằng chứng: CPU backend 140 % → 433 % khi nâng `record_fps` 5 → 15 mà fps xử lý không đổi. Hướng sửa: sleep tới `next_emit` thay vì đọc lại.
3. **Coordinator `GroupFrameHub` là trần thật** — mỗi batch còn: fuse 2 camera, vẽ overlay + boundary lên canvas, JPEG + push preview dashboard, `_last_aligned_batch` copy, và copy thêm một lần cho mỗi queue per-camera (`group_frame_hub.py:378-400`). Hướng sửa: bỏ copy thừa, chỉ dựng/encode preview khi có client WS đang mở.
4. **`_enqueue_media_sample` copy canvas fused trước khi kiểm tra track CONFIRMED** (`pipeline_service.py:877-882`) — bỏ được khi không có track, cùng lập luận với ruling ở Task 3.


## 13. Kế hoạch thi công sơ bộ (bản gốc, giữ để đối chiếu)

1. Tách hàm so khớp box dùng chung + `scripts/ab_detect.py` + `make ab-detect` (làm trước để có thước đo).
2. P1a: CLAHE uint8 + unit test đối chiếu số học với bản cũ + A/B qua harness.
3. P1b: bỏ copy thừa + overlay ở tỉ lệ đích + unit test toạ độ — **phần overlay ở tỉ lệ đích đã hoãn**, xem §5.2.
4. P1c: telemetry fps/frame + trường mới trong `/pipeline/status`.
5. P2: `detect_scale` + quy đổi toạ độ một điểm + `crop_pad_ratio` + A/B (mặc định tắt).
6. Nghiệm thu: `make test`, `make check`, `make verify-engines`, `make bench`, A/B app thật 60 s; ghi số trước/sau.

Kế hoạch chi tiết nằm ở `docs/superpowers/plans/2026-09-29-pipeline-throughput.md` (kèm bảng
Trạng thái thực thi ở đầu file).
