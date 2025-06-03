"""
Admin module for managing various administrative functions.
This module provides a refactored approach to admin functionality,
breaking down the monolithic admin.py into focused, manageable modules.
"""

from fastapi import APIRouter
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