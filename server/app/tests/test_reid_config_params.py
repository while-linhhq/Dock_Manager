"""Tests for Re-ID overlap-merge runtime config loading (Phần 3)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.pipeline_service import PipelineService


def _cfg_row(key: str, value: str):
    row = MagicMock()
    row.key = key
    row.value = value
    return row


def test_runtime_config_loads_overlap_merge_defaults():
    """When port_configs has no reid_* overlap keys, runtime_cfg uses settings defaults."""
    svc = PipelineService()
    with (
        patch('app.services.pipeline_service.SessionLocal') as mock_session,
        patch('app.services.pipeline_service.port_config_repo') as mock_repo,
    ):
        mock_repo.get_all.return_value = []
        mock_session.return_value = MagicMock()
        cfg = svc._load_runtime_config()

    assert cfg['reid_overlap_merge_enabled'] is True
    assert cfg['reid_edge_zone_ratio'] == 0.15
    assert cfg['reid_embedding_weight'] == 0.6
    assert cfg['reid_color_weight'] == 0.25
    assert cfg['reid_size_weight'] == 0.15
    assert cfg['reid_accept_threshold'] == 0.6
    assert cfg['reid_min_margin'] == 0.12


def test_runtime_config_reads_overlap_merge_overrides():
    """port_configs values override settings defaults."""
    svc = PipelineService()
    rows = [
        _cfg_row('reid_overlap_merge_enabled', 'false'),
        _cfg_row('reid_edge_zone_ratio', '0.2'),
        _cfg_row('reid_embedding_weight', '0.5'),
        _cfg_row('reid_color_weight', '0.3'),
        _cfg_row('reid_size_weight', '0.2'),
        _cfg_row('reid_accept_threshold', '0.7'),
        _cfg_row('reid_min_margin', '0.1'),
    ]
    with (
        patch('app.services.pipeline_service.SessionLocal') as mock_session,
        patch('app.services.pipeline_service.port_config_repo') as mock_repo,
    ):
        mock_repo.get_all.return_value = rows
        mock_session.return_value = MagicMock()
        cfg = svc._load_runtime_config()

    assert cfg['reid_overlap_merge_enabled'] is False
    assert cfg['reid_edge_zone_ratio'] == 0.2
    assert cfg['reid_embedding_weight'] == 0.5
    assert cfg['reid_color_weight'] == 0.3
    assert cfg['reid_size_weight'] == 0.2
    assert cfg['reid_accept_threshold'] == 0.7
    assert cfg['reid_min_margin'] == 0.1
