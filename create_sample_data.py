from sqlalchemy.orm import Session
from database import SessionLocal, engine
import models
from datetime import datetime

def create_sample_users():
    db = SessionLocal()
    try:
        # Check if we already have users
        existing_users = db.query(models.User).first()
        if not existing_users:
            sample_users = [
                models.User(
                    phone_number="+1234567890",
                    is_active=True,
                    created_at=datetime.utcnow()
                ),
                models.User(
                    phone_number="+9876543210",
                    is_active=True,
                    created_at=datetime.utcnow()
                ),
                models.User(
                    phone_number="+5555555555",
                    is_active=False,
                    created_at=datetime.utcnow()
                )
            ]
            for user in sample_users:
                db.add(user)
            db.commit()
            print("Sample users created successfully")
        else:
            print("Users already exist in the database")
    finally:
        db.close()

if __name__ == "__main__":
    models.Base.metadata.create_all(bind=engine)
    create_sample_users()
