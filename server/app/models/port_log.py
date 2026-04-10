from sqlalchemy import Column, Integer, String, Float, DateTime, JSON
from app.db.session import Base
import datetime

class PortLog(Base):
    __tablename__ = "port_logs"

    id = Column(Integer, primary_key=True, index=True)
    seq = Column(Integer) # Sequence number for the day
    logged_at = Column(DateTime, default=datetime.datetime.utcnow)
    track_id = Column(String, index=True)
    voted_ship_id = Column(String, index=True)
    first_seen_at = Column(DateTime)
    last_seen_at = Column(DateTime)
    confidence = Column(Float)
    ocr_attempts = Column(Integer)
    vote_summary = Column(JSON)
    
    # Optional: schema version for tracking log format changes
    schema_version = Column(Integer, default=3)
