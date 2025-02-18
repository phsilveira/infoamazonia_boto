from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from sqlalchemy.pool import QueuePool
from urllib.parse import urlparse

# Get environment mode
ENV_MODE = os.environ.get("ENV_MODE", "development")

# Set database URL based on environment
if ENV_MODE == "production":
    SQLALCHEMY_DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost/infoamazonia")
else:
    # Use SQLite for development
    SQLALCHEMY_DATABASE_URL = "sqlite:///./dev.db"

# Configure engine based on database type
if ENV_MODE == "production":
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        poolclass=QueuePool,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": 10,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5
        }
    )
else:
    # SQLite configuration - note: check_same_thread needed for SQLite
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False}
    )

# Configure session with expire_on_commit=False to prevent detached instance errors
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()