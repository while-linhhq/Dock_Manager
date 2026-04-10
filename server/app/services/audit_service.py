from typing import Any, Optional
from sqlalchemy.orm import Session

from app.repositories.audit_log_repository import audit_log_repo


class AuditService:
    def log(
        self,
        db: Session,
        action: str,
        entity_type: str,
        entity_id: Optional[int] = None,
        user_id: Optional[int] = None,
        details: Optional[dict[str, Any]] = None,
        ip_address: Optional[str] = None,
    ) -> None:
        audit_log_repo.create(db, {
            'user_id': user_id,
            'action': action,
            'entity_type': entity_type,
            'entity_id': entity_id,
            'details': details,
            'ip_address': ip_address,
        })


audit_service = AuditService()
