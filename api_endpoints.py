from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db
import models
from datetime import datetime
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/api/article-stats")
async def get_article_stats(request: Request, db: Session = Depends(get_db)):
    """Get article statistics for display in admin panel"""
    try:
        # Get total count
        total_count = db.query(models.Article).count()

        # Get oldest and newest dates
        dates_query = db.query(
            func.min(models.Article.published_date).label('oldest'),
            func.max(models.Article.published_date).label('newest')
        ).first()

        oldest_date = None
        newest_date = None
        
        if dates_query and dates_query.oldest:
            oldest_date = dates_query.oldest.strftime('%Y-%m-%d')
        
        if dates_query and dates_query.newest:
            newest_date = dates_query.newest.strftime('%Y-%m-%d')
        
        logger.info(f"Article stats: {total_count} articles, oldest: {oldest_date}, newest: {newest_date}")
        
        return {
            "success": True,
            "stats": {
                "total_count": total_count,
                "oldest_date": oldest_date,
                "newest_date": newest_date
            }
        }
    except Exception as e:
        logger.error(f"Error fetching article stats: {e}")
        return {
            "success": False,
            "error": str(e)
        }