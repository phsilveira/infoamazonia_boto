from fastapi import APIRouter, Request, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Dict
from datetime import datetime
import logging
from database import get_db
import models
from config import settings
from services.chatbot import ChatBot
from services.whatsapp import send_message
from services.chatgpt import ChatGPTService
from utils.message_loader import message_loader
import os

# Configure logging
logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhook"])

# Initialize ChatGPT service
chatgpt_service = ChatGPTService(os.environ.get('OPENAI_API_KEY'))

@router.get("")
async def verify_webhook_endpoint(request: Request):
    """Handle incoming webhook requests for both official and unofficial API formats"""
    mode = request.query_params.get('hub.mode')
    token = request.query_params.get('hub.verify_token')
    challenge = request.query_params.get('hub.challenge')

    # Ensure INFO log level is set for console logging
    logger.setLevel(logging.INFO)
    logger.info(f"Webhook verification request: {mode}, {token}, {challenge}")

    # Validate all required parameters are present
    if not all([mode, token, challenge]):
        logger.warning("Missing required parameters")
        raise HTTPException(status_code=400, detail="Missing parameters")

    # Verify the token and mode
    if mode != 'subscribe' or token != settings.WEBHOOK_VERIFY_TOKEN:
        logger.warning("Webhook verification failed")
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        # Convert challenge to integer and return
        challenge_int = int(challenge)
        logger.info("Webhook verified successfully!")
        return challenge_int
    except ValueError:
        logger.error("Invalid challenge value")
        raise HTTPException(status_code=400, detail="Invalid challenge value")

async def process_webhook_message(data: Dict, db: Session, request: Request) -> Dict:
    """Process webhook messages asynchronously"""
    try:
        phone_number = data.get('phone_number')
        message = data.get('message')
        current_state = None

        if not phone_number or not message:
            logger.error("Missing required fields in webhook data")
            return {"status": "error", "message": "Missing required fields"}

        # Get Redis client from app state with proper error handling
        redis_client = getattr(request.app.state, 'redis', None)
        if redis_client:
            try:
                # Get current state from Redis
                current_state = await redis_client.get(f"state:{phone_number}")
                if current_state:
                    logger.debug(f"Retrieved state for {phone_number}: {current_state}")
            except Exception as e:
                logger.warning(f"Redis operation failed, continuing without state: {e}")
        else:
            logger.warning("Redis client not available, continuing without state")

        # Initialize chatbot and process message
        chatbot = ChatBot(db)
        if current_state:
            chatbot.set_state(current_state)

        # Process the message using the unified processing function
        response_message, new_state = await process_message(phone_number, message, chatbot)

        # Try to update Redis cache with new state, but don't fail if Redis is unavailable
        if redis_client:
            try:
                await redis_client.setex(f"state:{phone_number}", 300, new_state)
                logger.debug(f"Updated Redis state for {phone_number}: {new_state}")
            except Exception as e:
                logger.warning(f"Failed to update Redis state: {e}")

        # Send response
        result = await send_message(phone_number, response_message, db)
        if result['status'] != 'success':
            raise Exception(result['message'])

        return {"status": "success", "message": "Message processed and sent"}

    except Exception as e:
        logger.error(f"Error in process_webhook_message: {str(e)}")
        return {"status": "error", "message": str(e)}

@router.post("", response_model=None)
async def webhook_endpoint(
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db)
):
    """Handle incoming webhook requests"""
    try:
        data = await request.json()
        logger.debug(f"Received webhook data: {data}")

        if not data:
            raise HTTPException(status_code=400, detail="No data provided")

        # Handle WhatsApp Cloud API format
        if data.get('object') == 'whatsapp_business_account':
            for entry in data['entry']:
                for change in entry.get('changes', []):
                    if change.get('field') == 'messages':
                        value = change['value']

                        # Handle message status updates
                        if 'statuses' in value:
                            for status in value['statuses']:
                                handle_message_status(status, db)

                        # Handle incoming messages
                        if 'messages' in value:
                            for message_data in value['messages']:
                                if message_data['type'] == 'text':
                                    webhook_data = {
                                        'phone_number': message_data['from'],
                                        'message': message_data['text']['body']
                                    }
                                    background_tasks.add_task(
                                        process_webhook_message,
                                        webhook_data,
                                        db,
                                        request
                                    )

        return {"status": "success", "message": "Webhook received and being processed"}

    except Exception as e:
        logger.error(f"Error in webhook endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

def handle_message_status(status: Dict, db: Session) -> None:
    """Process and store message status updates"""
    try:
        whatsapp_message_id = status['id']
        message = db.query(models.Message).filter_by(whatsapp_message_id=whatsapp_message_id).first()

        if not message:
            message = models.Message(
                whatsapp_message_id=whatsapp_message_id,
                phone_number=status['recipient_id'],
                message_type='outgoing',
                status=status['status'],
                status_timestamp=datetime.fromtimestamp(int(status['timestamp']))
            )
        else:
            message.status = status['status']
            message.status_timestamp = datetime.fromtimestamp(int(status['timestamp']))

        # Handle failed messages
        if status['status'] == 'failed' and 'errors' in status:
            error = status['errors'][0]
            message.error_code = error.get('code')
            message.error_title = error.get('title')
            message.error_message = error.get('message')

        db.add(message)
        db.commit()
        logger.info(f"Updated message status: {status['status']} for {whatsapp_message_id}")
    except Exception as e:
        logger.error(f"Error processing message status: {str(e)}")
        db.rollback()

async def process_message(phone_number: str, message: str, chatbot: ChatBot) -> tuple[str, str]:
    """Process a message and return the response and new state"""
    try:
        current_state = chatbot.state

        # Map states to their handler functions
        state_handlers = {
            'start': handle_start_state,
            'register': handle_register_state,
            'menu_state': handle_menu_state,
            'get_user_location': handle_location_state,
            'get_user_subject': handle_subject_state,
            'get_user_schedule': handle_schedule_state,
            'about': handle_about_state,
        }

        # Get the appropriate handler for the current state
        handler = state_handlers.get(current_state)
        if handler:
            if handler == handle_start_state:
                return await handler(chatbot, phone_number)
            elif handler == handle_register_state:
                return await handler(chatbot, phone_number, message)
            elif handler == handle_menu_state:
                return await handler(chatbot, message)
            elif handler == handle_about_state:
                return await handler(chatbot)
            else:
                return await handler(chatbot, phone_number, message)

        return message_loader.get_message('error.invalid_state'), chatbot.state

    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        return message_loader.get_message('error.process_message', error=str(e)), 'start'

async def handle_start_state(chatbot: ChatBot, phone_number: str) -> tuple[str, str]:
    return message_loader.get_message('start'), 'menu_state'

async def handle_register_state(chatbot: ChatBot, phone_number: str, message: str) -> tuple[str, str]:
    #Process registration logic here
    return message_loader.get_message('registration_success'), 'menu_state'

async def handle_menu_state(chatbot: ChatBot, message: str) -> tuple[str, str]:
    #Process menu logic here
    return message_loader.get_message('menu'), 'menu_state'

async def handle_location_state(chatbot: ChatBot, phone_number: str, message: str) -> tuple[str, str]:
    #Process location logic here
    return message_loader.get_message('location_received'), 'menu_state'

async def handle_subject_state(chatbot: ChatBot, phone_number: str, message: str) -> tuple[str, str]:
    #Process subject logic here
    return message_loader.get_message('subject_received'), 'menu_state'

async def handle_schedule_state(chatbot: ChatBot, phone_number: str, message: str) -> tuple[str, str]:
    #Process schedule logic here
    return message_loader.get_message('schedule_received'), 'menu_state'

async def handle_about_state(chatbot: ChatBot) -> tuple[str, str]:
    return message_loader.get_message('about'), 'menu_state'