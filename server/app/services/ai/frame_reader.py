"""Đọc RTSP / webcam, đẩy frame vào queue."""
import os
import queue
import threading
import time

import cv2


def open_rtsp(rtsp_url: str) -> cv2.VideoCapture:
    # Allow override via env; default to TCP + reasonable timeouts/buffers for stability.
    # NOTE: These options help transport stability but cannot fully fix a corrupt HEVC stream.
    if not os.environ.get("OPENCV_FFMPEG_CAPTURE_OPTIONS"):
        options = (
            "rtsp_flags;prefer_tcp"
            "|rtsp_transport;tcp"
            "|stimeout;20000000"
            "|buffer_size;10240000"
            "|max_delay;500000"
            "|analyzeduration;10000000"
            "|probesize;10000000"
        )
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = options
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    return cap


class FrameReaderThread(threading.Thread):
    """Đọc RTSP/webcam, đẩy frame.copy() vào queue (tránh race buffer OpenCV)."""

    def __init__(
        self,
        rtsp_url,
        frame_queue: "queue.Queue",
        stop_event: threading.Event,
        queue_maxsize: int = 2,
        target_fps: float | None = None,
    ):
        super().__init__(daemon=True)
        self.rtsp_url = rtsp_url
        self._frame_queue = frame_queue
        self._stop_event = stop_event
        self._cap = None
        self._target_interval = None
        if target_fps is not None:
            try:
                fps = float(target_fps)
                if fps > 0:
                    self._target_interval = 1.0 / fps
            except Exception:
                self._target_interval = None

    def run(self):
        try:
            if isinstance(self.rtsp_url, str):
                self._cap = open_rtsp(self.rtsp_url)
            else:
                self._cap = cv2.VideoCapture(self.rtsp_url)

            if self._cap.isOpened():
                self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            else:
                print(f"Error: Could not open stream {self.rtsp_url}")
                return

            print("Stream opened successfully.")

            next_emit = time.monotonic()
            while not self._stop_event.is_set():
                if self._target_interval is not None:
                    now = time.monotonic()
                    if now < next_emit:
                        time.sleep(min(0.02, next_emit - now))
                        continue
                    # schedule next slot before read to stabilize pacing
                    next_emit = now + self._target_interval
                ok, frame = self._cap.read()
                if not ok or frame is None:
                    if isinstance(self.rtsp_url, str):
                        print("Stream lost, reconnecting...")
                        self._cap.release()
                        time.sleep(2)
                        self._cap = open_rtsp(self.rtsp_url)
                        if self._cap.isOpened():
                            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        continue
                    break

                try:
                    self._frame_queue.put_nowait(frame.copy())
                except queue.Full:
                    try:
                        self._frame_queue.get_nowait()
                    except queue.Empty:
                        pass
                    try:
                        self._frame_queue.put_nowait(frame.copy())
                    except queue.Full:
                        pass
        except Exception as e:
            print(f"[WARNING] FrameReaderThread crashed: {e}")
        finally:
            if self._cap is not None:
                self._cap.release()
            self._stop_event.set()
