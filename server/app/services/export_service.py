import os
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from sqlalchemy.orm import Session

from app.repositories.port_log_repository import port_log_repo
from app.repositories.export_log_repository import export_log_repo

EXPORTS_DIR = Path('exports')
_HEADER_FILL = PatternFill('solid', fgColor='5B9BD5')
_HEADER_FONT = Font(bold=True, color='FFFFFF')


class ExportService:
    def export_port_logs_excel(
        self,
        db: Session,
        log_date: Optional[date] = None,
        ship_id: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> str:
        logs = port_log_repo.get_all_logs(db, limit=10000, ship_id=ship_id, log_date=log_date)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Port Logs'

        headers = ['ID', 'Seq', 'Logged At', 'Track ID', 'Ship ID', 'First Seen', 'Last Seen', 'Confidence', 'OCR Attempts', 'Schema Ver']
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.fill = _HEADER_FILL
            cell.font = _HEADER_FONT
            cell.alignment = Alignment(horizontal='center')

        for row_idx, log in enumerate(logs, 2):
            ws.cell(row=row_idx, column=1, value=log.id)
            ws.cell(row=row_idx, column=2, value=log.seq)
            ws.cell(row=row_idx, column=3, value=str(log.logged_at) if log.logged_at else '')
            ws.cell(row=row_idx, column=4, value=log.track_id)
            ws.cell(row=row_idx, column=5, value=log.voted_ship_id)
            ws.cell(row=row_idx, column=6, value=str(log.first_seen_at) if log.first_seen_at else '')
            ws.cell(row=row_idx, column=7, value=str(log.last_seen_at) if log.last_seen_at else '')
            ws.cell(row=row_idx, column=8, value=log.confidence)
            ws.cell(row=row_idx, column=9, value=log.ocr_attempts)
            ws.cell(row=row_idx, column=10, value=log.schema_version)

        EXPORTS_DIR.mkdir(exist_ok=True)
        filename = f"port_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        file_path = str(EXPORTS_DIR / filename)
        wb.save(file_path)

        # Record the export
        export_log_repo.create(db, {
            'user_id': user_id,
            'export_type': 'port_logs',
            'file_path': file_path,
            'filters': {'date': str(log_date) if log_date else None, 'ship_id': ship_id},
            'row_count': len(logs),
        })

        return file_path


export_service = ExportService()
