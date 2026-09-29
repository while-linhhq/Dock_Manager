import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from pydantic import BaseModel, model_validator
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import SessionLocal, get_db
from app.repositories.camera_group_repository import camera_group_repo
from app.repositories.camera_repository import camera_repo
from app.repositories.user_repository import user_repo
from app.services import pipeline_preview
from app.services.ai import seam_anchor_baseline
from app.services.ai.multi_frame_reader import capture_snapshot
from app.utils.ai.frame_quality import is_usable_bgr_frame
from app.services.pipeline_service import pipeline_service
from app.utils.ws_safe import SafeWebSocket, start_disconnect_watch, stop_disconnect_watch

router = APIRouter()


class PipelineStartRequest(BaseModel):
    camera_group_id: int
    enable_ocr: bool = True


class PipelineTestVideoRequest(BaseModel):
    source: str
    enable_ocr: bool = True
    save_to_db: bool = True


@router.post("/start")
async def start_pipeline(req: PipelineStartRequest, db: Session = Depends(get_db)):
    if pipeline_service.is_running:
        return {"message": "Pipeline is already running"}
    try:
        group = camera_group_repo.get(db, req.camera_group_id)
        if not group:
            raise HTTPException(status_code=404, detail='Camera group not found')
        if not group.is_active:
            raise HTTPException(status_code=400, detail='Camera group is inactive')
        await asyncio.to_thread(pipeline_service.start_group, group, req.enable_ocr)
        return {
            "message": "Pipeline started",
            "camera_group_id": req.camera_group_id,
            "camera_group_name": group.name,
        }
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(status_code=500, detail=str(err)) from err

@router.post("/stop")
async def stop_pipeline():
    if not pipeline_service.is_running:
        return {"message": "Pipeline is not running"}
    await asyncio.to_thread(pipeline_service.stop)
    return {"message": "Pipeline stopped"}

def _kill_orphan_ocr_workers() -> list[int]:
    """Kill lingering OCR child processes holding VRAM.

    The pipeline stop path closes the OCR subprocess cleanly, but a crashed or
    force-restarted process can leave orphans reparented to init that keep
    1.5-3GB of CUDA context each. Reap them explicitly on server shutdown so a
    subsequent start does not hit CUBLAS_ALLOC_FAILED.

    Lưu ý: worker là tiến trình con do ``multiprocessing`` spawn, nên /proc của nó
    chỉ hiện tên ``python`` với cmdline ``from multiprocessing.spawn import
    spawn_main``. Tên ``name='ocr-gpu-worker'`` chỉ tồn tại bên trong Python, không
    xuất hiện ở OS — vì vậy khớp theo chuỗi đó sẽ không bao giờ trúng. Nhận diện
    theo dấu hiệu thực: cmdline có ``multiprocessing`` + cùng cwd + cùng interpreter.
    """
    import os
    import sys

    import psutil

    cwd = os.path.realpath(os.getcwd())
    exe = os.path.realpath(sys.executable)
    me = psutil.Process()

    killed: list[int] = []
    for proc in psutil.process_iter(['pid', 'cmdline']):
        try:
            if proc.pid == me.pid:
                continue
            cmdline = ' '.join(proc.info.get('cmdline') or [])
            if 'multiprocessing' not in cmdline:
                continue
            if os.path.realpath(proc.cwd()) != cwd:
                continue
            if os.path.realpath(proc.exe()) != exe:
                continue
            proc.terminate()
            killed.append(proc.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    if killed:
        gone, alive = psutil.wait_procs(
            [psutil.Process(pid) for pid in killed if psutil.pid_exists(pid)],
            timeout=3.0,
        )
        for proc in alive:
            try:
                proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    return killed


@router.post("/shutdown-server")
async def shutdown_server(_=Depends(get_current_user)):
    """Ngắt toàn bộ server: dừng pipeline, kill orphan OCR, thoát tiến trình.

    Trả response trước rồi gửi SIGTERM cho chính tiến trình uvicorn để lifespan
    shutdown chạy đủ (đóng pipeline, sepay, DB) thay vì kill cứng.
    """
    import os
    import signal
    import threading

    if pipeline_service.is_running:
        try:
            await asyncio.to_thread(pipeline_service.stop)
        except Exception:
            pass

    killed = await asyncio.to_thread(_kill_orphan_ocr_workers)

    def _terminate_self() -> None:
        import time

        time.sleep(0.5)
        os.kill(os.getpid(), signal.SIGTERM)

    threading.Thread(target=_terminate_self, daemon=True).start()
    return {
        "message": "Server đang tắt",
        "orphan_ocr_killed": killed,
    }


def _resolve_log_path() -> str:
    """Absolute path to the active app log file (matches main._configure_logging)."""
    import os

    log_path = str(getattr(settings, 'LOG_FILE_PATH', 'logs/app.log') or 'logs/app.log')
    if not os.path.isabs(log_path):
        # server root = parent of the app package (…/server).
        # This file is app/api/v1/endpoints/pipeline.py → 5 dirname() to reach …/server.
        server_root = os.path.dirname(
            os.path.dirname(
                os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                )
            )
        )
        log_path = os.path.join(server_root, log_path)
    return log_path


def _tail_lines(path: str, max_lines: int) -> list[str]:
    """Read the last ``max_lines`` lines of a file without loading it whole."""
    import os

    if not os.path.exists(path):
        return []
    chunk_size = 64 * 1024
    with open(path, 'rb') as fh:
        fh.seek(0, os.SEEK_END)
        file_size = fh.tell()
        blocks: list[bytes] = []
        remaining = file_size
        newline_count = 0
        # +1 line so we can drop a partial leading line cleanly.
        while remaining > 0 and newline_count <= max_lines:
            read_size = min(chunk_size, remaining)
            remaining -= read_size
            fh.seek(remaining)
            block = fh.read(read_size)
            blocks.insert(0, block)
            newline_count += block.count(b'\n')
        data = b''.join(blocks)
    text = data.decode('utf-8', errors='replace')
    lines = text.splitlines()
    return lines[-max_lines:]


@router.get("/logs")
async def get_logs(lines: int = 200, _=Depends(get_current_user)):
    """Tail the backend log file for the in-app "Xem Logs" page.

    ``lines`` is clamped to [1, 5000] to bound response size.
    """
    max_lines = max(1, min(int(lines), 5000))
    path = _resolve_log_path()
    tail = await asyncio.to_thread(_tail_lines, path, max_lines)
    import os

    return {
        "path": path,
        "exists": os.path.exists(path),
        "lines": tail,
        "returned": len(tail),
        "requested": max_lines,
    }


def _authenticate_ws_token(token: str | None) -> int | None:
    """Validate a JWT query-param token for WS endpoints; return user_id or None."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None
    user_id = payload.get('sub')
    if user_id is None:
        return None
    db = SessionLocal()
    try:
        user = user_repo.get(db, int(user_id))
        if user is None or not user.is_active:
            return None
        return int(user_id)
    except (TypeError, ValueError):
        return None
    finally:
        db.close()


@router.websocket('/logs-stream')
async def logs_stream(websocket: WebSocket) -> None:
    """Realtime ``tail -f`` of the backend log file; query ?token=JWT&lines=N.

    Sends the last ``lines`` lines on connect, then streams each new line as it
    is appended. Handles log rotation (file truncated/replaced) by re-opening
    from the start when the inode/size shrinks.
    """
    token = websocket.query_params.get('token')
    if _authenticate_ws_token(token) is None:
        await websocket.close(code=1008)
        return

    try:
        initial_lines = int(websocket.query_params.get('lines', '200'))
    except (TypeError, ValueError):
        initial_lines = 200
    initial_lines = max(1, min(initial_lines, 5000))

    ws = SafeWebSocket(websocket)
    await ws.accept()
    disconnect, watch_task = start_disconnect_watch(websocket)

    import os

    path = _resolve_log_path()

    def _read_new(state: dict) -> tuple[list[str], dict]:
        """Blocking read of appended lines; returns (lines, updated_state)."""
        new_lines: list[str] = []
        try:
            if not os.path.exists(path):
                return [], state
            size = os.path.getsize(path)
            offset = state.get('offset', 0)
            # Rotation / truncation: file shrank -> restart from 0.
            if size < offset:
                offset = 0
            with open(path, 'rb') as fh:
                fh.seek(offset)
                chunk = fh.read()
                new_offset = fh.tell()
            state = {'offset': new_offset}
            if chunk:
                buffered = state_buffer.get('partial', b'') + chunk
                *complete, partial = buffered.split(b'\n')
                state_buffer['partial'] = partial
                for raw in complete:
                    new_lines.append(raw.decode('utf-8', errors='replace'))
        except OSError:
            return [], state
        return new_lines, state

    # Send initial tail, then set offset to current EOF.
    state_buffer: dict = {'partial': b''}
    try:
        initial = await asyncio.to_thread(_tail_lines, path, initial_lines)
        for line in initial:
            await ws.send_text(line)
        # Start streaming from current end of file.
        stream_state = {'offset': os.path.getsize(path) if os.path.exists(path) else 0}
        loop = asyncio.get_running_loop()
        last_activity = loop.time()
        while not disconnect.is_set():
            new_lines, stream_state = await asyncio.to_thread(_read_new, stream_state)
            if new_lines:
                for line in new_lines:
                    await ws.send_text(line)
                last_activity = loop.time()
            else:
                now = loop.time()
                if now - last_activity > 15.0:
                    await ws.send_text('\x00ka')  # keepalive sentinel, ignored by client
                    last_activity = now
                await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    except Exception:
        return
    finally:
        await stop_disconnect_watch(watch_task)


@router.get("/status")
async def get_status():
    gpu = pipeline_service.gpu_status
    if gpu is None:
        from app.utils.ai.gpu_probe import collect_gpu_runtime_status

        gpu = await asyncio.to_thread(collect_gpu_runtime_status)
    return {
        "is_running": pipeline_service.is_running,
        "ocr_cache_size": len(pipeline_service.ocr_cache),
        "active_group_id": pipeline_service.active_group_id,
        "seam_anchor_active": pipeline_service.seam_anchor_verifier is not None,
        "gpu": gpu,
        "detect_scale": pipeline_service.active_detect_scale,
        **pipeline_service.frame_stats_payload(),
    }


@router.websocket('/preview-stream')
async def pipeline_preview_stream(websocket: WebSocket) -> None:
    """Binary JPEG frames while pipeline is running; query ?token=JWT."""
    token = websocket.query_params.get('token')
    if not token:
        await websocket.close(code=1008)
        return
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get('sub')
        if user_id is None:
            await websocket.close(code=1008)
            return
    except JWTError:
        await websocket.close(code=1008)
        return

    db = SessionLocal()
    try:
        user = user_repo.get(db, int(user_id))
        if user is None or not user.is_active:
            await websocket.close(code=1008)
            return
    finally:
        db.close()

    ws = SafeWebSocket(websocket)
    await ws.accept()
    disconnect, watch_task = start_disconnect_watch(websocket)
    loop = asyncio.get_running_loop()
    try:
        last_sent = loop.time()
        last_sequence = 0
        while not disconnect.is_set():
            try:
                sequence, jpeg = await asyncio.wait_for(
                    asyncio.to_thread(
                        pipeline_preview.wait_for_jpeg,
                        last_sequence,
                        0.5,
                    ),
                    timeout=1.0,
                )
            except asyncio.TimeoutError:
                sequence, jpeg = last_sequence, None
            if jpeg and sequence > last_sequence:
                last_sequence = sequence
                await ws.send_bytes(jpeg)
                last_sent = loop.time()
            else:
                now = loop.time()
                if now - last_sent > 15.0:
                    await ws.send_text('ka')
                    last_sent = now
    except WebSocketDisconnect:
        pass
    except Exception:
        # Best-effort: avoid crashing the server loop on transient send errors
        return
    finally:
        await stop_disconnect_watch(watch_task)

@router.post("/test-video")
async def test_video(req: PipelineTestVideoRequest):
    """
    Test API: Process a video file and return detection results.
    """
    try:
        results = pipeline_service.test_video_sync(
            req.source,
            req.enable_ocr,
            req.save_to_db,
        )
        return {
            "success": True,
            "source": req.source,
            "saved_to_db": req.save_to_db,
            "detections_count": len(results),
            "results": results
        }
    except Exception as err:
        raise HTTPException(status_code=500, detail=str(err)) from err


class SeamAnchorLockRequest(BaseModel):
    group_id: Optional[int] = None
    camera_ids: Optional[list[int]] = None
    force_capture: bool = False

    @model_validator(mode='after')
    def validate_target(self) -> 'SeamAnchorLockRequest':
        if self.group_id is None and not self.camera_ids:
            raise ValueError('Either group_id or camera_ids is required')
        return self


def _resolve_target_cameras(
    db: Session,
    req: SeamAnchorLockRequest,
) -> tuple[list[int], int | None, dict[int, str]]:
    rtsp_by_camera: dict[int, str] = {}
    if req.group_id is not None:
        group = camera_group_repo.get(db, int(req.group_id))
        if not group:
            raise HTTPException(status_code=404, detail='Camera group not found')
        camera_ids = [
            int(member.camera_id)
            for member in group.members
            if bool(member.enabled) and getattr(member, 'camera', None) is not None
        ]
        for member in group.members:
            if member.camera is not None and member.camera.rtsp_url:
                rtsp_by_camera[int(member.camera_id)] = str(member.camera.rtsp_url)
        if req.camera_ids:
            filtered = [cid for cid in camera_ids if cid in set(int(x) for x in req.camera_ids)]
            camera_ids = filtered
        return camera_ids, int(req.group_id), rtsp_by_camera

    camera_ids = [int(x) for x in (req.camera_ids or [])]
    for camera_id in camera_ids:
        camera = camera_repo.get(db, int(camera_id))
        if camera is None:
            raise HTTPException(status_code=404, detail=f'Camera {camera_id} not found')
        if camera.rtsp_url:
            rtsp_by_camera[int(camera_id)] = str(camera.rtsp_url)
    return camera_ids, None, rtsp_by_camera


@router.post('/seam-anchor/lock-background')
async def lock_seam_anchor_background(
    req: SeamAnchorLockRequest,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    camera_ids, group_id, rtsp_by_camera = _resolve_target_cameras(db, req)
    if not camera_ids:
        raise HTTPException(status_code=400, detail='No cameras resolved to lock background')

    use_live_buffer = (
        pipeline_service.is_running
        and not req.force_capture
        and pipeline_service.active_group_id is not None
        and (group_id is None or pipeline_service.active_group_id == group_id)
    )

    locked: list[dict] = []
    failures: list[dict] = []
    live_frames: dict[int, object] | None = None
    if use_live_buffer:
        live_frames = pipeline_service.get_synchronized_frames(
            [int(camera_id) for camera_id in camera_ids],
            timeout_sec=2.5,
        )

    for camera_id in camera_ids:
        frame = None
        source = 'capture'
        if live_frames is not None:
            frame = live_frames.get(int(camera_id))
            if frame is not None:
                source = 'live_sync'

        if frame is None and use_live_buffer:
            frame = pipeline_service.get_latest_camera_frame(int(camera_id))
            if frame is not None:
                source = 'live'

        if frame is None:
            rtsp_url = rtsp_by_camera.get(int(camera_id))
            if not rtsp_url:
                failures.append({'camera_id': camera_id, 'reason': 'rtsp_url_missing'})
                continue
            frame = capture_snapshot(rtsp_url)
            if frame is None:
                failures.append({'camera_id': camera_id, 'reason': 'capture_failed'})
                continue

        if not is_usable_bgr_frame(frame):
            failures.append({'camera_id': camera_id, 'reason': 'frame_quality_rejected'})
            continue

        baseline_path = seam_anchor_baseline.save_baseline(group_id, int(camera_id), frame)
        applied = False
        bg_registry = pipeline_service.bg_registry
        if (
            bg_registry is not None
            and (group_id is None or pipeline_service.active_group_id == group_id)
        ):
            applied = bg_registry.lock_from_frame(int(camera_id), frame)

        locked.append(
            {
                'camera_id': int(camera_id),
                'source': source,
                'baseline_path': baseline_path,
                'applied_to_runtime': applied,
            }
        )

    if not locked:
        raise HTTPException(
            status_code=503,
            detail={'message': 'Failed to lock background', 'failures': failures},
        )

    return {
        'locked': locked,
        'failures': failures,
        'group_id': group_id,
        'used_live_buffer': use_live_buffer,
    }


@router.get('/seam-anchor/state')
async def seam_anchor_state(_=Depends(get_current_user)):
    verifier = pipeline_service.seam_anchor_verifier
    if verifier is None:
        return {
            'enabled': False,
            'anchors': [],
            'message': 'Seam anchor verifier is not active (pipeline not running or hybrid disabled)',
        }

    states = verifier.states_snapshot()
    anchors_payload = []
    for state in states:
        anchors_payload.append(
            {
                'global_id': state.global_id,
                'ship_id': state.ship_id,
                'track_id': state.track_id,
                'cam_a_id': state.cam_a_id,
                'cam_b_id': state.cam_b_id,
                'bbox_a': list(state.bbox_a),
                'bbox_b': list(state.bbox_b) if state.bbox_b else None,
                'first_seen_ts': state.first_seen_ts,
                'last_seen_ts': state.last_seen_ts,
                'anchored_at': state.anchored_at,
                'miss_started_at': state.miss_started_at,
                'last_score_a': state.last_score_a,
                'last_score_b': state.last_score_b,
            }
        )
    debug = verifier.debug_info()
    return {
        'enabled': True,
        'group_id': pipeline_service.active_group_id,
        'anchors': anchors_payload,
        'debug': debug,
    }
