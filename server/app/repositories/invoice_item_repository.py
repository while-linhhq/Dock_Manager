from sqlalchemy.orm import Session
from app.models.invoice_item import InvoiceItem
from typing import List, Optional


class InvoiceItemRepository:
    def get(self, db: Session, item_id: int) -> Optional[InvoiceItem]:
        return db.query(InvoiceItem).filter(InvoiceItem.id == item_id).first()

    def get_by_invoice(self, db: Session, invoice_id: int) -> List[InvoiceItem]:
        return db.query(InvoiceItem).filter(InvoiceItem.invoice_id == invoice_id).all()

    def create(self, db: Session, data: dict) -> InvoiceItem:
        db_obj = InvoiceItem(**data)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def create_bulk(self, db: Session, items: List[dict]) -> List[InvoiceItem]:
        db_objs = [InvoiceItem(**item) for item in items]
        db.add_all(db_objs)
        db.flush()
        for obj in db_objs:
            db.refresh(obj)
        return db_objs

    def delete(self, db: Session, item_id: int) -> bool:
        db_obj = self.get(db, item_id)
        if not db_obj:
            return False
        db.delete(db_obj)
        db.commit()
        return True


invoice_item_repo = InvoiceItemRepository()
