"""
Metrics and analytics module for admin panel.
Handles system metrics, statistics, and performance monitoring.
"""

from fastapi import APIRouter
from .base import *

router = APIRouter()

@router.get("", response_class=HTMLResponse)
async def get_metrics(
    request: Request,
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    # Get overall system metrics
    total_users = db.query(models.User).count()
    active_users = db.query(models.User).filter(models.User.is_active == True).count()
    total_articles = db.query(models.Article).count()
    total_news_sources = db.query(models.NewsSource).count()
    active_news_sources = db.query(models.NewsSource).filter(models.NewsSource.is_active == True).count()
    
    # Get recent activity metrics
    from datetime import datetime, timedelta
    last_week = datetime.now() - timedelta(days=7)
    
    recent_users = db.query(models.User).filter(models.User.created_at >= last_week).count()
    recent_articles = db.query(models.Article).filter(models.Article.created_at >= last_week).count()
    
    # Get interaction metrics if available
    total_interactions = 0
    recent_interactions = 0
    try:
        total_interactions = db.query(models.Interaction).count()
        recent_interactions = db.query(models.Interaction).filter(models.Interaction.created_at >= last_week).count()
    except:
        # Handle case where Interaction model might not exist
        pass
    
    # Get message metrics if available
    total_messages = 0
    recent_messages = 0
    try:
        total_messages = db.query(models.UserMessage).count()
        recent_messages = db.query(models.UserMessage).filter(models.UserMessage.created_at >= last_week).count()
    except:
        # Handle case where UserMessage model might not exist
        pass
    
    metrics = {
        "users": {
            "total": total_users,
            "active": active_users,
            "recent": recent_users
        },
        "articles": {
            "total": total_articles,
            "recent": recent_articles
        },
        "news_sources": {
            "total": total_news_sources,
            "active": active_news_sources
        },
        "interactions": {
            "total": total_interactions,
            "recent": recent_interactions
        },
        "messages": {
            "total": total_messages,
            "recent": recent_messages
        }
    }
    
    return templates.TemplateResponse(
        "admin/metrics.html",
        {"request": request, "metrics": metrics}
    )