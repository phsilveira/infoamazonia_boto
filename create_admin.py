from sqlalchemy.orm import Session
from database import SessionLocal, engine
import models
from auth import get_password_hash

def create_initial_admin():
    db = SessionLocal()
    try:
        # Check if admin already exists
        admin = db.query(models.Admin).filter(models.Admin.username == "admin").first()
        if not admin:
            admin = models.Admin(
                username="admin",
                email="admin@example.com",
                hashed_password=get_password_hash("admin"),
                is_active=True,
                role="admin"
            )
            db.add(admin)
            db.commit()
            print("Admin user created successfully")
        else:
            print("Admin user already exists")
    finally:
        db.close()

if __name__ == "__main__":
    models.Base.metadata.create_all(bind=engine)
    create_initial_admin()
