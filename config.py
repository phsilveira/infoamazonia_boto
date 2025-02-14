from pydantic_settings import BaseSettings
import os
from typing import Optional
from functools import lru_cache
import redis.asyncio as redis
import logging

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    """Application settings."""
    # Environment
    ENV: str = os.getenv("ENV", "development")
    DEBUG: bool = os.getenv("DEBUG", "True") == "True"

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./app.db")

    # API Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-here")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

    # Webhook Configuration
    WEBHOOK_VERIFY_TOKEN: str = os.getenv("WEBHOOK_VERIFY_TOKEN", "SAD")

    # WhatsApp API Configuration
    API_URL: str = os.getenv("API_URL", "https://graph.facebook.com/v12.0/")
    API_TOKEN: str = os.getenv("API_TOKEN", "")
    NUMBER_ID: str = os.getenv("NUMBER_ID", "")
    USE_OFFICIAL_API: bool = os.getenv("USE_OFFICIAL_API", "False") == "True"

    # Unofficial API Configuration
    EXTERNAL_SERVICE_URL: str = os.getenv("EXTERNAL_SERVICE_URL", "")
    UNOFFICIAL_CLIENT_TOKEN: str = os.getenv("UNOFFICIAL_CLIENT_TOKEN", "")

    # OpenAI Configuration
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # Redis Configuration
    REDIS_HOST: str = os.getenv("REDIS_HOST", "0.0.0.0")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    class Config:
        case_sensitive = True
        env_file = ".env"

@lru_cache()
def get_settings():
    """Get settings based on environment."""
    env = os.getenv("ENV", "development")
    return Settings(_env_file=f".env.{env}")

# Create settings instance
settings = get_settings()

# Create Redis instance
async def get_redis():
    try:
        redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True
        )
        return redis_client
    except Exception as e:
        logger.error(f"Failed to create Redis client: {e}")
        return None