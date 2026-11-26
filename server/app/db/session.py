from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings

def build_connect_args(database_url: str) -> dict:
    """Giữ options PostgreSQL hiện có và đặt timezone UTC ưu tiên cuối."""
    url = make_url(database_url)
    if url.get_backend_name() != 'postgresql':
        return {}
    options = url.query.get('options', '')
    if not isinstance(options, str):
        raise ValueError('DATABASE_URL chỉ được chứa một tham số options')
    return {'options': f'{options} -c timezone=UTC' if options else '-c timezone=UTC'}


# pool_pre_ping: discard stale connections (PG restart, idle timeout).
# pool_recycle: refresh connections before server-side idle limits.
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=1800,
    connect_args=build_connect_args(settings.DATABASE_URL),
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
