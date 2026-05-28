"""Ghi video từ frame đã annotate (YOLO), luồng riêng."""
from __future__ import annotations
import os
import queue
import threading
import time
from dataclasses import dataclass
from typing import Callable

VideoSavedCallback = Callable[[str, frozenset[str], float, float], None]

import cv2

from app.services.ai.boat_tracker import TrackState, TrackedBoat

from app.core.config import settings
from app.utils.ai.detect_paths import RUNS_DETECT, ensure_dir, timestamp_prefix, videos_dir_for_today
from app.utils.media.faststart_mp4 import faststart_inplace, has_moov_atom
from app.utils.media.mp4_codec import get_mp4_video_codec_fourcc
from app.utils.media.transcode_h264 import transcode_to_h264_faststart


def _recording_track_ids(tracked_boats: list) -> frozenset[str]:
    """Tracks still on screen (CONFIRMED or LOST) — keep recording through brief misses."""
    return frozenset(
        str(t.track_id)
        for t in tracked_boats
        if getattr(t, 'state', None) in (TrackState.CONFIRMED, TrackState.LOST)
    )


def _confirmed_track_ids(tracked_boats: list) -> frozenset[str]:
    return frozenset(
        str(t.track_id)
        for t in tracked_boats
        if getattr(t, 'state', None) == TrackState.CONFIRMED
    )


@dataclass(frozen=True)
class _FinalizeJob:
    path: str
    track_ids: frozenset[str]
    started_at: float
    ended_at: float


@dataclass
class _TrackRecordSession:
    track_id: str
    writer: cv2.VideoWriter
    path: str
    start_mono: float
    last_seen_mono: float
    start_wall: float
    last_video_frame_mono: float | None = None

    def write_frame_paced(self, frame, now: float, record_fps: float) -> None:
        last = self.last_video_frame_mono
        if last is None:
            n_write = 1
        else:
            elapsed = max(0.0, now - last)
            n_write = max(1, int(round(elapsed * record_fps)))
        for _ in range(n_write):
            self.writer.write(frame)
        self.last_video_frame_mono = now
        self.last_seen_mono = now


class VideoRecorderThread(threading.Thread):
    """
    Nhận (annotated_frame, tracked_boats); ghi MP4 **riêng từng track_id**.
    Một tàu mới xuất hiện không cắt clip của tàu đang ghi.
    Ngắt mỗi track: gap không thấy track đó, hoặc max duration.
    """

    def __init__(
        self,
        video_queue: 'queue.Queue',
        stop_event: threading.Event,
        max_duration_sec: float,
        gap_sec: float,
        record_fps: float,
        runs_base: str = RUNS_DETECT,
        on_video_saved: VideoSavedCallback | None = None,
        exclusive_single_track: bool = False,
    ):
        super().__init__(daemon=True)
        self._video_queue = video_queue
        self._stop_event = stop_event
        self._max_duration_sec = max(0.0, float(max_duration_sec))
        self._gap_sec = float(gap_sec)
        self._record_fps = max(1.0, float(record_fps))
        self._runs_base = runs_base
        self._on_video_saved = on_video_saved
        # Kept for API compat; per-track sessions are always used now.
        self._exclusive_single_track = bool(exclusive_single_track)

        self._sessions: dict[str, _TrackRecordSession] = {}
        self._frame_size: tuple[int, int] | None = None

        self._finalize_queue: queue.Queue[_FinalizeJob | None] = queue.Queue(maxsize=10)
        self._finalize_worker = threading.Thread(
            target=self._finalize_loop,
            daemon=True,
            name='VideoRecorderFinalize',
        )
        self._finalize_worker.start()

    def _finalize_loop(self) -> None:
        while True:
            job = self._finalize_queue.get()
            if job is None:
                self._finalize_queue.task_done()
                break
            try:
                self._finalize_recording(job)
            except Exception as exc:
                print(f'[RECORD] finalize failed: {exc}')
            finally:
                self._finalize_queue.task_done()

    def _finalize_recording(self, job: _FinalizeJob) -> None:
        path = job.path
        try:
            if bool(getattr(settings, 'VIDEO_TRANSCODE_ENABLE', True)):
                codec = (get_mp4_video_codec_fourcc(path) or '').strip().lower()
                if (not has_moov_atom(path)) or (codec and codec != 'avc1'):
                    tmp = f'{path}.h264.tmp.mp4'
                    transcode_to_h264_faststart(
                        path,
                        tmp,
                        preset=str(
                            getattr(settings, 'VIDEO_TRANSCODE_PRESET', 'veryfast') or 'veryfast'
                        ),
                        crf=int(getattr(settings, 'VIDEO_TRANSCODE_CRF', 23) or 23),
                    )
                    os.replace(tmp, path)
            faststart_inplace(path)
        except Exception as e:
            print(f'[RECORD] faststart failed: {e}')
        if self._on_video_saved is not None:
            try:
                self._on_video_saved(
                    path,
                    job.track_ids,
                    job.started_at,
                    job.ended_at,
                )
            except Exception as e:
                print(f'[RECORD] MinIO upload callback failed: {e}')
        print(f'[RECORD] Saved: {path}')

    def _enqueue_finalize(self, path: str, track_ids: frozenset[str], started_wall: float) -> None:
        job = _FinalizeJob(
            path=path,
            track_ids=track_ids,
            started_at=float(started_wall),
            ended_at=time.time(),
        )
        try:
            self._finalize_queue.put_nowait(job)
        except queue.Full:
            try:
                self._finalize_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._finalize_queue.put_nowait(job)
            except queue.Full:
                print(f'[RECORD] finalize queue full, dropping: {path}')

    def _open_session(self, track_id: str, frame) -> _TrackRecordSession | None:
        h, w = frame.shape[:2]
        self._frame_size = (w, h)
        out_dir = ensure_dir(videos_dir_for_today(self._runs_base))
        safe_tid = ''.join(c if c.isalnum() or c in '-_' else '_' for c in track_id)[:48]
        name = f'{timestamp_prefix()}_{safe_tid}.mp4'
        path = os.path.join(out_dir, name)
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(path, fourcc, self._record_fps, (w, h))
        if not writer.isOpened():
            print(f'[RECORD] Error: could not open VideoWriter for {path}')
            return None
        now = time.monotonic()
        session = _TrackRecordSession(
            track_id=track_id,
            writer=writer,
            path=path,
            start_mono=now,
            last_seen_mono=now,
            start_wall=time.time(),
        )
        session.write_frame_paced(frame, now, self._record_fps)
        print(f'[RECORD] Started track={track_id}: {path}')
        return session

    def _finalize_session(self, session: _TrackRecordSession) -> None:
        session.writer.release()
        self._enqueue_finalize(
            session.path,
            frozenset({session.track_id}),
            session.start_wall,
        )

    def _stop_all_sessions(self) -> None:
        for session in list(self._sessions.values()):
            self._finalize_session(session)
        self._sessions.clear()

    def _session_over_max_duration(self, session: _TrackRecordSession, now: float) -> bool:
        return (
            self._max_duration_sec > 0
            and (now - session.start_mono) >= self._max_duration_sec
        )

    def _session_gap_expired(self, session: _TrackRecordSession, now: float) -> bool:
        return self._gap_sec > 0 and (now - session.last_seen_mono) >= self._gap_sec

    def _process_frame(self, frame, tracked_boats: list[TrackedBoat]) -> None:
        now = time.monotonic()
        present = _recording_track_ids(tracked_boats)
        confirmed = _confirmed_track_ids(tracked_boats)

        for tid in confirmed:
            if tid not in self._sessions:
                session = self._open_session(tid, frame)
                if session is not None:
                    self._sessions[tid] = session

        for tid in list(present):
            session = self._sessions.get(tid)
            if session is None:
                continue
            session.write_frame_paced(frame, now, self._record_fps)
            if self._session_over_max_duration(session, now):
                self._finalize_session(session)
                del self._sessions[tid]

        for tid, session in list(self._sessions.items()):
            if tid in present:
                continue
            if self._session_gap_expired(session, now):
                self._finalize_session(session)
                del self._sessions[tid]

    def shutdown_finalize(self, timeout: float = 120.0) -> None:
        deadline = time.monotonic() + max(1.0, float(timeout))
        while time.monotonic() < deadline:
            if self._finalize_queue.unfinished_tasks <= 0:
                break
            time.sleep(0.1)
        try:
            self._finalize_queue.put_nowait(None)
        except queue.Full:
            pass
        self._finalize_worker.join(timeout=10.0)

    def run(self) -> None:
        try:
            while not self._stop_event.is_set():
                try:
                    item = self._video_queue.get(timeout=0.5)
                except queue.Empty:
                    now = time.monotonic()
                    for tid, session in list(self._sessions.items()):
                        if self._session_gap_expired(session, now):
                            self._finalize_session(session)
                            del self._sessions[tid]
                    continue

                if not item or len(item) < 2:
                    continue
                frame, tracked_boats = item[0], item[1]
                if frame is None or frame.size == 0:
                    continue

                self._process_frame(frame, tracked_boats)
        except Exception as e:
            print(f'[WARNING] VideoRecorderThread crashed: {e}')
        finally:
            self._stop_all_sessions()
