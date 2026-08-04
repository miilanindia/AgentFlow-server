from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "AgentFlow Backend"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    
    # Database Configuration
    # Example: postgresql+asyncpg://user:password@localhost:5432/dbname
    DATABASE_URL: str
    
    # CORS Configuration
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

settings = Settings()
