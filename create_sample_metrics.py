from sqlalchemy.orm import Session
from database import SessionLocal, engine
import models
from datetime import datetime, timedelta
import random

def create_sample_metrics():
    db = SessionLocal()
    try:
        # Check if we already have metrics
        existing_metrics = db.query(models.Metrics).first()
        if not existing_metrics:
            # Create metrics for the last 7 days
            for i in range(7):
                date = datetime.utcnow() - timedelta(days=i)
                metric = models.Metrics(
                    date=date,
                    total_users=random.randint(1000, 2000),
                    active_users=random.randint(500, 1000),
                    messages_sent=random.randint(5000, 10000),
                    messages_received=random.randint(2000, 5000),
                    click_through_rate=random.uniform(0.1, 0.5)
                )
                db.add(metric)
            db.commit()
            print("Sample metrics created successfully")
        else:
            print("Metrics already exist in the database")
    finally:
        db.close()

if __name__ == "__main__":
    models.Base.metadata.create_all(bind=engine)
    create_sample_metrics()
