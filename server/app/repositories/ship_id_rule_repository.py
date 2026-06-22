from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


class ShipIdRuleRepository:
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
        fields = {k: v for k, v in data.items() if v is not None}
        if not fields:
            return self.get_pattern(db, pattern_id)
        fields['updated_at'] = datetime.now(timezone.utc)
        fields['id'] = pattern_id
        set_clause = ', '.join(f'{k} = :{k}' for k in fields if k != 'id')
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
        fields = {k: v for k, v in data.items() if v is not None}
        if not fields:
            return self.get_convert_map_entry(db, entry_id)
        fields['id'] = entry_id
        set_clause = ', '.join(f'{k} = :{k}' for k in fields if k != 'id')
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
        """Return a string representing the last-modified state across all 3 tables."""
        row = db.execute(text("""
            SELECT COALESCE(MAX(ts)::text, '0')
            FROM (
                SELECT MAX(updated_at) AS ts FROM ship_id_patterns
                UNION ALL
                SELECT MAX(created_at) AS ts FROM ship_id_blacklist
                UNION ALL
                SELECT MAX(created_at) AS ts FROM ship_id_convert_map
            ) t
        """)).scalar()
        return str(row)


ship_id_rule_repo = ShipIdRuleRepository()
