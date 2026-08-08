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
    from app.websocket.manager import ws_manager
    logger.info("Initializing database tables...")
    try:
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize database tables: {e}")
        
    # Start Redis subscriber for websocket communication
    redis_listener_task = asyncio.create_task(ws_manager.listen_to_redis())
    
    yield
    
    # Clean up Redis subscriber on shutdown
    redis_listener_task.cancel()
    try:
        await redis_listener_task
    except asyncio.CancelledError:
        pass

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

    # CORS configuration
    import json
    origins = ["http://localhost:3000", "https://agentsflow.netlify.app"]
    if hasattr(settings, "CORS_ORIGINS"):
        try:
            if isinstance(settings.CORS_ORIGINS, list):
                origins.extend(settings.CORS_ORIGINS)
            elif isinstance(settings.CORS_ORIGINS, str):
                try:
                    loaded = json.loads(settings.CORS_ORIGINS)
                    if isinstance(loaded, list):
                        origins.extend(loaded)
                    else:
                        origins.append(settings.CORS_ORIGINS)
                except Exception:
                    origins.append(settings.CORS_ORIGINS)
        except Exception:
            pass
            
    # Clean origins
    origins = list(set([o.strip().rstrip("/") for o in origins if o and isinstance(o, str)]))

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
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
    app.include_router(api_router, prefix="/api", tags=["Auth"])
    app.include_router(ws_router)

    return app

app = create_app()

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)