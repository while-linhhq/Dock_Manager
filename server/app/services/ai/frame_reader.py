"""Đọc RTSP / webcam, đẩy frame vào queue."""
import os
import queue
import threading
import time

import cv2


def open_rtsp(rtsp_url: str) -> cv2.VideoCapture:
    options = "rtsp_transport;tcp|stimeout;20000000|buffer_size;10240000"
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
    ):
        super().__init__(daemon=True)
        self.rtsp_url = rtsp_url
        self._frame_queue = frame_queue
        self._stop_event = stop_event
        self._cap = None

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
