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
    USE_OFFICIAL_API: bool = os.getenv("USE_OFFICIAL_API", "True") == "True"

    # Unofficial API Configuration
    EXTERNAL_SERVICE_URL: str = os.getenv("EXTERNAL_SERVICE_URL", "")
    UNOFFICIAL_CLIENT_TOKEN: str = os.getenv("UNOFFICIAL_CLIENT_TOKEN", "")

    # OpenAI Configuration
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    
    # Azure OpenAI Configuration
    USE_AZURE_OPENAI: bool = os.getenv("USE_AZURE_OPENAI", "False") == "True"
    AZURE_OPENAI_API_KEY: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    AZURE_ENDPOINT_URL: str = os.getenv("ENDPOINT_URL", "https://boto.openai.azure.com/")
    AZURE_DEPLOYMENT_NAME: str = os.getenv("DEPLOYMENT_NAME", "gpt-4o-mini")
    AZURE_API_VERSION: str = os.getenv("AZURE_API_VERSION", "2024-05-01-preview")

    # Google Maps
    GOOGLEMAPS_API_KEY: str = os.getenv("GOOGLEMAPS_API_KEY", "")

    # Redis Configuration
    REDIS_HOST: str = os.getenv("REDIS_HOST", "0.0.0.0")  
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD")

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # Mailgun Email Settings
    MAILGUN_API_KEY: str = os.getenv("MAILGUN_API_KEY", "")
    MAILGUN_DOMAIN: str = os.getenv("MAILGUN_DOMAIN", "")
    
    # Articles API
    ARTICLES_API_URL: str = os.getenv("ARTICLES_API_URL", "https://aa109676-f2b5-40ce-9a8b-b7d95b3a219e-00-30gb0h9bugxba.spock.replit.dev/api/v1/articles/list")
    SEARCH_BASE_URL: str = os.getenv("SEARCH_BASE_URL", "https://aa109676-f2b5-40ce-9a8b-b7d95b3a219e-00-30gb0h9bugxba.spock.replit.dev")

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
    """
    Create and return a Redis client instance.
    Includes retry logic and better error handling.
    """
    try:
        redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD,
            decode_responses=True,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30
        )
        # Test the connection
        await redis_client.ping()
        logger.info("Successfully connected to Redis")
        return redis_client
    except redis.ConnectionError as e:
        logger.error(f"Failed to connect to Redis: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error creating Redis client: {e}")
        return None