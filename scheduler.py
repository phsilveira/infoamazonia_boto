from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
import logging
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
import models
from database import SessionLocal
from pytz import timezone
import asyncio
from services.whatsapp import send_message
from typing import List, Dict
from config import get_redis, settings

# Configure timezone
SP_TIMEZONE = timezone('America/Sao_Paulo')

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create scheduler with Brazil/Sao Paulo timezone
scheduler = AsyncIOScheduler(timezone=SP_TIMEZONE)

async def send_news_template(schedule_type: str, days_back: int = 30, use_ingestion_api: bool = False) -> None:
    """Base function for sending news templates to users based on their schedule"""
    db = None
    scheduler_run = None
    redis_client = None

    try:
        # Initialize Redis client
        redis_client = await get_redis()

        # Start scheduler run record
        db = SessionLocal()
        scheduler_run = models.SchedulerRun(
            task_name=f'send_{schedule_type}_news_template',
            status='running'
        )
        db.add(scheduler_run)
        db.commit()

        # Get active users with specified schedule
        active_users = db.query(models.User).filter(
            models.User.is_active == True,
            models.User.schedule == schedule_type
        ).all()

        # Get news via direct database query for recently ingested articles
        if use_ingestion_api:
            from sqlalchemy import desc, and_
            
            # For immediate messages, get only the most recent articles (last 24 hours)
            recent_time = datetime.now() - timedelta(hours=24)
            
            logger.info(f"Fetching recently ingested articles since {recent_time.strftime('%Y-%m-%d %H:%M')}")
            
            # Use direct database query for recently ingested articles
            articles_query = db.query(models.Article).filter(
                and_(
                    models.Article.created_at >= recent_time,
                    models.Article.is_published == True,
                    models.Article.summary_content.isnot(None)
                )
            ).order_by(desc(models.Article.created_at)).limit(10)
            
            # Fetch all matching articles
            db_articles = articles_query.all()
            
            # Transform database articles to the expected format
            articles = []
            for article in db_articles:
                articles.append({
                    'id': str(article.id),
                    'title': article.title,
                    'news_source': article.news_source or 'Unknown',
                    'url': article.url,
                    'published_date': article.published_date.strftime('%Y-%m-%d') if article.published_date else None,
                    'summary_content': article.summary_content
                })

        if not active_users:
            logger.info(f"No active users with {schedule_type} schedule found")
            scheduler_run.status = 'success'
            scheduler_run.end_time = datetime.utcnow()
            scheduler_run.affected_users = 0
            db.commit()
            return
        
        if not use_ingestion_api:
            # Use direct database query for articles
            from sqlalchemy import desc, and_
            import unicodedata
            
            # Calculate the date range
            date_to = datetime.now()
            date_from = (datetime.now() - timedelta(days=days_back))
            
            logger.info(f"Fetching articles from {date_from.strftime('%Y-%m-%d')} to {date_to.strftime('%Y-%m-%d')}")
            
            # Direct database query instead of HTTP request
            articles_query = db.query(models.Article).filter(
                and_(
                    models.Article.published_date >= date_from,
                    models.Article.published_date <= date_to,
                    models.Article.is_published == True,
                    models.Article.summary_content.isnot(None)
                )
            ).order_by(desc(models.Article.published_date))
            
            # Fetch all matching articles
            db_articles = articles_query.all()
            
            # Transform database articles to the expected format
            articles = []
            for article in db_articles:
                articles.append({
                    'id': str(article.id),
                    'title': article.title,
                    'news_source': article.news_source or 'Unknown',
                    'url': article.url,
                    'published_date': article.published_date.strftime('%Y-%m-%d') if article.published_date else None,
                    'summary_content': article.summary_content
                })

        if not articles:
            logger.info(f"No articles found in the response")
            scheduler_run.status = 'success'
            scheduler_run.end_time = datetime.utcnow()
            scheduler_run.affected_users = 0
            db.commit()
            return

        # Determine template name based on article count
        max_articles = 3
        articles = articles[:max_articles]

        template_parameters = []
        for article in articles:
            
            template_parameters.append({
                "type": "text",
                "text": f"{article['title']} - {article['news_source']}"
            })
            template_parameters.append({
                "type": "text",
                "text": article['url']
            })

        if len(articles) == 3:
            template_name = "three_articles"
        elif len(articles) == 2:
            template_name = "two_articles"
        else:
            template_name = "one_article"

        sent_count = 0
        # Send template to each active user
        for user in active_users:
            try:
                template_content = {
                    "name": template_name,
                    "language": "pt_BR",
                    "components": [
                        {
                            "type": "body",
                            "parameters": template_parameters
                        }
                    ]
                }
                result = await send_message(
                    to=user.phone_number,
                    content=template_content,
                    db=db,
                    message_type="template"
                )

                if result["status"] == "success":
                    # Set the user's chatbot state to monthly_news_response in Redis
                    if redis_client:
                        try:
                            await redis_client.setex(
                                f"state:{user.phone_number}",
                                2*60*60,  # 2 hours to expiry
                                "monthly_news_response"
                            )
                            logger.info(f"Set chatbot state to monthly_news_response for user {user.phone_number}")
                        except Exception as redis_error:
                            logger.error(f"Failed to set Redis state for user {user.phone_number}: {str(redis_error)}")

                    sent_count += 1
                    logger.info(f"Successfully sent {schedule_type} news template to {user.phone_number}")
                else:
                    logger.error(f"Failed to send template to {user.phone_number}: {result['message']}")
            except Exception as e:
                logger.error(f"Error sending template to {user.phone_number}: {str(e)}")

        # Update scheduler run record
        scheduler_run.status = 'success'
        scheduler_run.end_time = datetime.utcnow()
        scheduler_run.affected_users = sent_count
        db.commit()

        logger.info(f"{schedule_type.capitalize()} news template sent to {sent_count} users")

    except Exception as e:
        error_msg = f"Error in {schedule_type} news template sending: {str(e)}"
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

async def send_immediately_news_template():
    """Send news template to active users with immediate schedule using the ingestion API"""
    await send_news_template('immediately', days_back=1, use_ingestion_api=True)

async def send_daily_news_template():
    """Send daily news template to active users with daily schedule"""
    await send_news_template('daily', days_back=1)

async def send_weekly_news_template():
    """Send weekly news template to active users with weekly schedule"""
    await send_news_template('weekly', days_back=7)

async def send_monthly_news_template():
    """Send monthly news template to active users with monthly schedule"""
    await send_news_template('monthly', days_back=30)

async def update_user_status():
    """Check for users who haven't sent any messages in the last 30 days and mark them as inactive"""
    db = None
    scheduler_run = None

    try:
        # Initialize Redis client
        redis_client = await get_redis()
        
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

            # If no recent messages, mark user as inactive and send template
            if not latest_message:
                user.is_active = False
                updated_count += 1
                logger.info(f"Marking user {user.phone_number} as inactive due to 30+ days of inactivity")

                # Send unsubscribe template
                template_content = {
                    "name": "unsubscribe",
                    "language": "pt_BR"
                }

                try:
                    result = await send_message(
                        to=user.phone_number,
                        content=template_content,
                        db=db,
                        message_type="template"
                    )
                    if result["status"] == "success":
                        logger.info(f"Successfully sent unsubscribe template to {user.phone_number}")
                        if redis_client:
                            try:
                                await redis_client.setex(
                                    f"state:{user.phone_number}",
                                    6*60*60,  # 6 hours to expiry
                                    "unsubscribe_state"
                                )
                                logger.info(f"Set chatbot state to monthly_news_response for user {user.phone_number}")
                            except Exception as redis_error:
                                logger.error(f"Failed to set Redis state for user {user.phone_number}: {str(redis_error)}")

                    else:
                        logger.error(f"Failed to send unsubscribe template to {user.phone_number}: {result['message']}")
                except Exception as e:
                    logger.error(f"Error sending unsubscribe template to {user.phone_number}: {str(e)}")

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

async def clean_old_messages():
    """Remove messages older than 30 days to maintain database size"""
    db = None
    scheduler_run = None

    try:
        db = SessionLocal()
        scheduler_run = models.SchedulerRun(
            task_name='clean_old_messages',
            status='running'
        )
        db.add(scheduler_run)
        db.commit()

        # Calculate cutoff date (30 days ago)
        cutoff_date = datetime.utcnow() - timedelta(days=30)

        # Delete old messages
        deleted_count = db.query(models.Message).filter(
            models.Message.created_at < cutoff_date
        ).delete()

        db.commit()
        logger.info(f"Deleted {deleted_count} messages older than 30 days")

        # Update scheduler run record
        scheduler_run.status = 'success'
        scheduler_run.end_time = datetime.utcnow()
        scheduler_run.affected_users = deleted_count
        db.commit()

    except Exception as e:
        error_msg = f"Error cleaning old messages: {str(e)}"
        logger.error(error_msg)

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
        # scheduler.add_job(
        #     update_user_status,
        #     trigger=CronTrigger(hour=9, minute=0, timezone=SP_TIMEZONE),
        #     id='update_user_status',
        #     replace_existing=True,
        #     misfire_grace_time=300  # 5 minutes grace time
        # )

        # Daily news at 9:00 AM SP time
        scheduler.add_job(
            send_daily_news_template,
            trigger=CronTrigger(hour=9, minute=0, timezone=SP_TIMEZONE),
            id='send_daily_news_template',
            replace_existing=True,
            misfire_grace_time=300
        )

        # Weekly news at 9:00 AM SP time every Friday
        scheduler.add_job(
            send_weekly_news_template,
            trigger=CronTrigger(day_of_week='fri', hour=9, minute=0, timezone=SP_TIMEZONE),
            id='send_weekly_news_template',
            replace_existing=True,
            misfire_grace_time=300
        )

        # Monthly news at 9:00 AM SP time on the last day of each month
        scheduler.add_job(
            send_monthly_news_template,
            trigger=CronTrigger(day='last', hour=9, minute=0, timezone=SP_TIMEZONE),
            id='send_monthly_news_template',
            replace_existing=True,
            misfire_grace_time=300
        )

        # Immediate news every 3 hours
        scheduler.add_job(
            send_immediately_news_template,
            trigger=CronTrigger(hour='*/3', minute=0, timezone=SP_TIMEZONE),
            id='send_immediately_news_template',
            replace_existing=True,
            misfire_grace_time=300
        )

        # Add clean_old_messages job to run daily at 3 AM
        scheduler.add_job(
            clean_old_messages,
            trigger=CronTrigger(hour=3, minute=0, timezone=SP_TIMEZONE),
            id='clean_old_messages',
            replace_existing=True,
            misfire_grace_time=300
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