import os
from sqlalchemy import create_engine, text
from models import Base
from database import get_session, engine
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def reset_database():
    """Reset the database by dropping all tables and recreating them."""
    try:
        # Drop all tables
        Base.metadata.drop_all(bind=engine)
        logger.info("Successfully dropped all tables")
        
        # Recreate all tables
        Base.metadata.create_all(bind=engine)
        logger.info("Successfully recreated all tables")
        
        # Import and run sample data creation if needed
        try:
            from create_sample_data import create_sample_data
            create_sample_data()
            logger.info("Successfully created sample data")
        except ImportError:
            logger.warning("Sample data creation script not found, skipping...")
        except Exception as e:
            logger.error(f"Error creating sample data: {e}")
            
        logger.info("Database reset completed successfully")
        return True
    except Exception as e:
        logger.error(f"Error resetting database: {e}")
        return False

if __name__ == "__main__":
    reset_database()
