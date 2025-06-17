"""
Scheduler management module for admin panel.
Handles scheduled tasks, job monitoring, and scheduler statistics.
"""

from fastapi import APIRouter, BackgroundTasks
from .base import *
import scheduler

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

@router.post("/trigger/daily-news", response_class=HTMLResponse)
async def trigger_daily_news(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    """Manually trigger daily news template job"""
    background_tasks.add_task(scheduler.send_daily_news_template)
    return RedirectResponse(url="/admin/scheduler", status_code=302)

@router.post("/trigger/weekly-news", response_class=HTMLResponse)
async def trigger_weekly_news(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    """Manually trigger weekly news template job"""
    background_tasks.add_task(scheduler.send_weekly_news_template)
    return RedirectResponse(url="/admin/scheduler", status_code=302)

@router.post("/trigger/monthly-news", response_class=HTMLResponse)
async def trigger_monthly_news(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    """Manually trigger monthly news template job"""
    background_tasks.add_task(scheduler.send_monthly_news_template)
    return RedirectResponse(url="/admin/scheduler", status_code=302)

@router.post("/trigger/immediate-news", response_class=HTMLResponse)
async def trigger_immediate_news(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    """Manually trigger immediate news template job"""
    background_tasks.add_task(scheduler.send_immediately_news_template)
    return RedirectResponse(url="/admin/scheduler", status_code=302)

@router.post("/trigger/clean-messages", response_class=HTMLResponse)
async def trigger_clean_messages(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    """Manually trigger clean old messages job"""
    background_tasks.add_task(scheduler.clean_old_messages)
    return RedirectResponse(url="/admin/scheduler", status_code=302)

@router.post("/trigger/download-news", response_class=HTMLResponse)
async def trigger_download_news(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    """Manually trigger download news from sources job"""
    background_tasks.add_task(scheduler.download_news_from_sources)
    return RedirectResponse(url="/admin/scheduler", status_code=302)