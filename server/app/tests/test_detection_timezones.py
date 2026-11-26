from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from app.schemas.detection import DetectionRead, DetectionUpdate


def test_read_legacy_and_aware_times_have_same_utc_contract():
    row = DetectionRead.model_validate(dict(
        id=48958, created_at=datetime(2026, 11, 25),
        start_time='2026-11-25T04:30:02.370914',
        end_time='2026-11-25T04:32:52.181633',
        berth_in_time='2026-11-25T11:32:27.064126+07:00',
        berth_out_time='2026-11-25T04:32:52.181633Z',
    ))
    assert row.end_time == row.berth_out_time
    assert row.start_time.microsecond == 370914
    for key in ('start_time', 'end_time', 'berth_in_time', 'berth_out_time'):
        assert getattr(row, key).tzinfo == timezone.utc
        assert row.model_dump(mode='json')[key].endswith('Z')


def test_patch_keeps_unset_distinct_from_clear_and_normalizes_offsets():
    assert DetectionUpdate(confidence=0.7).model_dump(exclude_unset=True) == {'confidence': 0.7}
    assert DetectionUpdate(start_time=None).model_dump(exclude_unset=True) == {'start_time': None}
    value = DetectionUpdate(start_time='2026-11-25T11:30:02.370914+07:00').start_time
    assert value == datetime(2026, 11, 25, 4, 30, 2, 370914, tzinfo=timezone.utc)


def test_update_sets_transaction_timezone_before_flush_without_committing():
    from app.repositories.detection_repository import DetectionRepository

    repo = DetectionRepository()
    row = SimpleNamespace(start_time=None)
    repo.get = Mock(return_value=row)
    db = Mock()
    db.get_bind.return_value.dialect.name = 'postgresql'
    events = []
    db.execute.side_effect = lambda stmt: events.append(str(stmt))
    db.flush.side_effect = lambda: events.append('flush')
    value = datetime(2026, 11, 25, 4, 30, tzinfo=timezone.utc)

    assert repo.update_fields(db, 48958, {'start_time': value}, commit=False) is row
    assert row.start_time == value
    assert events == ["SET LOCAL TIME ZONE 'UTC'", 'flush']
    db.commit.assert_not_called()


def test_engine_pins_postgres_session_timezone_to_utc():
    """Mọi connection PostgreSQL phải chạy với TimeZone = UTC.

    Không ghim thì cột naive chứa giờ UTC bị quy đổi theo cấu hình server ngay
    lúc ghi, làm lệch toàn bộ so sánh/lọc theo thời gian.
    """
    from app.db.session import build_connect_args

    assert build_connect_args('postgresql+psycopg://u:p@h:5432/db') == {
        'options': '-c timezone=UTC'
    }
    assert build_connect_args('postgresql://u:p@h:5432/db') == {
        'options': '-c timezone=UTC'
    }
    # SQLite (test in-memory) không có khái niệm TimeZone session.
    assert build_connect_args('sqlite:///:memory:') == {}
    # Giữ options khác nhưng vẫn ghim UTC.
    assert build_connect_args(
        'postgresql://u:p@h:5432/db?options=-c%20statement_timeout%3D5000'
    ) == {'options': '-c statement_timeout=5000 -c timezone=UTC'}
    assert build_connect_args(
        'postgresql://u:p@h/db?options=-c%20timezone%3DAsia%2FSaigon%20-c%20statement_timeout%3D5000'
    ) == {'options': '-c timezone=Asia/Saigon -c statement_timeout=5000 -c timezone=UTC'}
    assert build_connect_args('postgresql://u:p@h/db?options=') == {
        'options': '-c timezone=UTC'
    }
    try:
        build_connect_args('postgresql://u:p@h/db?options=a&options=b')
    except ValueError:
        pass
    else:
        raise AssertionError('Duplicate options must be rejected')


def test_init_sql_and_migration_agree_on_timestamptz_columns():
    """Schema khởi tạo và migration chỉ đổi start/end trong phạm vi task."""
    from pathlib import Path
    import re

    db_dir = Path(__file__).resolve().parents[1] / 'db'
    init_sql = (db_dir / 'init.sql').read_text(encoding='utf-8')
    migration = (
        db_dir / 'migrations' / '2026_11_detection_timestamptz.sql'
    ).read_text(encoding='utf-8')

    for column in ('start_time', 'end_time'):
        assert re.search(
            rf'^\s*{column}\s+TIMESTAMPTZ\b', init_sql, re.MULTILINE
        ), f'init.sql must declare {column} as TIMESTAMPTZ'
        assert f'ALTER COLUMN {column} TYPE TIMESTAMPTZ' in migration, (
            f'migration must convert {column} to TIMESTAMPTZ'
        )
        # Dữ liệu cũ là UTC tường minh — không được để PostgreSQL tự đoán theo
        # TimeZone của session.
        assert f'USING {column} AT TIME ZONE' in migration, (
            f'migration must interpret {column} as UTC'
        )
    for column in ('created_at', 'verified_at', 'berth_in_time', 'berth_out_time'):
        assert f'ALTER COLUMN {column}' not in migration
