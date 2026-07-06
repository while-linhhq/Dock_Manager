"""Migrate DB media URIs minio://media/<key> -> s3://<new>/<key>.

Gated per-key: only rewrite when object EXISTS in the new AWS bucket
(head_object). Missing keys are skipped and reported (avoids dangling refs).
Backs up old values to media_uri_migration_backup before mutating.
Idempotent: safe to re-run.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

sys.path.insert(0, '/home/ubuntu-linh/Documents/dock-manager/server')

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.storage.s3_service import get_s3_client  # noqa: E402
from sqlalchemy import text  # noqa: E402

NEW_BUCKET = str(settings.MINIO_BUCKET).strip()
OLD_PREFIX = 'minio://media/'
NEW_PREFIX = f's3://{NEW_BUCKET}/'

TARGETS = [
    ('detection_media', 'file_path', 'id'),
    ('detections', 'audit_image_path', 'id'),
    ('detections', 'video_path', 'id'),
    ('media_short_links', 'minio_path', 'code'),
]

DRY_RUN = '--apply' not in sys.argv


def key_exists(client, key: str) -> bool:
    try:
        client.head_object(Bucket=NEW_BUCKET, Key=key)
        return True
    except Exception:
        return False


def main() -> None:
    client = get_s3_client()
    db = SessionLocal()
    exist_cache: dict[str, bool] = {}
    mode = 'DRY-RUN' if DRY_RUN else 'APPLY'
    print(f'=== media bucket migration [{mode}] -> {NEW_BUCKET} ===')

    # backup table
    if not DRY_RUN:
        db.execute(text(
            'CREATE TABLE IF NOT EXISTS media_uri_migration_backup ('
            'id serial primary key, tbl text, col text, row_key text, '
            'old_value text, new_value text, migrated_at timestamptz)'
        ))
        db.commit()

    grand = {'migrate': 0, 'skip_missing': 0}
    for tbl, col, pk in TARGETS:
        rows = db.execute(text(
            f'SELECT {pk} AS k, {col} AS v FROM {tbl} '
            f"WHERE {col} LIKE :p"
        ), {'p': OLD_PREFIX + '%'}).fetchall()
        migrate = skip = 0
        for r in rows:
            uri = r.v
            key = uri[len(OLD_PREFIX):]
            if key not in exist_cache:
                exist_cache[key] = key_exists(client, key)
            if not exist_cache[key]:
                skip += 1
                continue
            new_uri = NEW_PREFIX + key
            if not DRY_RUN:
                db.execute(text(
                    'INSERT INTO media_uri_migration_backup '
                    '(tbl,col,row_key,old_value,new_value,migrated_at) '
                    'VALUES (:t,:c,:k,:o,:n,:ts)'
                ), {'t': tbl, 'c': col, 'k': str(r.k), 'o': uri,
                    'n': new_uri, 'ts': datetime.now(timezone.utc)})
                db.execute(text(
                    f'UPDATE {tbl} SET {col}=:n WHERE {pk}=:k'
                ), {'n': new_uri, 'k': r.k})
            migrate += 1
        if not DRY_RUN:
            db.commit()
        grand['migrate'] += migrate
        grand['skip_missing'] += skip
        print(f'  {tbl}.{col:20} rewrite={migrate:4}  skip_missing={skip:4}')

    print(f'--- total rewrite={grand["migrate"]}  '
          f'skip_missing={grand["skip_missing"]} ---')
    if DRY_RUN:
        print('DRY-RUN only. Re-run with --apply to mutate.')
    db.close()


if __name__ == '__main__':
    main()
