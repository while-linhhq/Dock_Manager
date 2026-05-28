from app.utils.port_timing_config import resolve_positive_seconds


def test_resolve_prefers_seconds_key() -> None:
    cfg = {'ocr_interval_sec': '1.2', 'ocr_interval_frames': '10'}
    assert (
        resolve_positive_seconds(
            cfg,
            sec_key='ocr_interval_sec',
            legacy_frame_key='ocr_interval_frames',
            default_sec=0.5,
            fps=20.0,
        )
        == 1.2
    )


def test_resolve_converts_legacy_frames() -> None:
    cfg = {'track_min_hits': '30'}
    assert (
        resolve_positive_seconds(
            cfg,
            sec_key='track_min_confirm_sec',
            legacy_frame_key='track_min_hits',
            default_sec=1.5,
            fps=20.0,
        )
        == 1.5
    )
