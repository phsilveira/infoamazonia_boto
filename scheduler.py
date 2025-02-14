from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from pytz import timezone
import logging
from datetime import datetime
from sqlalchemy.orm import Session
import models

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create scheduler with Brazil/Sao Paulo timezone
scheduler = AsyncIOScheduler(timezone=timezone('America/Sao_Paulo'))

async def send_whatsapp_message(db: Session, message_id: int):
    """Mock function to simulate sending WhatsApp message"""
    scheduled_message = db.query(models.ScheduledMessage).filter(models.ScheduledMessage.id == message_id).first()
    if scheduled_message:
        template = scheduled_message.template
        logger.info(f"[MOCK] Sending WhatsApp message at {datetime.now()}:")
        logger.info(f"Template: {template.name}")
        logger.info(f"Content: {template.content}")
        logger.info(f"Target Groups: {scheduled_message.target_groups}")
        logger.info(f"Personalization Data: {scheduled_message.personalization_data}")
        
        # Update message status
        scheduled_message.status = "sent"
        db.commit()

def schedule_message(db: Session, message_id: int, scheduled_time: datetime):
    """Schedule a message to be sent at the specified time"""
    scheduler.add_job(
        send_whatsapp_message,
        trigger=DateTrigger(
            run_date=scheduled_time,
            timezone=timezone('America/Sao_Paulo')
        ),
        args=[db, message_id]
    )
    logger.info(f"Message {message_id} scheduled for {scheduled_time}")

def start_scheduler():
    """Start the scheduler"""
    scheduler.start()
    logger.info("Scheduler started with Brazil/Sao Paulo timezone")
