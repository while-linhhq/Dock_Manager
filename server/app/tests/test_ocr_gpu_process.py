from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.ai.ocr_gpu_process import OcrGpuProcessClient
from app.utils.ai.ship_id_recognizer import create_ship_id_recognizer


def test_create_ship_id_recognizer_uses_subprocess_when_ready():
    fake_client = MagicMock()
    fake_client.start.return_value = True
    fake_client.device = 'gpu'

    with patch('app.services.ai.ocr_gpu_process.OcrGpuProcessClient', return_value=fake_client):
        recognizer = create_ship_id_recognizer(prefer_gpu_subprocess=True)

    assert recognizer is fake_client
    fake_client.start.assert_called_once()


def test_create_ship_id_recognizer_falls_back_when_subprocess_fails():
    fake_client = MagicMock()
    fake_client.start.return_value = False
    fallback = MagicMock()

    with patch('app.services.ai.ocr_gpu_process.OcrGpuProcessClient', return_value=fake_client):
        with patch('app.utils.ai.ship_id_recognizer.ShipIdRecognizer', return_value=fallback) as mock_cls:
            recognizer = create_ship_id_recognizer(prefer_gpu_subprocess=True)

    assert recognizer is fallback
    fake_client.close.assert_called_once()
    mock_cls.assert_called_once()
    assert mock_cls.call_args.kwargs.get('use_gpu') is False


def test_ocr_gpu_client_close_terminates_alive_process():
    client = OcrGpuProcessClient.__new__(OcrGpuProcessClient)
    client._started = True
    client._cpu_fallback = None
    client._request_q = MagicMock()
    proc = MagicMock()
    proc.is_alive.side_effect = [True, False]
    client._proc = proc

    client.close()

    proc.join.assert_called()
    assert client._started is False
