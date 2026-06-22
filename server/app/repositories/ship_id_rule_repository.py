import hashlib
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

_PATTERN_UPDATE_FIELDS = frozenset({'name', 'pattern', 'priority', 'description', 'is_active'})
_CONVERT_MAP_UPDATE_FIELDS = frozenset({'correct_value', 'reason'})


class ShipIdRuleRepository:
    @staticmethod
    def _pick_update_fields(data: dict, allowed: frozenset[str]) -> dict:
        return {key: value for key, value in data.items() if key in allowed and value is not None}
    # ── Patterns ──────────────────────────────────────────────────────────

    def get_all_patterns(self, db: Session) -> list[dict]:
        rows = db.execute(
            text('SELECT * FROM ship_id_patterns ORDER BY priority DESC, id ASC')
        ).mappings().all()
        return [dict(r) for r in rows]

    def get_active_patterns(self, db: Session) -> list[dict]:
        rows = db.execute(
            text('SELECT * FROM ship_id_patterns WHERE is_active = TRUE ORDER BY priority DESC, id ASC')
        ).mappings().all()
        return [dict(r) for r in rows]

    def get_pattern(self, db: Session, pattern_id: int) -> Optional[dict]:
        row = db.execute(
            text('SELECT * FROM ship_id_patterns WHERE id = :id'), {'id': pattern_id}
        ).mappings().first()
        return dict(row) if row else None

    def create_pattern(self, db: Session, data: dict) -> dict:
        row = db.execute(
            text("""
                INSERT INTO ship_id_patterns (name, pattern, priority, description, is_active)
                VALUES (:name, :pattern, :priority, :description, :is_active)
                RETURNING *
            """),
            data,
        ).mappings().first()
        db.commit()
        return dict(row)

    def update_pattern(self, db: Session, pattern_id: int, data: dict) -> Optional[dict]:
        fields = self._pick_update_fields(data, _PATTERN_UPDATE_FIELDS)
        if not fields:
            return self.get_pattern(db, pattern_id)
        fields['updated_at'] = datetime.now(timezone.utc)
        fields['id'] = pattern_id
        set_clause = ', '.join(f'{key} = :{key}' for key in fields if key != 'id')
        row = db.execute(
            text(f'UPDATE ship_id_patterns SET {set_clause} WHERE id = :id RETURNING *'),
            fields,
        ).mappings().first()
        db.commit()
        return dict(row) if row else None

    def delete_pattern(self, db: Session, pattern_id: int) -> bool:
        result = db.execute(
            text('DELETE FROM ship_id_patterns WHERE id = :id'), {'id': pattern_id}
        )
        db.commit()
        return result.rowcount > 0

    # ── Blacklist ──────────────────────────────────────────────────────────

    def get_all_blacklist(self, db: Session) -> list[dict]:
        rows = db.execute(
            text('SELECT * FROM ship_id_blacklist ORDER BY created_at DESC')
        ).mappings().all()
        return [dict(r) for r in rows]

    def create_blacklist(self, db: Session, data: dict) -> dict:
        row = db.execute(
            text("""
                INSERT INTO ship_id_blacklist (value, reason)
                VALUES (:value, :reason)
                RETURNING *
            """),
            data,
        ).mappings().first()
        db.commit()
        return dict(row)

    def delete_blacklist(self, db: Session, entry_id: int) -> bool:
        result = db.execute(
            text('DELETE FROM ship_id_blacklist WHERE id = :id'), {'id': entry_id}
        )
        db.commit()
        return result.rowcount > 0

    # ── Convert Map ────────────────────────────────────────────────────────

    def get_all_convert_map(self, db: Session) -> list[dict]:
        rows = db.execute(
            text('SELECT * FROM ship_id_convert_map ORDER BY created_at DESC')
        ).mappings().all()
        return [dict(r) for r in rows]

    def get_convert_map_entry(self, db: Session, entry_id: int) -> Optional[dict]:
        row = db.execute(
            text('SELECT * FROM ship_id_convert_map WHERE id = :id'), {'id': entry_id}
        ).mappings().first()
        return dict(row) if row else None

    def create_convert_map(self, db: Session, data: dict) -> dict:
        row = db.execute(
            text("""
                INSERT INTO ship_id_convert_map (wrong_value, correct_value, reason)
                VALUES (:wrong_value, :correct_value, :reason)
                RETURNING *
            """),
            data,
        ).mappings().first()
        db.commit()
        return dict(row)

    def update_convert_map(self, db: Session, entry_id: int, data: dict) -> Optional[dict]:
        fields = self._pick_update_fields(data, _CONVERT_MAP_UPDATE_FIELDS)
        if not fields:
            return self.get_convert_map_entry(db, entry_id)
        fields['id'] = entry_id
        set_clause = ', '.join(f'{key} = :{key}' for key in fields if key != 'id')
        row = db.execute(
            text(f'UPDATE ship_id_convert_map SET {set_clause} WHERE id = :id RETURNING *'),
            fields,
        ).mappings().first()
        db.commit()
        return dict(row) if row else None

    def delete_convert_map(self, db: Session, entry_id: int) -> bool:
        result = db.execute(
            text('DELETE FROM ship_id_convert_map WHERE id = :id'), {'id': entry_id}
        )
        db.commit()
        return result.rowcount > 0

    # ── State hash for polling ─────────────────────────────────────────────

    def get_state_hash(self, db: Session) -> str:
        """Fingerprint rule state: per-table counts, timestamps, and convert-map content."""
        stats = db.execute(text("""
            SELECT
                (SELECT COUNT(*) FROM ship_id_patterns) AS pattern_count,
                (SELECT COALESCE(CAST(MAX(updated_at) AS TEXT), '0') FROM ship_id_patterns) AS pattern_ts,
                (SELECT COUNT(*) FROM ship_id_blacklist) AS blacklist_count,
                (SELECT COALESCE(CAST(MAX(created_at) AS TEXT), '0') FROM ship_id_blacklist) AS blacklist_ts,
                (SELECT COUNT(*) FROM ship_id_convert_map) AS convert_count,
                (SELECT COALESCE(CAST(MAX(created_at) AS TEXT), '0') FROM ship_id_convert_map) AS convert_ts
        """)).mappings().first()

        convert_rows = db.execute(text("""
            SELECT wrong_value, correct_value, reason
            FROM ship_id_convert_map
            ORDER BY id
        """)).mappings().all()
        convert_content = (
            hashlib.md5(
                '|'.join(
                    f"{row['wrong_value']}:{row['correct_value']}:{row['reason'] or ''}"
                    for row in convert_rows
                ).encode(),
                usedforsecurity=False,
            ).hexdigest()
            if convert_rows
            else '0'
        )

        return '|'.join([
            str(stats['pattern_count']),
            str(stats['pattern_ts']),
            str(stats['blacklist_count']),
            str(stats['blacklist_ts']),
            str(stats['convert_count']),
            str(stats['convert_ts']),
            convert_content,
        ])


ship_id_rule_repo = ShipIdRuleRepository()
