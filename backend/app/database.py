from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_engine(
    settings.database_dsn(),
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=3,
    max_overflow=2,
    pool_timeout=15,
    pool_use_lifo=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session]:
    with SessionLocal() as session:
        yield session
