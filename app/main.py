from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.core.config import settings
from app.core.logger import setup_logger, logger

def create_app() -> FastAPI:
    # Setup logger
    setup_logger()
    logger.info("Starting AgentFlow Backend...")

    app = FastAPI(
        title=settings.PROJECT_NAME,
        version="0.1.0",
        description="Backend for AI Browser Agent",
        docs_url="/docs",
        redoc_url="/redoc"
    )

    # CORS configuration
    if settings.CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.CORS_ORIGINS,
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
    app.include_router(api_router, prefix="/api")
    app.include_router(ws_router)

    return app

app = create_app()

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
