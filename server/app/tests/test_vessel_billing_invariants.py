from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, text

from app.api.v1.endpoints.vessels import normalize_vessel_classification_fields
from app.services import detection_invoice_service as invoice_service
from app.services.ship_invoice_backfill_service import fee_backfill_target


def test_vessel_classification_requires_consistent_type_scope():
    assert normalize_vessel_classification_fields('spot', 343) == ('spot', None)
    assert normalize_vessel_classification_fields('unclassified', 344) == (
        'unclassified',
        None,
    )
    assert normalize_vessel_classification_fields('monthly', 344) == ('monthly', 344)
    with pytest.raises(ValueError, match='monthly'):
        normalize_vessel_classification_fields('monthly', None)


def test_fee_backfill_target_supports_both_scopes():
    spot_fee = SimpleNamespace(
        is_active=True,
        unit='per_hour',
        vessel_id=12,
        vessel_type_id=None,
    )
    monthly_fee = SimpleNamespace(
        is_active=True,
        unit='per_month',
        vessel_id=None,
        vessel_type_id=344,
    )

    assert fee_backfill_target(spot_fee) == ('vessel', 12)
    assert fee_backfill_target(monthly_fee) == ('vessel_type', 344)


def test_unbillable_detection_retires_existing_unpaid_ai_invoice():
    db = MagicMock()
    det = SimpleNamespace(id=9, vessel_id=None)
    existing = SimpleNamespace(
        id=77,
        creation_source='AI',
        payment_status='UNPAID',
        financial_locked_at=None,
        deleted_at=None,
    )

    with (
        patch.object(invoice_service, 'SessionLocal', return_value=db),
        patch.object(invoice_service.detection_repo, 'get', return_value=det),
        patch.object(invoice_service.invoice_repo, 'get_by_detection_id', return_value=existing),
    ):
        result = invoice_service.recompute_ai_invoice_for_detection(9)

    assert result == {'status': 'retired_unbillable', 'invoice_id': 77}
    assert existing.deleted_at is not None
    db.commit.assert_called_once()


def test_legacy_classification_migration_is_idempotent(monkeypatch):
    from app.db import schema_patches

    engine = create_engine('sqlite:///:memory:')
    monkeypatch.setattr(schema_patches, 'engine', engine)
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE vessel_types (id INTEGER PRIMARY KEY, type_name TEXT NOT NULL)'))
        conn.execute(text("""
            CREATE TABLE vessels (
                id INTEGER PRIMARY KEY,
                ship_id TEXT NOT NULL,
                vessel_type_id INTEGER,
                classification TEXT NOT NULL DEFAULT 'unclassified'
            )
        """))
        conn.execute(text("""
            CREATE TABLE fee_configs (
                id INTEGER PRIMARY KEY,
                vessel_type_id INTEGER,
                vessel_id INTEGER,
                fee_name TEXT NOT NULL,
                base_fee NUMERIC NOT NULL,
                unit TEXT,
                is_active BOOLEAN,
                effective_from DATE,
                effective_to DATE,
                berth_limit_count INTEGER,
                berth_limit_unit TEXT,
                over_limit_penalty_amount NUMERIC,
                outside_hours_penalty_amount NUMERIC,
                outside_hours_penalty_per_hour NUMERIC,
                max_berth_duration_minutes INTEGER,
                over_duration_penalty_amount NUMERIC,
                operating_hours JSON
            )
        """))
        conn.execute(text("INSERT INTO vessel_types VALUES (343, 'Tàu lẻ'), (344, 'Tàu tháng')"))
        conn.execute(text("""
            INSERT INTO vessels (id, ship_id, vessel_type_id) VALUES
            (1, 'SPOT-1', 343), (2, 'MONTHLY-1', 344), (3, 'UNKNOWN-1', NULL)
        """))
        conn.execute(text("""
            INSERT INTO fee_configs
                (id, vessel_type_id, vessel_id, fee_name, base_fee, unit, is_active)
            VALUES (25, 343, NULL, 'Spot legacy', 1000000, 'per_hour', 1),
                   (26, 344, NULL, 'Monthly', 50000000, 'per_month', 1)
        """))

    schema_patches._migrate_vessel_classification_data()
    schema_patches._migrate_vessel_classification_data()

    with engine.connect() as conn:
        vessels = conn.execute(
            text('SELECT id, classification, vessel_type_id FROM vessels ORDER BY id')
        ).all()
        copied = conn.execute(
            text('SELECT count(*) FROM fee_configs WHERE vessel_id = 1 AND is_active = 1')
        ).scalar_one()
        legacy_active = conn.execute(
            text('SELECT is_active FROM fee_configs WHERE id = 25')
        ).scalar_one()

    assert vessels == [
        (1, 'spot', None),
        (2, 'monthly', 344),
        (3, 'unclassified', None),
    ]
    assert copied == 1
    assert not legacy_active
