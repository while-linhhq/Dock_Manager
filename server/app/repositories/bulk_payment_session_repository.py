from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.bulk_payment_session import BulkPaymentSession


class BulkPaymentSessionRepository:
    def get_by_reference(self, db: Session, reference_code: str) -> Optional[BulkPaymentSession]:
        return (
            db.query(BulkPaymentSession)
            .filter(BulkPaymentSession.reference_code == reference_code)
            .first()
        )

    def create(
        self,
        db: Session,
        *,
        reference_code: str,
        invoice_ids: List[int],
        expected_total,
        created_by: Optional[int],
    ) -> BulkPaymentSession:
        row = BulkPaymentSession(
            reference_code=reference_code,
            invoice_ids=invoice_ids,
            expected_total=expected_total,
            status='pending',
            created_by=created_by,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def mark_completed(self, db: Session, session: BulkPaymentSession, sepay_txn_id: int) -> BulkPaymentSession:
        session.status = 'completed'
        session.sepay_txn_id = sepay_txn_id
        session.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(session)
        return session


bulk_payment_session_repo = BulkPaymentSessionRepository()
