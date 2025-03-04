
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone
import logging
from datetime import datetime, timedelta
import asyncio
from sqlalchemy.orm import Session
import models
import httpx
from config import settings
from database import SessionLocal

# Configure timezone
SP_TIMEZONE = timezone('America/Sao_Paulo')

# Configure logging with custom formatter to include timezone
class TimezoneFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        # Convert time to Brazil/Sao Paulo timezone
        dt = datetime.fromtimestamp(record.created).astimezone(SP_TIMEZONE)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.strftime("%Y-%m-%d %H:%M:%S %Z")

# Setup logging
formatter = TimezoneFormatter(
    fmt='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S %Z'
)
handler = logging.StreamHandler()
handler.setFormatter(formatter)

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(handler)

# Create scheduler with Brazil/Sao Paulo timezone
scheduler = AsyncIOScheduler(timezone=SP_TIMEZONE)

# Task registry to track all scheduled tasks
TASK_REGISTRY = {
    'update_user_status': {
        'description': 'Update inactive users daily',
        'schedule': 'daily at 11:15 AM',
        'last_run': None,
        'status': 'pending'
    },
    'send_scheduled_messages': {
        'description': 'Send scheduled WhatsApp messages',
        'schedule': 'as needed',
        'last_run': None,
        'status': 'pending'
    }
}

def log_with_timestamp(message, level="info"):
    """Helper function to log with current timezone timestamp"""
    current_time = datetime.now(SP_TIMEZONE)
    formatted_message = f"[{current_time}] {message}"
    
    if level.lower() == "error":
        logger.error(formatted_message)
    elif level.lower() == "warning":
        logger.warning(formatted_message)
    else:
        logger.info(formatted_message)

async def update_user_status():
    """
    Check for users who haven't sent any messages in the last 30 days
    and mark them as inactive
    """
    log_with_timestamp("Starting user status update check...")
    db = None
    
    try:
        # Update task registry
        TASK_REGISTRY['update_user_status']['last_run'] = datetime.now(SP_TIMEZONE)
        TASK_REGISTRY['update_user_status']['status'] = 'running'
        
        # Get a database session
        db = SessionLocal()
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        
        # Get all active users
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
                log_with_timestamp(f"Marking user {user.phone_number} as inactive due to 30+ days of inactivity")
        
        # Commit changes
        if updated_count > 0:
            db.commit()
            log_with_timestamp(f"Updated {updated_count} users to inactive status")
        else:
            log_with_timestamp("No inactive users found")
        
        # Update task status
        TASK_REGISTRY['update_user_status']['status'] = 'completed'
            
    except Exception as e:
        error_msg = f"Error updating user status: {str(e)}"
        log_with_timestamp(error_msg, "error")
        if db:
            db.rollback()
        # Update task status
        TASK_REGISTRY['update_user_status']['status'] = 'failed'
    finally:
        if db:
            db.close()

async def send_whatsapp_message(db: Session, message_id: int):
    """Send WhatsApp template message to specified users"""
    log_with_timestamp(f"Processing scheduled message {message_id}")
    
    try:
        # Update task registry
        TASK_REGISTRY['send_scheduled_messages']['last_run'] = datetime.now(SP_TIMEZONE)
        TASK_REGISTRY['send_scheduled_messages']['status'] = 'running'
        
        scheduled_message = db.query(models.ScheduledMessage).filter(models.ScheduledMessage.id == message_id).first()
        if not scheduled_message:
            log_with_timestamp(f"Scheduled message {message_id} not found", "error")
            return

        # Get the template
        template = scheduled_message.template
        if not template:
            log_with_timestamp(f"Template not found for message {message_id}", "error")
            return

        # Get target users based on schedule preference
        target_group = scheduled_message.target_groups.get('target_group', 'all')
        users_query = db.query(models.User).filter(models.User.is_active == True)

        if target_group != 'all':
            users_query = users_query.filter(models.User.schedule == target_group)

        users = users_query.all()
        log_with_timestamp(f"Found {len(users)} target users for message {message_id}")

        # WhatsApp API configuration
        whatsapp_api_url = f"https://graph.facebook.com/v17.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }

        # Send message to each user
        success_count = 0
        failed_count = 0
        
        async with httpx.AsyncClient() as client:
            for user in users:
                try:
                    payload = {
                        "messaging_product": "whatsapp",
                        "to": user.phone_number,
                        "type": "template",
                        "template": {
                            "name": template.name,
                            "language": {
                                "code": "en_US"
                            }
                        }
                    }

                    response = await client.post(
                        whatsapp_api_url,
                        headers=headers,
                        json=payload,
                        timeout=10.0  # Add timeout
                    )
                    response_data = response.json()

                    if response.status_code == 200:
                        # Log successful message
                        message = models.Message(
                            whatsapp_message_id=response_data.get('messages', [{}])[0].get('id', 'unknown'),
                            phone_number=user.phone_number,
                            message_type='outgoing',
                            message_content=f"Template: {template.name}",
                            status='sent'
                        )
                        db.add(message)
                        db.commit()
                        success_count += 1
                    else:
                        failed_count += 1
                        log_with_timestamp(f"Failed to send message to {user.phone_number}: {response_data}", "error")

                except Exception as e:
                    failed_count += 1
                    log_with_timestamp(f"Error sending message to {user.phone_number}: {str(e)}", "error")
                    continue

        # Update scheduled message status
        scheduled_message.status = "sent"
        db.commit()
        log_with_timestamp(f"Completed sending scheduled message {message_id}. Success: {success_count}, Failed: {failed_count}")
        
        # Update task status
        TASK_REGISTRY['send_scheduled_messages']['status'] = 'completed'

    except Exception as e:
        log_with_timestamp(f"Error processing scheduled message {message_id}: {str(e)}", "error")
        # Update task status
        TASK_REGISTRY['send_scheduled_messages']['status'] = 'failed'

def schedule_message(db: Session, message_id: int, schedule_type: str, scheduled_date: str = None):
    """Schedule a message based on the schedule type"""
    log_with_timestamp(f"Scheduling message {message_id} with type {schedule_type}")
    
    try:
        if schedule_type == "just_in_time" and scheduled_date:
            # For just in time, use the provided date at 9 AM SP time
            schedule_time = SP_TIMEZONE.localize(datetime.strptime(f"{scheduled_date} 09:00", "%Y-%m-%d %H:%M"))
            trigger = DateTrigger(run_date=schedule_time)
            job_id = f"send_message_{message_id}_{scheduled_date}"
        else:
            # For recurring schedules, use CronTrigger
            trigger_kwargs = {
                "hour": 9,
                "minute": 0,
                "timezone": SP_TIMEZONE
            }

            if schedule_type == "daily":
                # Run every day at 9 AM SP
                job_id = f"send_message_{message_id}_daily"
            elif schedule_type == "weekly":
                # Run every Monday at 9 AM SP
                trigger_kwargs["day_of_week"] = "mon"
                job_id = f"send_message_{message_id}_weekly"
            elif schedule_type == "monthly":
                # Run on the 1st of every month at 9 AM SP
                trigger_kwargs["day"] = "1"
                job_id = f"send_message_{message_id}_monthly"
            else:
                log_with_timestamp(f"Invalid schedule type: {schedule_type}", "error")
                return

            trigger = CronTrigger(**trigger_kwargs)

        # Add the job to the scheduler
        scheduler.add_job(
            send_whatsapp_message,
            trigger=trigger,
            args=[db, message_id],
            id=job_id,
            replace_existing=True,
            misfire_grace_time=3600  # Allow 1 hour grace time for misfires
        )
        log_with_timestamp(f"Message {message_id} scheduled successfully with ID {job_id}")
        
    except Exception as e:
        log_with_timestamp(f"Error scheduling message {message_id}: {str(e)}", "error")

async def check_scheduler_health():
    """Check the health of all scheduled tasks"""
    log_with_timestamp("Performing scheduler health check")
    
    try:
        # Get all scheduled jobs
        jobs = scheduler.get_jobs()
        job_ids = [job.id for job in jobs]
        
        log_with_timestamp(f"Found {len(jobs)} active scheduled jobs: {', '.join(job_ids)}")
        
        # Check if update_user_status is scheduled
        if 'update_user_status' not in job_ids:
            log_with_timestamp("WARNING: User status update job is not scheduled!", "warning")
            # Reschedule it
            schedule_user_status_update()
            log_with_timestamp("Re-scheduled user status update job", "info")
            
        # Log task registry status
        for task_id, task_info in TASK_REGISTRY.items():
            last_run = task_info['last_run'].strftime('%Y-%m-%d %H:%M:%S') if task_info['last_run'] else 'Never'
            log_with_timestamp(f"Task '{task_id}' - Status: {task_info['status']}, Last run: {last_run}")
            
    except Exception as e:
        log_with_timestamp(f"Error checking scheduler health: {str(e)}", "error")

def schedule_user_status_update():
    """Schedule the user status update task"""
    # Add job to update user status daily at 11:15 AM
    scheduler.add_job(
        update_user_status,
        trigger=CronTrigger(hour=11, minute=15),
        id='update_user_status',
        replace_existing=True,
        misfire_grace_time=300  # Allow 5 minutes of misfire grace time
    )
    log_with_timestamp("User status update scheduled for 11:15 AM daily")

def schedule_test_run():
    """Schedule a test run of user status update shortly after startup"""
    # Add job to run shortly after startup for testing
    scheduler.add_job(
        update_user_status,
        trigger=DateTrigger(run_date=datetime.now(SP_TIMEZONE) + timedelta(seconds=30)),
        id='update_user_status_test',
        replace_existing=True
    )
    log_with_timestamp("Test run scheduled for 30 seconds from now")

def schedule_health_check():
    """Schedule periodic health checks for the scheduler"""
    # Run health check every 12 hours
    scheduler.add_job(
        check_scheduler_health,
        trigger=CronTrigger(hour='*/12'),
        id='scheduler_health_check',
        replace_existing=True
    )
    log_with_timestamp("Scheduler health check scheduled to run every 12 hours")

def start_scheduler():
    """Start the scheduler and ensure all tasks are properly registered"""
    log_with_timestamp("Initializing scheduler...")
    
    try:
        # Schedule regular user status updates
        schedule_user_status_update()
        
        # Schedule a test run that will execute shortly after startup
        schedule_test_run()
        
        # Schedule periodic health checks
        schedule_health_check()
        
        # Start the scheduler
        scheduler.start()
        log_with_timestamp("Scheduler started successfully with Brazil/Sao Paulo timezone")
        
        # Run an immediate health check
        asyncio.create_task(check_scheduler_health())
        
    except Exception as e:
        log_with_timestamp(f"Error starting scheduler: {str(e)}", "error")

def get_scheduler_status():
    """Get the current status of all scheduled tasks"""
    jobs = scheduler.get_jobs()
    return {
        "active_jobs": [{"id": job.id, "next_run": job.next_run_time} for job in jobs],
        "task_registry": TASK_REGISTRY
    }
