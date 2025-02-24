from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone
import logging
from datetime import datetime
from sqlalchemy.orm import Session
import models
import httpx
from config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create scheduler with Brazil/Sao Paulo timezone
scheduler = AsyncIOScheduler(timezone=timezone('America/Sao_Paulo'))

async def send_whatsapp_message(db: Session, message_id: int):
    """Send WhatsApp template message to specified users"""
    try:
        scheduled_message = db.query(models.ScheduledMessage).filter(models.ScheduledMessage.id == message_id).first()
        if not scheduled_message:
            logger.error(f"Scheduled message {message_id} not found")
            return

        # Get the template
        template = scheduled_message.template
        if not template:
            logger.error(f"Template not found for message {message_id}")
            return

        # Get target users based on schedule preference
        target_group = scheduled_message.target_groups.get('target_group', 'all')
        users_query = db.query(models.User).filter(models.User.is_active == True)

        if target_group != 'all':
            users_query = users_query.filter(models.User.schedule == target_group)

        users = users_query.all()

        # WhatsApp API configuration
        whatsapp_api_url = f"https://graph.facebook.com/v17.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }

        # Send message to each user
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
                        json=payload
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
                        logger.info(f"Message sent to {user.phone_number}")
                    else:
                        logger.error(f"Failed to send message to {user.phone_number}: {response_data}")

                except Exception as e:
                    logger.error(f"Error sending message to {user.phone_number}: {str(e)}")
                    continue

        # Update scheduled message status
        scheduled_message.status = "sent"
        db.commit()
        logger.info(f"Completed sending scheduled message {message_id}")

    except Exception as e:
        logger.error(f"Error processing scheduled message {message_id}: {str(e)}")

def schedule_message(db: Session, message_id: int, schedule_type: str, scheduled_date: str = None):
    """Schedule a message based on the schedule type"""
    sp_tz = timezone('America/Sao_Paulo')

    if schedule_type == "just_in_time" and scheduled_date:
        # For just in time, use the provided date at 9 AM SP time
        schedule_time = sp_tz.localize(datetime.strptime(f"{scheduled_date} 09:00", "%Y-%m-%d %H:%M"))
        trigger = DateTrigger(run_date=schedule_time)
    else:
        # For recurring schedules, use CronTrigger
        trigger_kwargs = {
            "hour": 9,
            "minute": 0,
            "timezone": sp_tz
        }

        if schedule_type == "daily":
            # Run every day at 9 AM SP
            pass
        elif schedule_type == "weekly":
            # Run every Monday at 9 AM SP
            trigger_kwargs["day_of_week"] = "mon"
        elif schedule_type == "monthly":
            # Run on the 1st of every month at 9 AM SP
            trigger_kwargs["day"] = "1"
        else:
            logger.error(f"Invalid schedule type: {schedule_type}")
            return

        trigger = CronTrigger(**trigger_kwargs)

    # Add the job to the scheduler
    scheduler.add_job(
        send_whatsapp_message,
        trigger=trigger,
        args=[db, message_id]
    )
    logger.info(f"Message {message_id} scheduled with type {schedule_type}")

def start_scheduler():
    """Start the scheduler"""
    scheduler.start()
    logger.info("Scheduler started with Brazil/Sao Paulo timezone")