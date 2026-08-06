from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# Normalize Database URL for Async Engine
raw_url = settings.DATABASE_URL or "sqlite+aiosqlite:///./agentflow.db"
async_url = raw_url

if async_url.startswith("postgresql://"):
    async_url = async_url.replace("postgresql://", "postgresql+asyncpg://", 1)

if "asyncpg" in async_url and "sslmode=" in async_url:
    async_url = async_url.replace("sslmode=require", "ssl=require").replace("sslmode=prefer", "ssl=prefer").replace("sslmode=disable", "ssl=disable")

# Async Engine setup (for FastAPI async routes)
async_engine = create_async_engine(
    async_url,
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

# Sync engine setup (mostly for Alembic)
sync_url = raw_url.replace("+asyncpg", "").replace("ssl=require", "sslmode=require") if raw_url else ""

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
