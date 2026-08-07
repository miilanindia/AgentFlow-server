from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "AgentFlow Backend"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    
    # Database Configuration
    DATABASE_URL: str = "sqlite+aiosqlite:///./agentflow.db"
    
    # CORS Configuration
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]
    
    # Redis Configuration
    REDIS_URL: str = "redis://localhost:6379/0"

     # JWT Configuration  ← YE NAYA ADD KARNA HAI
    JWT_SECRET: str = "agentflow_super_secret_key_123!"
    JWT_ALGORITHM: str = "HS256"
    
    # API Keys (Yeh add hona zaroori tha)
    GOOGLE_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    
    # Agent & Token Limits
    MAX_TOOL_ITERATIONS: int = 4
    MAX_HISTORY_MESSAGES: int = 6
    MAX_PAGE_TEXT_CHARS: int = 2000
    MAX_SEARCH_RESULTS: int = 5
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

settings = Settings()