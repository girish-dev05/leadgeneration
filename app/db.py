from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import get_settings

settings = get_settings()

connect_args = {}
if settings.db_url.startswith('mysql'):
    connect_args = {
        "connect_timeout": 5,
        "read_timeout": 10,
        "write_timeout": 10,
    }
elif settings.db_url.startswith('postgresql'):
    connect_args = {
        "connect_timeout": 5,
    }

engine = create_engine(
    settings.db_url,
    pool_pre_ping=True,
    connect_args=connect_args,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
