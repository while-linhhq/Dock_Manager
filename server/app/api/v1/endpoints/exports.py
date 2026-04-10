from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.deps import get_current_user
from app.services.export_service import export_service

router = APIRouter()


@router.get('/port-logs')
def export_port_logs(
    log_date: Optional[date] = None,
    ship_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    file_path = export_service.export_port_logs_excel(
        db,
        log_date=log_date,
        ship_id=ship_id,
        user_id=current_user.id,
    )
    return FileResponse(
        path=file_path,
        filename=file_path.split('/')[-1].split('\\')[-1],
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
