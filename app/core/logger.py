import sys
from loguru import logger
from app.core.config import settings

def setup_logger():
    # Remove default logger
    logger.remove()
    
    # Add a custom sink that writes to stdout
    logger.add(
        sys.stdout,
        enqueue=True,
        backtrace=True,
        level=settings.LOG_LEVEL,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )
    
    logger.info("Logger configured successfully.")

# Expose a ready-to-use configured logger
__all__ = ["logger", "setup_logger"]
