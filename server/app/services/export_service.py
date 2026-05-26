import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from sqlalchemy.orm import Session

from app.repositories.fee_config_repository import fee_config_repo
from app.repositories.invoice_repository import invoice_repo
from app.repositories.port_log_repository import port_log_repo
from app.repositories.export_log_repository import export_log_repo
from app.utils.fee_billing_unit import fee_billing_unit_label

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

        headers = [
            'ID',
            'Seq',
            'Ships Completed Today',
            'Logged At',
            'Track ID',
            'Voted Ship ID',
            'First Seen',
            'Last Seen',
            'Confidence',
            'OCR Attempts',
            'Vote Summary (JSON)',
            'Schema Ver',
        ]
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.fill = _HEADER_FILL
            cell.font = _HEADER_FONT
            cell.alignment = Alignment(horizontal='center')

        for row_idx, log in enumerate(logs, 2):
            vote_json = ''
            if log.vote_summary is not None:
                try:
                    vote_json = json.dumps(log.vote_summary, ensure_ascii=False)
                except (TypeError, ValueError):
                    vote_json = str(log.vote_summary)
            ws.cell(row=row_idx, column=1, value=log.id)
            ws.cell(row=row_idx, column=2, value=log.seq)
            ws.cell(row=row_idx, column=3, value=getattr(log, 'ships_completed_today', None))
            ws.cell(row=row_idx, column=4, value=str(log.logged_at) if log.logged_at else '')
            ws.cell(row=row_idx, column=5, value=log.track_id)
            ws.cell(row=row_idx, column=6, value=log.voted_ship_id)
            ws.cell(row=row_idx, column=7, value=str(log.first_seen_at) if log.first_seen_at else '')
            ws.cell(row=row_idx, column=8, value=str(log.last_seen_at) if log.last_seen_at else '')
            ws.cell(row=row_idx, column=9, value=log.confidence)
            ws.cell(row=row_idx, column=10, value=log.ocr_attempts)
            ws.cell(row=row_idx, column=11, value=vote_json)
            ws.cell(row=row_idx, column=12, value=log.schema_version)

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

    @staticmethod
    def _payment_status_label(status: Optional[str]) -> str:
        key = (status or 'UNPAID').upper()
        mapping = {
            'PAID': 'Đã thanh toán',
            'PARTIAL': 'Thanh toán một phần',
            'UNPAID': 'Chưa thanh toán',
            'OVERDUE': 'Quá hạn',
            'CANCELLED': 'Đã hủy',
        }
        return mapping.get(key, status or '')

    @staticmethod
    def _berth_minutes(invoice) -> Optional[float]:
        det = getattr(invoice, 'detection', None)
        if det is not None and det.start_time is not None and det.end_time is not None:
            secs = (det.end_time - det.start_time).total_seconds()
            if secs > 0:
                return round(secs / 60, 2)
        return None

    @staticmethod
    def _invoice_ref_fees(invoice) -> str:
        parts: list[str] = []
        for item in invoice.items or []:
            fc = getattr(item, 'fee_config', None)
            if fc is not None and getattr(fc, 'fee_name', None):
                parts.append(str(fc.fee_name))
            elif getattr(item, 'description', None):
                parts.append(str(item.description))
        return '; '.join(parts)

    @staticmethod
    def _invoice_list_kind_label(creation_source: Optional[str]) -> str:
        src = (creation_source or 'USER').upper()
        if src in ('AI', 'ORDER_AUTO'):
            return 'Hóa đơn tự động'
        return 'Hóa đơn tạo tay'

    def _write_revenue_invoices_workbook(self, invoices: list) -> openpyxl.Workbook:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Hóa đơn'

        headers = [
            'ID',
            'Số hóa đơn',
            'Danh mục',
            'Mã đơn hàng',
            'Mã tàu',
            'Loại tàu',
            'Detection ID',
            'Confidence TB',
            'Thời gian neo (phút)',
            'Thời gian tạo',
            'Ngày xóa',
            'Trạng thái thanh toán',
            'Phí tham chiếu',
            'Tổng tiền',
            'Nguồn tạo',
            'Tạo bởi',
            'Vượt giới hạn neo',
        ]
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.fill = _HEADER_FILL
            cell.font = _HEADER_FONT
            cell.alignment = Alignment(horizontal='center')

        for row_idx, inv in enumerate(invoices, 2):
            vessel = inv.vessel
            ship_id = getattr(inv, 'vessel_ship_id_snapshot', None) or (
                vessel.ship_id if vessel else None
            )
            type_name = getattr(inv, 'vessel_type_name_snapshot', None) or (
                vessel.vessel_type.type_name
                if vessel and vessel.vessel_type
                else None
            )
            conf = None
            det = inv.detection
            if det is not None and det.confidence is not None:
                conf = float(det.confidence)
            creator_label = '—'
            if inv.creator is not None:
                creator_label = inv.creator.full_name or inv.creator.username or str(inv.creator.id)

            ws.cell(row=row_idx, column=1, value=inv.id)
            ws.cell(row=row_idx, column=2, value=inv.invoice_number)
            ws.cell(row=row_idx, column=3, value=self._invoice_list_kind_label(inv.creation_source))
            ws.cell(row=row_idx, column=4, value=inv.order_id)
            ws.cell(row=row_idx, column=5, value=ship_id)
            ws.cell(row=row_idx, column=6, value=type_name)
            ws.cell(row=row_idx, column=7, value=inv.detection_id)
            ws.cell(row=row_idx, column=8, value=conf)
            ws.cell(row=row_idx, column=9, value=self._berth_minutes(inv))
            ws.cell(row=row_idx, column=10, value=str(inv.created_at) if inv.created_at else '')
            ws.cell(row=row_idx, column=11, value=str(inv.deleted_at) if inv.deleted_at else '')
            ws.cell(row=row_idx, column=12, value=self._payment_status_label(inv.payment_status))
            ws.cell(row=row_idx, column=13, value=self._invoice_ref_fees(inv))
            ws.cell(row=row_idx, column=14, value=float(inv.total_amount or 0))
            ws.cell(row=row_idx, column=15, value=inv.creation_source)
            ws.cell(row=row_idx, column=16, value=creator_label)
            ws.cell(
                row=row_idx,
                column=17,
                value='Có' if getattr(inv, 'is_over_berth_limit', False) else 'Không',
            )
        return wb

    def export_revenue_invoices_excel(
        self,
        db: Session,
        invoice_ids: list[int],
        *,
        user_id: Optional[int] = None,
        list_kind: Optional[str] = None,
        invoice_sub_tab: Optional[str] = None,
        filters: Optional[dict] = None,
    ) -> str:
        invoices = invoice_repo.get_by_ids(db, invoice_ids, include_deleted=True)
        if not invoices:
            raise ValueError('No invoices found for export')

        wb = self._write_revenue_invoices_workbook(invoices)

        EXPORTS_DIR.mkdir(exist_ok=True)
        kind = (list_kind or 'invoices').replace('_', '-')
        tab = (invoice_sub_tab or 'all').replace('_', '-')
        filename = f"revenue_{kind}_{tab}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        file_path = str(EXPORTS_DIR / filename)
        wb.save(file_path)

        export_log_repo.create(
            db,
            {
                'user_id': user_id,
                'export_type': 'revenue_invoices',
                'file_path': file_path,
                'filters': filters or {'invoice_ids': invoice_ids, 'list_kind': list_kind},
                'row_count': len(invoices),
            },
        )
        return file_path

    def export_all_revenue_invoices_excel(
        self,
        db: Session,
        *,
        user_id: Optional[int] = None,
    ) -> str:
        invoices = invoice_repo.get_all_revenue_export(db)
        if not invoices:
            raise ValueError('No invoices found for export')

        wb = self._write_revenue_invoices_workbook(invoices)

        EXPORTS_DIR.mkdir(exist_ok=True)
        filename = f"revenue_all_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        file_path = str(EXPORTS_DIR / filename)
        wb.save(file_path)

        export_log_repo.create(
            db,
            {
                'user_id': user_id,
                'export_type': 'revenue_invoices_all',
                'file_path': file_path,
                'filters': {'scope': 'all_revenue_history'},
                'row_count': len(invoices),
            },
        )
        return file_path

    def export_revenue_fee_configs_excel(
        self,
        db: Session,
        fee_config_ids: list[int],
        *,
        user_id: Optional[int] = None,
        filters: Optional[dict] = None,
    ) -> str:
        fees = fee_config_repo.get_by_ids(db, fee_config_ids)
        if not fees:
            raise ValueError('No fee configs found for export')

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Cấu hình phí'

        headers = [
            'ID',
            'Tên phí',
            'Loại tàu',
            'Đơn giá',
            'Đơn vị',
            'Đang áp dụng',
            'Giới hạn neo',
            'Hiệu lực từ',
            'Hiệu lực đến',
            'Tạo lúc',
            'Cập nhật',
        ]
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.fill = _HEADER_FILL
            cell.font = _HEADER_FONT
            cell.alignment = Alignment(horizontal='center')

        for row_idx, fee in enumerate(fees, 2):
            limit_label = ''
            if fee.berth_limit_count and fee.berth_limit_unit:
                unit = 'ngày' if fee.berth_limit_unit == 'day' else 'tháng'
                limit_label = f'{fee.berth_limit_count} lần/{unit}'
            ws.cell(row=row_idx, column=1, value=fee.id)
            ws.cell(row=row_idx, column=2, value=fee.fee_name)
            ws.cell(
                row=row_idx,
                column=3,
                value=fee.vessel_type.type_name if fee.vessel_type else '',
            )
            ws.cell(row=row_idx, column=4, value=float(fee.base_fee or 0))
            ws.cell(row=row_idx, column=5, value=fee_billing_unit_label(fee.unit))
            ws.cell(row=row_idx, column=6, value='Có' if fee.is_active else 'Không')
            ws.cell(row=row_idx, column=7, value=limit_label)
            ws.cell(
                row=row_idx,
                column=8,
                value=str(fee.effective_from) if fee.effective_from else '',
            )
            ws.cell(
                row=row_idx,
                column=9,
                value=str(fee.effective_to) if fee.effective_to else '',
            )
            ws.cell(row=row_idx, column=10, value=str(fee.created_at) if fee.created_at else '')
            ws.cell(row=row_idx, column=11, value=str(fee.updated_at) if fee.updated_at else '')

        EXPORTS_DIR.mkdir(exist_ok=True)
        filename = f"revenue_fee_configs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        file_path = str(EXPORTS_DIR / filename)
        wb.save(file_path)

        export_log_repo.create(
            db,
            {
                'user_id': user_id,
                'export_type': 'revenue_fee_configs',
                'file_path': file_path,
                'filters': filters or {'fee_config_ids': fee_config_ids},
                'row_count': len(fees),
            },
        )
        return file_path


export_service = ExportService()
