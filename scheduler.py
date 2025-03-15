from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
import logging
from sqlalchemy.orm import Session
import models
from database import SessionLocal
from pytz import timezone
import asyncio

# Configure timezone
SP_TIMEZONE = timezone('America/Sao_Paulo')

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create scheduler with Brazil/Sao Paulo timezone
scheduler = AsyncIOScheduler(timezone=SP_TIMEZONE)

async def update_user_status():
    """Check for users who haven't sent any messages in the last 30 days and mark them as inactive"""
    db = None
    scheduler_run = None

    try:
        # Start scheduler run record
        db = SessionLocal()
        scheduler_run = models.SchedulerRun(
            task_name='update_user_status',
            status='running'
        )
        db.add(scheduler_run)
        db.commit()

        # Get inactive users
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        active_users = db.query(models.User).filter(models.User.is_active == True).all()

        updated_count = 0

        for user in active_users:
            # Check if user has any incoming messages in the last 30 days
            latest_message = db.query(models.Message).filter(
                models.Message.phone_number == user.phone_number,
                models.Message.message_type == 'incoming',
                models.Message.created_at >= thirty_days_ago
            ).first()

            # If no recent messages, mark user as inactive
            if not latest_message:
                user.is_active = False
                updated_count += 1
                logger.info(f"Marking user {user.phone_number} as inactive due to 30+ days of inactivity")

        # Commit changes
        if updated_count > 0:
            db.commit()
            logger.info(f"Updated {updated_count} users to inactive status")

        # Update scheduler run record
        scheduler_run.status = 'success'
        scheduler_run.end_time = datetime.utcnow()
        scheduler_run.affected_users = updated_count
        db.commit()

    except Exception as e:
        error_msg = f"Error updating user status: {str(e)}"
        logger.error(error_msg)

        # Update scheduler run record with error
        if scheduler_run and db:
            scheduler_run.status = 'failed'
            scheduler_run.end_time = datetime.utcnow()
            scheduler_run.error_message = error_msg
            db.commit()
    finally:
        if db:
            db.close()

def start_scheduler():
    """Start the scheduler with the user status update task"""
    logger.info("Initializing scheduler...")

    try:
        # Schedule regular user status updates - daily at 11:15 AM
        scheduler.add_job(
            update_user_status,
            trigger=CronTrigger(hour=11, minute=15),
            id='update_user_status',
            replace_existing=True,
            misfire_grace_time=300  # 5 minutes grace time
        )

        # Start the scheduler
        scheduler.start()
        logger.info("Scheduler started successfully")

    except Exception as e:
        logger.error(f"Error starting scheduler: {str(e)}")

def get_scheduler_status():
    """Get the current status of scheduled tasks"""
    return {
        "active_jobs": [{"id": job.id, "next_run": job.next_run_time} for job in scheduler.get_jobs()]
    }