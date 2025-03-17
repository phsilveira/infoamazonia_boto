from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
import logging
from sqlalchemy.orm import Session
import models
from database import SessionLocal
from pytz import timezone
import asyncio
from services.whatsapp import send_message
import httpx
from typing import List, Dict

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

async def send_daily_template():
    """Send hello_world template message to all active users"""
    db = None
    scheduler_run = None

    try:
        # Start scheduler run record
        db = SessionLocal()
        scheduler_run = models.SchedulerRun(
            task_name='send_daily_template',
            status='running'
        )
        db.add(scheduler_run)
        db.commit()

        # Get all active users
        active_users = db.query(models.User).filter(models.User.is_active == True).all()
        sent_count = 0

        # Template message configuration
        template_content = {
            "name": "hello_world",
            "language": "en_US"
        }

        # Send template to each active user
        for user in active_users:
            try:
                result = await send_message(
                    to=user.phone_number,
                    content=template_content,
                    db=db,
                    message_type="template"
                )
                if result["status"] == "success":
                    sent_count += 1
                    logger.info(f"Successfully sent template to {user.phone_number}")
                else:
                    logger.error(f"Failed to send template to {user.phone_number}: {result['message']}")
            except Exception as e:
                logger.error(f"Error sending template to {user.phone_number}: {str(e)}")

        # Update scheduler run record
        scheduler_run.status = 'success'
        scheduler_run.end_time = datetime.utcnow()
        scheduler_run.affected_users = sent_count
        db.commit()

        logger.info(f"Daily template message sent to {sent_count} users")

    except Exception as e:
        error_msg = f"Error in daily template sending: {str(e)}"
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

async def send_monthly_news_template():
    """Send monthly news template to active users with monthly schedule"""
    db = None
    scheduler_run = None

    try:
        # Start scheduler run record
        db = SessionLocal()
        scheduler_run = models.SchedulerRun(
            task_name='send_monthly_news_template',
            status='running'
        )
        db.add(scheduler_run)
        db.commit()

        # Get active users with monthly schedule
        active_users = db.query(models.User).filter(
            models.User.is_active == True,
            models.User.schedule == 'monthly'
        ).all()

        if not active_users:
            logger.info("No active users with monthly schedule found")
            scheduler_run.status = 'success'
            scheduler_run.end_time = datetime.utcnow()
            scheduler_run.affected_users = 0
            db.commit()
            return

        # Get last 30 days news
        date_to = datetime.now().strftime('%Y-%m-%d')
        date_from = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

        headers = {
            'accept': 'application/json'
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f'https://aa109676-f2b5-40ce-9a8b-b7d95b3a219e-00-30gb0h9bugxba.spock.replit.dev/api/v1/articles/list',
                params={'date_from': date_from, 'date_to': date_to},
                headers=headers
            )
            news_data = response.json()

        if not news_data.get('articles'):
            logger.error("No articles found in the response")
            raise Exception("No articles found in the API response")

        # Get first 3 article titles
        articles = news_data['articles'][:3]
        article_titles = [article['title'] for article in articles]

        sent_count = 0
        # Send template to each active user
        for user in active_users:
            try:
                template_content = {
                    "name": "articles_summary",
                    "language": "pt_BR",
                    "components": [
                      {
                        "type": "body",
                          "parameters": [
                              {"type": "text", "text": article_titles[0]},
                              {"type": "text", "text": article_titles[1]},
                              {"type": "text", "text": article_titles[2]}
                          ]
                      }
                    ]

                }

                print(template_content)

                result = await send_message(
                    to=user.phone_number,
                    content=template_content,
                    db=db,
                    message_type="template"
                )

                if result["status"] == "success":
                    sent_count += 1
                    logger.info(f"Successfully sent monthly news template to {user.phone_number}")
                else:
                    logger.error(f"Failed to send template to {user.phone_number}: {result['message']}")
            except Exception as e:
                logger.error(f"Error sending template to {user.phone_number}: {str(e)}")

        # Update scheduler run record
        scheduler_run.status = 'success'
        scheduler_run.end_time = datetime.utcnow()
        scheduler_run.affected_users = sent_count
        db.commit()

        logger.info(f"Monthly news template sent to {sent_count} users")

    except Exception as e:
        error_msg = f"Error in monthly news template sending: {str(e)}"
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

async def start_scheduler():
    """Start the scheduler with all tasks"""
    logger.info("Initializing scheduler...")

    try:
        scheduler.add_job(
            update_user_status,
            trigger=CronTrigger(minute='*/15'),  # For testing: run every minute
            id='update_user_status',
            replace_existing=True,
            misfire_grace_time=300  # 5 minutes grace time
        )

        scheduler.add_job(
            send_daily_template,
            trigger=CronTrigger(hour=9, minute=20, timezone=SP_TIMEZONE),
            id='send_daily_template',
            replace_existing=True,
            misfire_grace_time=300  # 5 minutes grace time
        )

        scheduler.add_job(
            send_monthly_news_template,
            trigger=CronTrigger(day=1, hour=10, minute=0, timezone=SP_TIMEZONE),  # Run at 10 AM on the 1st day of each month
            id='send_monthly_news_template',
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