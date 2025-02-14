from pydantic_settings import BaseSettings
import os
from typing import Optional
from functools import lru_cache

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
    
    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    class Config:
        case_sensitive = True
        env_file = ".env"

class DevSettings(Settings):
    """Development-specific settings."""
    class Config:
        env_file = ".env.development"

class ProdSettings(Settings):
    """Production-specific settings."""
    DEBUG: bool = False
    LOG_LEVEL: str = "WARNING"
    
    class Config:
        env_file = ".env.production"

@lru_cache()
def get_settings():
    """Get settings based on environment."""
    env = os.getenv("ENV", "development")
    if env == "production":
        return ProdSettings()
    return DevSettings()

# Create settings instance
settings = get_settings()
