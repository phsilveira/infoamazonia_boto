"""
Base configuration and shared dependencies for admin modules.
Contains common imports, utilities, and configurations used across all admin modules.
"""

from fastapi import Depends, HTTPException, status, Request, Form, Body
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, Response, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_, func, select, text, case
from datetime import datetime, timezone
from typing import List, Optional
import json
import httpx
import logging
import csv
import io

# Import project modules
import models
import schemas
from database import get_db
from auth import get_current_admin, get_password_hash
from config import settings
from services.chatgpt import ChatGPTService
from utils.prompt_loader import prompt_loader
from cache_utils import invalidate_dashboard_caches, get_cache, set_cache

# Configure logging
logger = logging.getLogger(__name__)

# Create templates instance
templates = Jinja2Templates(directory="templates")

# Initialize services
chatgpt_service = ChatGPTService()

# Common dependencies
def get_current_admin_dependency():
    """Dependency for getting current authenticated admin user."""
    return Depends(get_current_admin)

def get_db_dependency():
    """Dependency for getting database session."""
    return Depends(get_db)

# Common utility functions
async def handle_database_error(e: Exception, operation: str):
    """Common error handling for database operations."""
    logger.error(f"Database error during {operation}: {str(e)}")
    raise HTTPException(
        status_code=500,
        detail=f"Database error during {operation}: {str(e)}"
    )

async def invalidate_caches_and_log(request: Request, entity_type: str, entity_id: str = None):
    """Common cache invalidation with logging."""
    await invalidate_dashboard_caches(request)
    if entity_id:
        logger.info(f"Cache invalidated after {entity_type} operation on ID: {entity_id}")
    else:
        logger.info(f"Cache invalidated after {entity_type} operation")

def apply_pagination(query, skip: int = 0, limit: int = 100):
    """Apply pagination to a query."""
    return query.offset(skip).limit(limit)

def apply_search_filter(query, model_field, search_term: str):
    """Apply search filter to a query field."""
    if search_term:
        return query.filter(model_field.ilike(f"%{search_term}%"))
    return query

def apply_status_filter(query, model_field, status: str):
    """Apply status filter to a query."""
    if status:
        is_active = status == "active"
        return query.filter(model_field == is_active)
    return query