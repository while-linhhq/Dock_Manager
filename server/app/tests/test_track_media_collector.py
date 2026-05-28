import numpy as np

from app.services.ai.track_media_collector import TrackMediaCollector


def test_fused_and_single_detection_snapshots_stay_distinct() -> None:
    collector = TrackMediaCollector()
    fused = np.zeros((120, 240, 3), dtype=np.uint8)
    fused[:, :, 1] = 200
    single = np.zeros((120, 80, 3), dtype=np.uint8)
    single[:, :, 2] = 180

    collector.update_fused_detection('gid_test', 0.95, fused)
    collector.update_single_detection('gid_test', 0.90, 4, single)

    snap = collector.pop('gid_test')
    assert snap is not None
    assert snap.fused_best_detection_jpeg is not None
    assert snap.single_best_detection_jpeg is not None
    assert snap.fused_best_detection_jpeg != snap.single_best_detection_jpeg
    assert snap.single_best_camera_id == 4
