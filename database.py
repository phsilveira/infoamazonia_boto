from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import SQLAlchemyError
import os
import logging
from urllib.parse import urlparse
import time
from contextlib import contextmanager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get environment mode
ENV_MODE = os.environ.get("ENV_MODE", "development")

# Set database URL based on environment
if ENV_MODE == "production":
    DATABASE_URL = os.environ.get("DATABASE_URL")
    if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URL = DATABASE_URL
else:
    # Use SQLite for development
    SQLALCHEMY_DATABASE_URL = "sqlite:///./dev.db"

# Production database configuration
POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", "5"))
MAX_OVERFLOW = int(os.environ.get("DB_MAX_OVERFLOW", "10"))
POOL_TIMEOUT = int(os.environ.get("DB_POOL_TIMEOUT", "30"))
POOL_RECYCLE = int(os.environ.get("DB_POOL_RECYCLE", "1800"))  # 30 minutes
MAX_RETRIES = int(os.environ.get("DB_MAX_RETRIES", "3"))
RETRY_DELAY = int(os.environ.get("DB_RETRY_DELAY", "2"))

def create_db_engine(url, is_production=False):
    """Create database engine with appropriate configuration."""
    try:
        if is_production:
            # Production PostgreSQL configuration
            engine = create_engine(
                url,
                poolclass=QueuePool,
                pool_size=POOL_SIZE,
                max_overflow=MAX_OVERFLOW,
                pool_timeout=POOL_TIMEOUT,
                pool_recycle=POOL_RECYCLE,
                pool_pre_ping=True,
                connect_args={
                    "connect_timeout": 10,
                    "keepalives": 1,
                    "keepalives_idle": 30,
                    "keepalives_interval": 10,
                    "keepalives_count": 5,
                    "sslmode": "require" if url and "localhost" not in url else "prefer"
                }
            )
        else:
            # Development SQLite configuration
            engine = create_engine(
                url,
                connect_args={"check_same_thread": False}
            )

        # Test connection
        engine.connect()
        logger.info(f"Successfully connected to {'PostgreSQL' if is_production else 'SQLite'} database")
        return engine
    except Exception as e:
        logger.error(f"Error creating database engine: {str(e)}")
        raise

def get_engine():
    """Get database engine with retry logic."""
    retry_count = 0
    while retry_count < MAX_RETRIES:
        try:
            return create_db_engine(SQLALCHEMY_DATABASE_URL, ENV_MODE == "production")
        except Exception as e:
            retry_count += 1
            if retry_count == MAX_RETRIES:
                logger.error(f"Failed to connect to database after {MAX_RETRIES} attempts")
                raise
            logger.warning(f"Database connection attempt {retry_count} failed. Retrying in {RETRY_DELAY} seconds...")
            time.sleep(RETRY_DELAY * retry_count)  # Exponential backoff

# Create engine
engine = get_engine()

# Configure session with expire_on_commit=False to prevent detached instance errors
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False
)

Base = declarative_base()

@contextmanager
def get_db():
    """Database session context manager with proper error handling."""
    db = SessionLocal()
    try:
        yield db
    except SQLAlchemyError as e:
        logger.error(f"Database error: {str(e)}")
        db.rollback()
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()