from sqlalchemy.orm import Session
from database import SessionLocal, engine
import models
from datetime import datetime

def create_sample_news_sources():
    db = SessionLocal()
    try:
        # Check if we already have news sources
        existing_sources = db.query(models.NewsSource).first()
        if not existing_sources:
            sample_sources = [
                models.NewsSource(
                    name="Amazon Conservation News",
                    url="https://www.amazonconservation.org/news/",
                    is_active=True,
                    created_at=datetime.utcnow()
                ),
                models.NewsSource(
                    name="Rainforest Alliance",
                    url="https://www.rainforest-alliance.org/news/",
                    is_active=True,
                    created_at=datetime.utcnow()
                ),
                models.NewsSource(
                    name="Global Forest Watch",
                    url="https://www.globalforestwatch.org/blog/",
                    is_active=True,
                    created_at=datetime.utcnow()
                )
            ]
            for source in sample_sources:
                db.add(source)
            db.commit()
            print("Sample news sources created successfully")
        else:
            print("News sources already exist in the database")
    finally:
        db.close()

if __name__ == "__main__":
    models.Base.metadata.create_all(bind=engine)
    create_sample_news_sources()
