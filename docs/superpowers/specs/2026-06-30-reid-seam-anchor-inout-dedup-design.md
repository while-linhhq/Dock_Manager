# Re-ID + Seam Anchor + IN/OUT Dedup Design

## Context

Camera trong group bố trí kề nhau, FOV **chồng lấn** (overlap), thứ tự lưu trong `camera_group` (`camera_order`). Một tàu thường xuất hiện **đồng thời** trên 2 camera kề trước, sau đó mới mất ở camera này và còn ở camera kia.

Hai lỗi thực tế:

1. **Double IN/OUT**: tàu neo ở camera1 đã tính IN; khi ra ngang camera2 lại tính thêm IN/OUT. Nguyên nhân: `boundary_crossing_events` ghi DB ngay lúc crossing (`cross_camera_reid.py:337`), nếu 2 camera chưa merge kịp thành 1 `GlobalIdentity` thì ghi 2 row; merge sau không xoá row cũ.

2. **Re-ID fail cho tàu transit không OCR**: tàu hiện ở camera2, OCR chưa đọc được biển, embedding yếu (đổi góc/sáng). Ba cơ chế hiện có (OCR match, seam anchor resurrect, embedding cosine ≥ 0.6) đều fail → tạo `GlobalIdentity` mới → double count.

Nghiệp vụ chốt: **1 G_ID = 1 IN + 1 OUT**. Tàu cắt zone là chắc chắn sẽ neo (zone vẽ có chủ đích). Re-dock sau khi rời cảng = lượt mới. Restart khi đang neo phải khôi phục để không đếm lại.

## Mục tiêu

- Mỗi `GlobalIdentity` ghi tối đa 1 IN + 1 OUT.
- Merge sớm khi tàu cùng thấy trên 2 camera kề (overlap), không cần OCR.
- Gom + làm rõ tham số re-id / seam anchor, đưa hết vào `port_configs` + UI.
- Restart không làm đếm lại IN cho tàu đang neo.

## Non-goals

- Split identity sau khi merge sai (để phase sau).
- Persist identity dài hạn theo ship_id cho re-dock (nghiệp vụ: re-dock = lượt mới).
- Baseline adaptive theo ngày/đêm (phase sau).

---

## Phần 1 — IN/OUT dedup (deferred write)

Bỏ ghi DB lúc crossing. Chỉ cập nhật state trên `GlobalIdentity`. Ghi 1 lần lúc finalize.

**`cross_camera_reid.py:report_boundary_crossing()`**
- Giữ logic set `identity.berth_in_ts` (min) / `berth_out_ts` (max).
- **Bỏ** gọi `record_boundary_crossing_event()`.
- Bỏ biến `should_record`.

**`cross_camera_reid.py:_finalize_identity_locked()`** (điểm hợp nhất duy nhất)
- Nếu `berth_in_ts` không None: ghi 1 event IN (`global_id`, ship_id, ts).
- Nếu `berth_out_ts` không None: ghi 1 event OUT.
- Sanity: nếu `berth_out_ts < berth_in_ts` → log cảnh báo, vẫn ghi theo ts thực.
- Guard cờ mới `GlobalIdentity.events_written: bool` để không double-insert khi finalize chạy 2 lần (anchor release + flush expired).

**Last-chance merge trước finalize (C1)**
- Trước khi `_finalize_identity_locked` ghi event, chạy 1 lượt quét identity khác chưa finalize có cùng ship_id hoặc đặc trưng khớp gate cứng → merge nếu khớp. Tránh finalize identity lẽ ra phải merge.

Hệ quả: event xuất hiện khi tàu rời (trễ tới `reid_handoff_window_sec`). Chấp nhận — nghiệp vụ đếm lượt, không cần realtime.

---

## Phần 2 — Concurrent overlap merge

Camera overlap FOV. Merge khi tàu **đồng thời** thấy trên 2 camera kề.

**Chặn hiện tại cần đổi**: `_has_concurrent_active_on_other_camera()` đang **chặn** embedding match khi 2 cam cùng active. Với overlap FOV, concurrent active trên cam kề + edge zone chính là **tín hiệu merge**. Bỏ chặn cho cặp adjacent + edge-zone; giữ chặn cho cam không kề.

**Component mới `server/app/services/ai/handoff_matcher.py`**

```
class OverlapMergeMatcher:
    candidate_identities(camera_b, track, now) -> list[GlobalIdentity]
        # gate cứng:
        #   - identity có active track trên camera A kề (camera_order |idx diff|==1)
        #   - track mới ở edge zone phía giáp A (reid_edge_zone_ratio)
        #   - camera A có đúng 1 track liên quan, camera B đúng 1 track (1 boat)
        #   - motion_state tương thích (cùng STATIC, hoặc cùng moving) — gate A2
    score(identity, track) -> float
        # fusion mềm có trọng số chuẩn hoá:
        #   reid_embedding_weight * cosine(best-of-20 emb, track.emb)
        #   reid_color_weight     * hsv_similarity(identity dominant hsv, track hsv)
        #   reid_size_weight      * box_size_ratio(identity last box, track box)
    best_match(camera_b, track, now) -> global_id | None
        # accept khi: 1 candidate vượt gate, score >= reid_accept_threshold,
        #             và (score - score#2) >= reid_min_margin
```

Gọi từ `CrossCameraReIdManager._match_existing_identity()` chèn vào **giữa** bước embedding cosine mạnh và bước tạo identity mới:

```
1. OCR exact match            (giữ)
2. Seam anchor resurrect      (giữ)
3. Embedding cosine >= reid_visual_threshold   (giữ, strong)
4. [MỚI] OverlapMergeMatcher.best_match()      (signal yếu, fusion)
5. tạo GlobalIdentity mới     (chỉ khi 4 fail)
```

**Lưu HSV vào `GlobalIdentity`**: thêm rolling list `dominant_hsv_history` (cap 20, như `embeddings`). Set trong `_attach_track`/`report_track_update` từ `track.dominant_color_hsv` (đã có từ `_enrich_track`). Dùng `extract_dominant_hsv()`/`hsv_matches()` từ `seam_anchor_color.py`.

---

## Phần 3 — Tối ưu cấu hình tham số

Param mới (seed `schema_patches.py` + init_db + UI `PortConfigsSection.tsx` category `reid`/`seam`):

| Key | Default | Vai trò |
|---|---|---|
| `reid_overlap_merge_enabled` | `true` | Bật concurrent overlap merge (Phần 2) |
| `reid_edge_zone_ratio` | `0.15` | Bề rộng vùng overlap (fraction width) xét merge. Tách khỏi `edge_zone_ratio` (đang dùng cho primary-camera) |
| `reid_embedding_weight` | `0.6` | Trọng số embedding trong fusion |
| `reid_color_weight` | `0.25` | Trọng số HSV similarity |
| `reid_size_weight` | `0.15` | Trọng số box size ratio |
| `reid_accept_threshold` | `0.6` | Ngưỡng tổng score mềm để accept merge |
| `reid_min_margin` | `0.12` | Chênh score so với candidate #2 (chống nhầm A1) |

Tái dùng (không thêm): `reid_visual_threshold`, `reid_handoff_window_sec`, `edge_zone_ratio` (giữ cho primary-camera).

Ranh giới rõ giữa hai cơ chế:
- **Overlap merge** (Phần 2): tàu còn thấy ≥ 1 camera.
- **Seam anchor**: tàu STATIC mất hẳn cả 2 camera. Giữ nguyên param seam anchor.

Resolver đọc config qua `pipeline_service._load_runtime_config()` → `_tracker_kwargs` / reid manager init, theo pattern `visual_match_threshold` đã có.

---

## Phần 4 — Edge cases đưa vào P1

**A2 — Motion gate chống nhầm transit/neo**: fusion chỉ merge khi `motion_state` tương thích. Dùng `MotionClassifier` output (hiện chỉ seam anchor dùng, mở rộng cho cross-camera).

**C1 — Last-chance merge trước finalize**: đã mô tả Phần 1.

**E5 — Color gate cho seam resurrect**: `try_resurrect()` thêm HSV gate cạnh embedding gate 0.65; nếu incoming có OCR ship_id khác anchor → từ chối resurrect.

**F2 — Persist berth state qua restart**: lưu berth state tối thiểu vào DB khi set IN, khôi phục lúc restart để tàu đang neo không bị đếm IN lại. Theo đúng pattern `AnchoredIdentityRepository`/`anchored_identities` (table riêng + repo riêng).

Bảng mới `active_berth_states` + `ActiveBerthStateRepository`:

| Cột | Kiểu | Vai trò |
|---|---|---|
| `global_id` | str (key) | Khoá theo `GlobalIdentity.global_id` |
| `group_id` | int \| null | Camera group |
| `ship_id` | str \| null | Biển số nếu đã đọc được |
| `berth_in_ts` | datetime | Thời điểm IN (để restore không đếm lại) |
| `camera_ids` | JSON | Danh sách camera đang giữ identity |
| `embedding` | bytes + `embedding_shape` | Best-of embedding để re-match sau restart |
| `dominant_hsv` | JSON | HSV để gate màu khi re-match |
| `updated_at` | datetime | Lần cập nhật cuối |

Repo methods (mirror `AnchoredIdentityRepository`): `upsert(identity)`, `delete(global_id)`, `list_active(group_id=None)`, `row_to_restore(row)`.

**Lifecycle**:
- Upsert khi `berth_in_ts` được set lần đầu (ship IN) trong `report_boundary_crossing()`. Cập nhật embedding/hsv/camera_ids khi identity đổi (tuỳ chọn throttle như seam baseline `last_db_flush_at`).
- Delete trong `_finalize_identity_locked()` sau khi đã ghi event OUT (`events_written=True`).

**Restart restore**:
- Lúc pipeline start, `list_active()` nạp các row thành "pending-restore" trong reid manager (cấu trúc nhẹ: `global_id`, `ship_id`, `berth_in_ts`, embedding, hsv, camera_ids).
- Khi track mới được match: OCR ship_id exact, hoặc embedding/HSV qua đúng gate fusion (`OverlapMergeMatcher` reuse) → rebind về `global_id` + `berth_in_ts` đã khôi phục thay vì tạo identity mới. Không ghi IN lại.
- Row hỏng/thiếu trường → fallback coi như tàu mới (đếm IN) + log cảnh báo.

Schema: thêm bảng vào `init_db.py` + `schema_patches.py` (tạo bảng nếu chưa có, theo pattern `anchored_identities`).

## Phần 5 — Edge cases ghi nhận, để P2

- **A1** xử lý cơ bản bằng `reid_min_margin`; split khi mâu thuẫn mạnh để P2.
- **D2** split identity: chưa có, P2.
- **E1/E2/E3** seam anchor occlusion/baseline lỗi thời: revalidation hiện tại đỡ phần lớn; baseline adaptive P2.
- **E4** nhiều tàu cùng seam: anchor theo box+embedding thay vì chỉ vùng — P2.
- **C3** hysteresis zone: gắn phase vào G_ID — cân nhắc P2.

---

## Error handling

- Unknown/invalid ship_id lọc trước khi vào pool/merge (giữ nguyên).
- `events_written` guard chống double-insert.
- `berth_out_ts >= berth_in_ts` sanity check lúc finalize.
- Merge fusion bọc try/except, fail thì fallback tạo identity mới (không crash pipeline).
- Restore restart: nếu DB state hỏng/thiếu, fallback coi như tàu mới (đếm IN) + log.

## Testing

Resolver/matcher test độc lập (synthetic identity/track, không cần camera thật):

1. **Phần 1**: 2 G_ID từ 2 cam → merge → finalize → đúng 1 IN + 1 OUT.
2. **Phần 1**: tàu chỉ IN chưa OUT → finalize ghi IN, không OUT.
3. **Phần 1**: double finalize (anchor release + flush) → `events_written` chặn → không double row.
4. **Phần 1**: `berth_out_ts < berth_in_ts` → log + ghi theo ts thực.
5. **Phần 2**: concurrent overlap no-OCR, embedding yếu + color bù → merge.
6. **Phần 2**: 2 tàu khác nhau gần seam, score sát → `reid_min_margin` chặn → không merge.
7. **Phần 2**: cam không kề → không merge.
8. **A2**: transit box overlap tàu neo, motion khác → không merge.
9. **E5**: resurrect IoU cao nhưng OCR ship_id khác → từ chối.
10. **F2**: persist berth_in → restart restore → detect lại (match OCR/embedding) rebind về global_id cũ, không tạo IN mới.
10b. **F2**: row `active_berth_states` hỏng/thiếu trường → fallback tàu mới + log, không crash.
10c. **F2**: finalize ghi OUT → delete row `active_berth_states`.
11. **Phần 3**: resolver/matcher đọc đúng config từ runtime_cfg.

Run:
```bash
pytest server/app/tests/test_overlap_merge.py server/app/tests/test_inout_dedup.py -q
```

## Deliberate simplifications

- Re-dock = lượt mới → không persist identity dài hạn theo ship_id.
- Bỏ dwell-time gate (F1) — zone vẽ ở chỗ chắc chắn neo.
- Split identity (D2) để P2 — phức tạp, cần bằng chứng mâu thuẫn mạnh.
- Persist restart (F2) chỉ lưu berth state tối thiểu, không snapshot toàn identity.
