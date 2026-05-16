#!/usr/bin/env python3
"""
Audit detection media layout on MinIO S3 API (MINIO_ENDPOINT, default 127.0.0.1:9100).

Port 9101 is the MinIO Console UI only — objects live in the bucket on :9100.
Local ./app/data-docker/minio is the docker volume for the same store when using compose.

  cd server && python scripts/verify_minio_layout.py
"""
from __future__ import annotations

import os
import sys

SERVER_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if SERVER_ROOT not in sys.path:
    sys.path.insert(0, SERVER_ROOT)
os.chdir(SERVER_ROOT)

from app.services.storage.minio_probe import probe_minio  # noqa: E402


def main() -> None:
    summary = probe_minio(max_list=10000)
    print('MinIO S3 API endpoint:', summary['endpoint'])
    print('Bucket:', summary['bucket'])
    print('Objects listed (cap):', summary['listed'])
    print('Layout counts:', summary['counts'])
    print()
    if summary['final_samples']:
        print('New layout samples (detections/DD-MM-YYYY/id/videos|images/):')
        for key in summary['final_samples']:
            print(' ', key)
    else:
        print('No new-layout final objects found.')
    if summary['legacy_samples']:
        print()
        print('Legacy samples (detections/{id}/video|image/ — old code):')
        for key in summary['legacy_samples']:
            print(' ', key)
    if summary['staging_samples']:
        print()
        print('Staging samples:')
        for key in summary['staging_samples']:
            print(' ', key)
    final_n = int(summary['counts'].get('final', 0))
    sys.exit(0 if final_n > 0 else 2)


if __name__ == '__main__':
    main()
