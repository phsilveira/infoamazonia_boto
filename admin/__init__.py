"""
Admin module for managing various administrative functions.
This module provides a refactored approach to admin functionality,
breaking down the monolithic admin.py into focused, manageable modules.
"""

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from .base import *
import httpx
from .users import router as users_router
from .news_sources import router as news_sources_router
from .messages import router as messages_router
from .interactions import router as interactions_router
from .articles import router as articles_router
from .admin_users import router as admin_users_router
from .metrics import router as metrics_router
from .scheduler import router as scheduler_router

# Create main admin router
router = APIRouter(prefix="/admin", tags=["admin"])

# Include all sub-routers
router.include_router(users_router, prefix="/users", tags=["users"])
router.include_router(news_sources_router, prefix="/news-sources", tags=["news-sources"])
router.include_router(messages_router, prefix="/messages", tags=["messages"])
router.include_router(interactions_router, prefix="/interactions", tags=["interactions"])
router.include_router(articles_router, prefix="/articles", tags=["articles"])
router.include_router(admin_users_router, prefix="/admin-users", tags=["admin-users"])
router.include_router(metrics_router, prefix="/metrics", tags=["metrics"])
router.include_router(scheduler_router, prefix="/scheduler", tags=["scheduler"])

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