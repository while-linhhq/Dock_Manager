# server/app/tests/test_license_state_repository.py
import pytest
from sqlalchemy import inspect
from app.db.schema_patches import _ensure_license_state
from app.db.session import SessionLocal, engine
from app.repositories.license_state_repository import LicenseStateRepository


@pytest.fixture(autouse=True)
def _license_state_table():
    # Trên DB chưa từng có bảng mới, test repository chạy trước test schema
    # patch (theo thứ tự khai báo) nên phải tự bảo đảm bảng tồn tại — đúng
    # đường đi production (startup gọi apply_schema_patches()).
    _ensure_license_state()


def test_ensure_is_idempotent():
    db = SessionLocal()
    try:
        repo = LicenseStateRepository()
        row = repo.ensure(db, 'inst-test-1')
        assert row.id == 1
        again = repo.ensure(db, 'ignored')
        assert again.instance_id == row.instance_id  # existing row wins
        repo.update(db, status='valid', features={'max_cameras': 12})
        db.refresh(again)
        assert again.status == 'valid' and again.features == {'max_cameras': 12}
    finally:
        db.rollback(); db.close()


def test_schema_patch_creates_table():
    from app.db.schema_patches import _ensure_license_state
    _ensure_license_state()
    _ensure_license_state()
    assert inspect(engine).has_table('license_state')
