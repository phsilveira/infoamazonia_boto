import os
import sys
from sqlalchemy.orm import Session
from database import SessionLocal
import models
import auth
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_superadmin(username, email, password):
    """Create a superadmin user or update an existing admin to superadmin"""
    db = SessionLocal()
    try:
        # First, check if user exists
        existing_admin = db.query(models.Admin).filter(
            (models.Admin.username == username) | (models.Admin.email == email)
        ).first()
        
        if existing_admin:
            # If admin exists, update role to superadmin
            logger.info(f"Updating existing admin {existing_admin.username} to superadmin role")
            existing_admin.role = "superadmin"
            db.commit()
            logger.info(f"Admin {existing_admin.username} updated to superadmin successfully")
            return existing_admin
        else:
            # Create new superadmin
            logger.info(f"Creating new superadmin user: {username}")
            hashed_password = auth.get_password_hash(password)
            new_admin = models.Admin(
                username=username,
                email=email,
                hashed_password=hashed_password,
                role="superadmin",
                is_active=True
            )
            db.add(new_admin)
            db.commit()
            db.refresh(new_admin)
            logger.info(f"New superadmin {username} created successfully")
            return new_admin
    except Exception as e:
        logger.error(f"Error creating/updating superadmin: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) != 4:
        logger.error("Usage: python create_superadmin.py <username> <email> <password>")
        sys.exit(1)
        
    username = sys.argv[1]
    email = sys.argv[2]
    password = sys.argv[3]
    
    try:
        admin = create_superadmin(username, email, password)
        logger.info(f"Superadmin operation completed for {admin.username}")
    except Exception as e:
        logger.error(f"Failed to create/update superadmin: {e}")
        sys.exit(1)