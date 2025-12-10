from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
from urllib.parse import urlparse
from config import settings


SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL or "postgresql://postgres:postgres@localhost/infoamazonia"

parsed_url = urlparse(SQLALCHEMY_DATABASE_URL)

connect_args = {}
if parsed_url.scheme.startswith("postgres"):
    connect_args = {
        "connect_timeout": 10,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5
    }

# Configure engine based on database type
# if ENV_MODE == "production":
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
# else:
#     # SQLite configuration - note: check_same_thread needed for SQLite
#     engine = create_engine(
#         SQLALCHEMY_DATABASE_URL,
#         connect_args={"check_same_thread": False}
#     )

# Configure session with expire_on_commit=False to prevent detached instance errors
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)

Base = declarative_base()

def init_db():
    db = SessionLocal()
    try:
        # Create the pgvector extension
        db.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        db.commit()
        print("pgvector extension created successfully")
    except Exception as e:
        db.rollback()
        print(f"Failed to create extension: {str(e)}")
    finally:
        db.close()

def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()