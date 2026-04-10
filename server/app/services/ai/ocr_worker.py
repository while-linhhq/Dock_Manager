"""Paddle OCR worker: ship ID từ crop, cập nhật cache, lưu cap/crops khi CONFIRMED.

- OCR có mã: ``{prefix}_{track}_frame.jpg`` / ``*_boat.jpg`` (throttle ``confirmed_save_interval``).
- OCR không có kết quả: ``*_noocr_*`` (throttle ``ocr_miss_save_interval``) để rà soát thủ công;
  không dùng chung timestamp với lần lưu khi đọc được — tránh bỏ lỡ ảnh khi vừa lưu bản thành công.
"""
from __future__ import annotations

import json
import os
import queue
import threading
import time
from datetime import datetime

import cv2

from app.services.ai.boat_tracker import BoatTracker, TrackState, TrackedBoat
from app.utils.ai.detect_paths import (
    RUNS_DETECT,
    cap_dir_for_today,
    crops_dir_for_today,
    ensure_dir,
    ocr_audit_frames_dir_for_today,
    ocr_audit_logs_dir_for_today,
    timestamp_prefix,
)
from app.utils.ai.pipeline_utils import clamp_box, ocr_cache_key_track
from app.utils.ai.ship_id_recognizer import ShipIdRecognizer


def _fmt_local_dt(ts: float) -> str:
    """Giờ địa phương, ms 3 chữ số — phù hợp đọc và xuất Excel."""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _load_audit_counters_from_today_file(runs_base: str) -> tuple[int, int]:
    """
    Đọc file JSONL của ngày hiện tại (nếu có) để tiếp tục seq / ships_completed_today
    sau khi restart pipeline trong cùng ngày.
    """
    log_path = os.path.join(ocr_audit_logs_dir_for_today(runs_base), "ocr_events.jsonl")
    if not os.path.isfile(log_path):
        return (0, 0)
    max_seq = 0
    max_ships = 0
    try:
        with open(log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                s = obj.get("seq")
                if isinstance(s, int) and s > max_seq:
                    max_seq = s
                sc = obj.get("ships_completed_today")
                if isinstance(sc, int) and sc > max_ships:
                    max_ships = sc
    except OSError:
        return (0, 0)
    return (max_seq, max_ships)


def _build_track_removed_logger(
    runs_base: str,
    enable: bool,
    log_dedup_window_sec: float = 0.0,
):
    """
    Factory trả callback cho BoatTracker.on_track_removed; ghi 1 dòng JSONL khi track kết thúc.
    - confidence: độ tin cậy detection YOLO (bbox) tại frame match cuối của track.
    - log_dedup_window_sec > 0: cùng voted_ship_id trong cửa sổ thời gian → likely_duplicate,
      không tăng ships_completed_today (defense-in-depth nếu tracker re-id miss).
    seq / ships_completed_today: tiếp tục từ file cùng ngày khi khởi động lại pipeline.
    schema_version: tăng khi đổi schema (xuất Excel).
    """
    if not enable:
        return None

    today = datetime.now().strftime("%Y-%m-%d")
    persisted_seq, persisted_ships = _load_audit_counters_from_today_file(runs_base)
    seq_next = [persisted_seq]
    daily_state = {"day": today, "count": persisted_ships}
    log_recent: dict[str, tuple[str, float]] = {}

    def _on_removed(tb: TrackedBoat, ocr_history: list[tuple[str, float]]) -> None:
        seq_next[0] += 1
        today = datetime.now().strftime("%Y-%m-%d")
        if daily_state["day"] != today:
            daily_state["day"] = today
            daily_state["count"] = 0
            log_recent.clear()

        vote_summary: dict[str, dict] = {}
        for sid, conf in ocr_history:
            if sid not in vote_summary:
                vote_summary[sid] = {"count": 0, "total_conf": 0.0}
            vote_summary[sid]["count"] += 1
            vote_summary[sid]["total_conf"] = round(
                vote_summary[sid]["total_conf"] + conf, 4
            )

        voted_id = None
        if vote_summary:
            voted_id = max(vote_summary, key=lambda k: vote_summary[k]["total_conf"])

        now = time.time()
        likely_duplicate = False
        continuation_of: str | None = None

        if voted_id is not None and log_dedup_window_sec > 0:
            prev = log_recent.get(voted_id)
            if prev is not None and (now - prev[1]) < log_dedup_window_sec:
                likely_duplicate = True
                continuation_of = prev[0]
            else:
                log_recent[voted_id] = (str(tb.track_id), now)

        if not likely_duplicate:
            daily_state["count"] += 1

        record = {
            "schema_version": 4,
            "seq": seq_next[0],
            "ships_completed_today": daily_state["count"],
            "logged_at": _fmt_local_dt(now),
            "track_id": str(tb.track_id),
            "first_seen_at": _fmt_local_dt(tb.first_seen_ts),
            "last_seen_at": _fmt_local_dt(tb.last_seen_ts),
            "confidence": round(float(tb.conf), 4),
            "voted_ship_id": voted_id,
            "ocr_attempts": len(ocr_history),
            "vote_summary": vote_summary,
            "likely_duplicate": likely_duplicate,
            "continuation_of_track": continuation_of,
        }
        logs_dir = ensure_dir(ocr_audit_logs_dir_for_today(runs_base))
        log_path = os.path.join(logs_dir, "ocr_events.jsonl")
        with open(log_path, "a", encoding="utf-8") as lf:
            lf.write(json.dumps(record, ensure_ascii=False) + "\n")

    return _on_removed


class OcrWorkerThread(threading.Thread):
    def __init__(
        self,
        recognizer: ShipIdRecognizer,
        ocr_queue: "queue.Queue",
        ocr_cache: dict,
        ocr_lock: threading.RLock,
        stop_event: threading.Event,
        ocr_label_ttl: float,
        confirmed_save_interval: float,
        boat_tracker: BoatTracker | None = None,
        runs_base: str = RUNS_DETECT,
        save_ocr_audit_frames: bool = True,
        ocr_miss_save_interval: float | None = None,
    ):
        super().__init__(daemon=True)
        self.recognizer = recognizer
        self._ocr_queue = ocr_queue
        self._ocr_cache = ocr_cache
        self._ocr_lock = ocr_lock
        self._stop_event = stop_event
        self.ocr_label_ttl = ocr_label_ttl
        # Khoảng cách tối thiểu (giây) giữa hai lần lưu cap/crops khi OCR **có** mã (CONFIRMED).
        # 0 = lưu mỗi OCR tick không hạn chế.
        self.confirmed_save_interval = confirmed_save_interval
        # Khi OCR **không** đọc được: throttle riêng (None → cùng confirmed_save_interval).
        self.ocr_miss_save_interval = (
            float(ocr_miss_save_interval)
            if ocr_miss_save_interval is not None
            else confirmed_save_interval
        )
        self._boat_tracker = boat_tracker
        self._runs_base = runs_base
        self.save_ocr_audit_frames = save_ocr_audit_frames
        self._last_cap_save_ts: dict[str, float] = {}
        self._last_noocr_cap_save_ts: dict[str, float] = {}

    def run(self):
        try:
            while not self._stop_event.is_set():
                try:
                    item = self._ocr_queue.get(timeout=1.0)
                except queue.Empty:
                    continue

                frame, boxes_list = item
                h, w = frame.shape[:2]
                now = time.time()

                # --- Audit frame: lưu mỗi lần OCR chạy, không phụ thuộc kết quả ---
                if self.save_ocr_audit_frames:
                    audit_prefix = timestamp_prefix()
                    audit_dir = ensure_dir(ocr_audit_frames_dir_for_today(self._runs_base))
                    cv2.imwrite(
                        os.path.join(audit_dir, f"{audit_prefix}_ocr.jpg"),
                        frame,
                    )

                updates = []

                for idx, pair in enumerate(boxes_list):
                    if isinstance(pair, tuple) and len(pair) == 2:
                        track_id, b = pair[0], pair[1]
                    else:
                        track_id = idx
                        b = pair

                    track_id_str = str(track_id)
                    x1, y1, x2, y2 = clamp_box(b, w, h)
                    crop = frame[y1:y2, x1:x2]
                    ck = ocr_cache_key_track(track_id)

                    state = (
                        self._boat_tracker.get_track_state(track_id_str)
                        if self._boat_tracker is not None
                        else TrackState.CONFIRMED
                    )

                    ocr_res = None
                    if crop.size > 0:
                        ocr_res = self.recognizer.recognize_bgr(crop)

                    if ocr_res:
                        best = ocr_res[0]
                        sid = best["id"]
                        conf = float(best["confidence"])

                        if self._boat_tracker is not None:
                            self._boat_tracker.add_ocr_vote(track_id_str, sid, conf)
                            voted = self._boat_tracker.get_voted_ship_id(track_id_str)
                            label = f"{voted} (voted)" if voted else f"{sid} ({conf:.2f})"
                        else:
                            label = f"{sid} ({conf:.2f})"

                        updates.append((ck, {"text": label, "time": now}))

                        if state == TrackState.CONFIRMED:
                            last_ts = self._last_cap_save_ts.get(track_id_str, 0.0)
                            if self.confirmed_save_interval <= 0 or (
                                time.monotonic() - last_ts
                            ) >= self.confirmed_save_interval:
                                save_prefix = timestamp_prefix()
                                cap_dir = ensure_dir(cap_dir_for_today(self._runs_base))
                                crop_dir = ensure_dir(crops_dir_for_today(self._runs_base))
                                cv2.imwrite(
                                    os.path.join(
                                        cap_dir,
                                        f"{save_prefix}_{track_id_str}_frame.jpg",
                                    ),
                                    frame,
                                )
                                cv2.imwrite(
                                    os.path.join(
                                        crop_dir,
                                        f"{save_prefix}_{track_id_str}_boat.jpg",
                                    ),
                                    crop,
                                )
                                self._last_cap_save_ts[track_id_str] = time.monotonic()

                    elif crop.size > 0 and state == TrackState.CONFIRMED:
                        last_miss = self._last_noocr_cap_save_ts.get(track_id_str, 0.0)
                        if self.ocr_miss_save_interval <= 0 or (
                            time.monotonic() - last_miss
                        ) >= self.ocr_miss_save_interval:
                            save_prefix = timestamp_prefix()
                            cap_dir = ensure_dir(cap_dir_for_today(self._runs_base))
                            crop_dir = ensure_dir(crops_dir_for_today(self._runs_base))
                            cv2.imwrite(
                                os.path.join(
                                    cap_dir,
                                    f"{save_prefix}_{track_id_str}_noocr_frame.jpg",
                                ),
                                frame,
                            )
                            cv2.imwrite(
                                os.path.join(
                                    crop_dir,
                                    f"{save_prefix}_{track_id_str}_noocr_boat.jpg",
                                ),
                                crop,
                            )
                            self._last_noocr_cap_save_ts[track_id_str] = time.monotonic()

                with self._ocr_lock:
                    for ck, entry in updates:
                        self._ocr_cache[ck] = entry

        except Exception as e:
            print(f"[WARNING] OcrWorkerThread crashed: {e}")
        finally:
            self._stop_event.set()
