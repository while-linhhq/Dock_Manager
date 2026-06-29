# Zone-Gated Identity Vote

**Date:** 2026-06-29  
**Status:** Approved

## Problem

OCR và embedding nhận diện tàu ngay khi tàu xuất hiện trong frame — kể cả khi tàu đang di chuyển ngoài vùng neo. Các phiếu vote thu thập lúc đó nhiễu (ảnh mờ, góc xấu, bbox nhỏ) và ảnh hưởng đến final ship_id. Muốn pool vote chỉ nhận phiếu khi tàu thực sự neo trong berth zone và bbox chiếm đủ diện tích vùng.

## Yêu cầu

- OCR và embedding **vẫn chạy** từ đầu (overlay hiển thị bình thường).
- Vote chỉ vào pool khi `berth_zone_overlap >= berth_zone_threshold` trên track đó.
- Khi overlap < threshold: phiếu bị bỏ qua, pool không thay đổi.
- Pool đã tích lũy **không bị xóa** khi tàu rời zone (option A).
- Camera không cấu hình berth zone → không gate (backward compatible).

## Thiết kế

### Gate logic

Thêm helper `_is_in_recognition_zone(track)` trong `per_camera_pipeline.py`:

```python
def _is_in_recognition_zone(self, track: TrackedBoat) -> bool:
    overlap = getattr(track, 'berth_zone_overlap', None)
    threshold = getattr(track, 'berth_zone_threshold', None)
    if overlap is None or threshold is None:
        return True  # camera không config zone → không gate
    return overlap >= threshold
```

### Gate điểm

**`_on_ocr_result`** trong `per_camera_pipeline.py` — thêm trước `report_ocr_result`:

```python
track = self._tracker.get_track(track_id)
if track and not self._is_in_recognition_zone(track):
    return  # skip vote; overlay cache đã update ở worker
```

**`_on_visual_result`** trong `per_camera_pipeline.py` — thêm trước đoạn gọi `report_ocr_result` + `update_track_metadata`:

```python
track = self._tracker.get_track(track_id)
if track and not self._is_in_recognition_zone(track):
    return  # skip vote; ocr_cache entry vẫn còn emb overlay
```

### Không thay đổi

- `OcrWorkerThread`, `VisualIdWorkerThread` — chạy bình thường, vẫn update `ocr_cache` (overlay).
- `BoatTracker.add_ocr_vote` — không đổi signature.
- `CrossCameraReIdManager` — không đổi.
- `update_ship_id_stability` / lock logic — không đổi. Lock tự không trigger vì pool không nhận phiếu mới khi ngoài zone.
- `berth_zone_overlap` / `berth_zone_threshold` đã có sẵn trên `TrackedBoat` từ pipeline hiện tại.

## Data flow

```
RTSP frame
  → YOLO detect → BoatTracker.update() → TrackedBoat (berth_zone_overlap cập nhật mỗi frame)
      → OcrWorkerThread.recognize()
          → callback _on_ocr_result(track_id, sid, conf)
              → _is_in_recognition_zone(track)?
                  NO  → return (overlay đã ok, vote bị gate)
                  YES → add_ocr_vote + report_ocr_result → pool
      → VisualIdWorkerThread.embed()
          → callback _on_visual_result(track_id, ship_id, conf, source, top_k)
              → update ocr_cache (emb overlay)
              → _is_in_recognition_zone(track)?
                  NO  → return
                  YES → report_ocr_result + update_track_metadata → pool
```

## Cạnh trường hợp

| Tình huống | Xử lý |
|---|---|
| `berth_zone_overlap=None` (camera không có zone) | `_is_in_recognition_zone` trả `True` → không gate |
| `berth_zone_threshold=None` | Tương tự, không gate |
| Track bị remove trước khi callback fire | `get_track` trả `None` → `not None and ...` = False → không gate (vote cho phép) |
| Tàu vào zone → vote → rời zone → vào lại | Pool giữ nguyên, tiếp tục cộng dồn |
| Lock đã set trước khi vào zone | `_on_ocr_result` check `is_track_identity_locked` trước gate → skip sớm hơn (không đổi) |

## Test

Thêm vào `server/app/tests/test_zone_gated_vote.py`:

1. Track với `berth_zone_overlap=0.1`, `threshold=0.3` → `_on_ocr_result` không gọi `add_ocr_vote`.
2. Track với `berth_zone_overlap=0.5`, `threshold=0.3` → vote vào pool bình thường.
3. Track với `berth_zone_overlap=None` → vote vào pool (no gate).
4. Track rời zone sau khi đã có vote → pool giữ nguyên, `get_voted_ship_id` trả kết quả cũ.

## Files thay đổi

| File | Loại thay đổi |
|---|---|
| `server/app/services/ai/per_camera_pipeline.py` | Thêm `_is_in_recognition_zone`, gate trong 2 callback |
| `server/app/tests/test_zone_gated_vote.py` | Thêm mới — 4 test cases |
