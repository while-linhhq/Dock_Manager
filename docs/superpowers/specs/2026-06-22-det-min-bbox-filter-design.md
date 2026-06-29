# Per-camera min bbox filter — design spec

**Date:** 2026-06-22  
**Status:** Approved — pending implementation

## Goal

Filter YOLO detections smaller than configurable min width/height (pixels on native frame) before `BoatTracker.update`, reducing noise tracks/OCR/visual load.

## Decisions

| Topic | Choice |
|-------|--------|
| Unit | Absolute pixels on native frame (post-CLAHE, same resolution as raw) |
| Logic | `width >= min_width` AND `height >= min_height` |
| Storage | `cameras.detection_settings` JSONB (separate from `boundary_lines`) |
| Defaults | `min_bbox_width=50`, `min_bbox_height=30` when null/missing |
| Scope | Hybrid `PerCameraPipeline` only — not AI Lab, not global port_configs |
| Hot-reload | Yes — on `PUT /cameras/{id}/detection-settings` |

## Data model

### Column

`cameras.detection_settings` JSONB nullable — added via `schema_patches._ensure_cameras_detection_settings()`.

### JSON shape

```json
{
  "min_bbox_width": 50,
  "min_bbox_height": 30
}
```

### Pydantic

`CameraDetectionSettings` in `app/schemas/camera.py` — validators clamp `max(1, int(value))`.

`CameraRead.detection_settings: Optional[CameraDetectionSettings]`.

## API

`PUT /api/v1/cameras/{camera_id}/detection-settings`

- Body: `CameraDetectionSettings`
- Persists via `camera_repo.set_detection_settings`
- Calls `apply_detection_settings_update` → `pipeline_service.update_camera_detection_settings`

Does not modify `PUT /boundary-lines`.

## Backend helpers

`app/services/ai/detection_filter.py`:

- `parse_min_bbox_from_detection_settings(payload) -> (int, int)`
- `filter_boxes_by_min_size(boxes, confs, min_w, min_h)`
- `apply_detection_settings_update(camera_id, payload)`

## Pipeline

`PerCameraPipelineConfig.detection_settings: dict | None`

On init: parse → `_det_min_bbox_width`, `_det_min_bbox_height`

After `predict_boxes` in `_process_frame`: apply filter

`update_detection_settings(payload)` for hot-reload

`pipeline_service._start_group_hybrid`: pass `member.camera.detection_settings`

`pipeline_service.update_camera_detection_settings(camera_id, payload)`

## Frontend

`CameraDetectionSettings` type + `CameraRead.detection_settings`

`portApi.setDetectionSettings(cameraId, body)`

`BoundaryLineEditor`: number inputs for min W/H + "Lưu ngưỡng bbox" button — independent of boundary geometry save

## Tests

`server/app/tests/test_detection_bbox_filter.py` — parse defaults/clamp + filter AND/`>=` logic

## Out of scope

- Fused `YoloWorkerThread` path
- AI Lab
- `port_configs` global keys
