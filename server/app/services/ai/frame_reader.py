"""Đọc RTSP / webcam, đẩy frame vào queue."""

import queue
import threading
import time

from app.utils.ai.ffmpeg_log import suppress_ffmpeg_decoder_logs

suppress_ffmpeg_decoder_logs()

import cv2

try:
    cv2.setLogLevel(2)
except Exception:
    pass


def open_rtsp(rtsp_url: str) -> cv2.VideoCapture:
    return cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)


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

                now = time.monotonic()
                if self._target_interval is not None and now < next_emit:
                    continue
                if self._target_interval is not None:
                    next_emit = now + self._target_interval

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
