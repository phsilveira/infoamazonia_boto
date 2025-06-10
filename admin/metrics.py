"""
Metrics and analytics module for admin panel.
Handles system metrics, statistics, and performance monitoring.
"""

from fastapi import APIRouter
from .base import *
import httpx

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
        total_interactions = db.query(models.UserInteraction).count()
        recent_interactions = db.query(models.UserInteraction).filter(models.UserInteraction.created_at >= last_week).count()
    except:
        # Handle case where Interaction model might not exist
        pass
    
    # Get message metrics if available
    total_messages = 0
    recent_messages = 0
    try:
        total_messages = db.query(models.Message).count()
        recent_messages = db.query(models.Message).filter(models.Message.created_at >= last_week).count()
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

@router.get("/ctr-stats", response_class=HTMLResponse)
async def ctr_stats_page(
    request: Request,
    current_admin: models.Admin = get_current_admin_dependency()
):
    """Display detailed click-through rate statistics"""
    try:
        # Fetch CTR stats from the API endpoint
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{settings.SEARCH_BASE_URL}/api/v1/analytics/ctr-stats")
            response.raise_for_status()
            ctr_data = response.json()
            
        return templates.TemplateResponse(
            "admin/ctr-stats.html",
            {"request": request, "ctr_data": ctr_data}
        )
    except Exception as e:
        logger.error(f"Error fetching CTR stats for page: {str(e)}")
        # Instead of using a separate error template, we'll use the main template
        # with error data that can display a message
        dummy_data = {
            "totals": {
                "total_urls": 0,
                "total_impressions": 0,
                "total_clicks": 0,
                "overall_ctr": 0
            },
            "stats": []
        }
        return templates.TemplateResponse(
            "admin/ctr-stats.html",
            {
                "request": request, 
                "ctr_data": dummy_data,
                "error": f"Failed to fetch CTR statistics: {str(e)}"
            }
        )