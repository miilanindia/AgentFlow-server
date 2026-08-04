from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# Async Engine setup (for FastAPI async routes)
async_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
    pool_pre_ping=True
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine, 
    class_=AsyncSession,
    autocommit=False, 
    autoflush=False,
    expire_on_commit=False
)

# Sync engine setup (mostly for Alembic if not using async alembic environment, but Alembic can be configured for async)
# If settings.DATABASE_URL uses `postgresql+asyncpg`, we need to replace it for sync engine
sync_url = settings.DATABASE_URL.replace("+asyncpg", "") if settings.DATABASE_URL else ""

sync_engine = create_engine(
    sync_url,
    echo=settings.DEBUG,
    future=True,
    pool_pre_ping=True
) if sync_url else None

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=sync_engine
) if sync_engine else None
