#!/usr/bin/env python3
"""Hard-delete all detections, invoices, and detection media in MinIO."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from app.db.session import SessionLocal
from app.services.detection_cleanup_service import purge_all_detections_and_invoices
from app.services.pipeline_service import pipeline_service

logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
_log = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description='Purge all detections, invoices, and MinIO detection media.')
    parser.add_argument(
        '--yes',
        action='store_true',
        help='Skip confirmation prompt.',
    )
    args = parser.parse_args()

    if pipeline_service.is_running:
        _log.error('Stop the AI pipeline before purge (pipeline is running).')
        return 1

    if not args.yes:
        _log.error('Refusing to run without --yes (destructive operation).')
        return 1

    db = SessionLocal()
    try:
        summary = purge_all_detections_and_invoices(db)
    finally:
        db.close()

    print(summary)
    return 0


if __name__ == '__main__':
    sys.exit(main())
