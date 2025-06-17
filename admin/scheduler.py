"""
Scheduler management module for admin panel.
Handles scheduled tasks, job monitoring, and scheduler statistics.
"""

from fastapi import APIRouter
from .base import *

router = APIRouter()

@router.get("", response_class=HTMLResponse)
async def scheduler_runs_page(
    request: Request,
    skip: int = 0,
    limit: int = 100,
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    # Get scheduler runs if available
    try:
        scheduler_runs = db.query(models.SchedulerRun).order_by(
            desc(models.SchedulerRun.start_time)
        ).offset(skip).limit(limit).all()
    except Exception as e:
        # Handle case where SchedulerRun model might not exist
        scheduler_runs = []
        print(f"Error fetching scheduler runs: {e}")
    
    # Get scheduled messages if available
    try:
        scheduled_messages = db.query(models.ScheduledMessage).order_by(
            desc(models.ScheduledMessage.created_at)
        ).limit(10).all()
    except Exception as e:
        # Handle case where ScheduledMessage model might not exist
        scheduled_messages = []
        print(f"Error fetching scheduled messages: {e}")
    
    return templates.TemplateResponse(
        "admin/scheduler.html",
        {
            "request": request,
            "scheduler_runs": scheduler_runs,
            "scheduled_messages": scheduled_messages
        }
    )