import asyncio
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# WINDOWS FIX: Playwright ko chalane ke liye yeh zaroori hai
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from contextlib import asynccontextmanager
from app.core.config import settings
from app.core.logger import setup_logger, logger
from app.database.database import async_engine
from app.database.models import Base

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database tables...")
    try:
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize database tables: {e}")
    yield

def create_app() -> FastAPI:
    # Setup logger
    setup_logger()
    logger.info("Starting AgentFlow Backend...")

    app = FastAPI(
        title=settings.PROJECT_NAME,
        version="0.1.0",
        description="Backend for AI Browser Agent",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan
    )

    # CORS configuration (Allow all for dev)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Changed to * for dev to avoid CORS issues
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Example Health Check Route
    @app.get("/health", tags=["Health"])
    async def health_check():
        return {"status": "ok", "project": settings.PROJECT_NAME}

    # Include routers
    from app.api.router import api_router
    from app.websocket.routes import router as ws_router
    
    # YAHAN /api PREFIX ADD KIYA HAI
    app.include_router(api_router, prefix="/api")
    app.include_router(ws_router)

    return app

app = create_app()

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)