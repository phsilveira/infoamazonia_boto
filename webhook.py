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
from services.handlers import (
    handle_start_state,
    handle_register_state,
    handle_menu_state,
    handle_modify_subscription_state,
    handle_location_state,
    handle_subject_state,
    handle_schedule_state,
    handle_about_state,
    handle_term_info_state,
    handle_article_summary_state,
    handle_news_suggestion_state,
    handle_feedback_state,
    handle_unsubscribe_state,
    handle_monthly_news_response  
)
import os

# Configure logging
logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhook"])

# Initialize ChatGPT service
chatgpt_service = ChatGPTService()

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
    """Process webhook messages asynchronously with improved error handling"""
    try:
        phone_number = data.get('phone_number')
        message = data.get('message')
        current_state = None
        redis_client = request.app.state.redis

        # Check if there's an ongoing processing for this phone number using Redis
        if redis_client:
            is_processing = await redis_client.get(f"processing:{phone_number}")
            if is_processing:
                await send_message(phone_number, "Estamos processando sua solicitação, aguarde", db)
                return {"status": "success", "message": "Processing notification sent"}

            # Mark this phone number as being processed with 5 minute expiry
            await redis_client.setex(f"processing:{phone_number}", 60*10, "1")

        # Get Redis client from app state with proper error handling

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

        # Initialize chatbot and process message with Redis client
        chatbot = ChatBot(db, redis_client)
        if current_state:
            chatbot.set_state(current_state)

        # Process the message using the unified processing function
        new_state = await process_message(phone_number, message, chatbot)

        # Try to update Redis cache with new state, but don't fail if Redis is unavailable
        if redis_client:
            try:
                await redis_client.setex(f"state:{phone_number}", 10*60, new_state)
                logger.debug(f"Updated Redis state for {phone_number}: {new_state}")
            except Exception as e:
                logger.warning(f"Failed to update Redis state: {e}")

        # Send response with transaction handling
        try:
            result = {"status": "success", "message": "Message processed"}
            if result['status'] != 'success':
                raise Exception(result['message'])

            # If everything succeeded, commit the transaction
            try:
                db.commit()
            except Exception as e:
                logger.error(f"Failed to commit transaction: {e}")
                db.rollback()
                raise

            return {"status": "success", "message": "Message processed and sent"}
        except Exception as e:
            db.rollback()
            logger.error(f"Error sending message: {e}")
            raise
    except Exception as e:
        logger.error(f"Error in process_webhook_message: {str(e)}")
        # Ensure the transaction is rolled back in case of any error
        try:
            db.rollback()
        except:
            pass
        return {"status": "error", "message": str(e)}
    finally:
        # Clean up processing state from Redis
        if redis_client:
            await redis_client.delete(f"processing:{phone_number}")


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
                                    # Log incoming message
                                    incoming_message = models.Message(
                                        whatsapp_message_id=message_data['id'],
                                        phone_number=message_data['from'],
                                        message_type='incoming',
                                        message_content=message_data['text']['body'],
                                        status='received'
                                    )
                                    db.add(incoming_message)
                                    db.commit()

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
                                elif message_data['type'] == 'button':
                                    # Handle button response - used for interactive messages
                                    button_payload = message_data['button'].get('payload')
                                    button_text = message_data['button'].get('text')
                                    logger.info(f"Received button response: {button_text} (payload: {button_payload})")
                                    
                                    # Log incoming button message
                                    incoming_message = models.Message(
                                        whatsapp_message_id=message_data['id'],
                                        phone_number=message_data['from'],
                                        message_type='incoming',
                                        message_content=f"Button: {button_text}",
                                        status='received'
                                    )
                                    db.add(incoming_message)
                                    db.commit()
                                    
                                    # Process the button click as a message
                                    webhook_data = {
                                        'phone_number': message_data['from'],
                                        'message': button_payload  # Use the payload for processing
                                    }
                                    background_tasks.add_task(
                                        process_webhook_message,
                                        webhook_data,
                                        db,
                                        request
                                    )
                                elif message_data['type'] == 'interactive':
                                    # Handle interactive message responses (button clicks from the new UI)
                                    interactive_data = message_data.get('interactive', {})
                                    
                                    if interactive_data.get('type') == 'button_reply':
                                        button_reply = interactive_data.get('button_reply', {})
                                        button_id = button_reply.get('id')
                                        button_title = button_reply.get('title')
                                        
                                        logger.info(f"Received interactive button reply: {button_title} (id: {button_id})")
                                        
                                        # Log incoming interactive button message
                                        incoming_message = models.Message(
                                            whatsapp_message_id=message_data['id'],
                                            phone_number=message_data['from'],
                                            message_type='incoming',
                                            message_content=f"Interactive Button: {button_title}",
                                            status='received'
                                        )
                                        db.add(incoming_message)
                                        db.commit()
                                        
                                        # Process the interactive button click as a message
                                        # We'll use the button ID (sim/não) as the message content
                                        webhook_data = {
                                            'phone_number': message_data['from'],
                                            'message': button_id  # Use the button ID for processing
                                        }
                                        background_tasks.add_task(
                                            process_webhook_message,
                                            webhook_data,
                                            db,
                                            request
                                        )
                                    else:
                                        logger.warning(f"Unsupported interactive type: {interactive_data.get('type')}")
                                        await send_message(
                                            message_data['from'],
                                            "Desculpe, no momento só aceitamos botões de resposta.",
                                            db
                                        )
                                else:
                                    await send_message(
                                        message_data['from'],
                                        "Desculpe, no momento só aceitamos mensagens de texto.",
                                        db
                                    )

        return {"status": "success", "message": "Webhook received and being processed"}

    except Exception as e:
        logger.error(f"Error in webhook endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

def handle_message_status(status: Dict, db: Session) -> None:
    """Process and store message status updates"""
    try:
        whatsapp_message_id = status['id']
        message = models.Message(
            whatsapp_message_id=whatsapp_message_id,
            phone_number=status['recipient_id'],
            message_type='outgoing',
            status=status['status'],
            status_timestamp=datetime.fromtimestamp(int(status['timestamp']))
        )

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

async def process_message(phone_number: str, message: str, chatbot: ChatBot) -> str:
    """Process a message and return the new state"""
    try:
        current_state = chatbot.state

        # Map states to their handler functions
        state_handlers = {
            'start': handle_start_state,
            'register': handle_register_state,
            'menu_state': handle_menu_state,
            'modify_subscription_state': handle_modify_subscription_state,
            'get_user_location': handle_location_state,
            'get_user_subject': handle_subject_state,
            'get_user_schedule': handle_schedule_state,
            'about': handle_about_state,
            'get_term_info': handle_term_info_state,
            'feedback_state': handle_feedback_state,
            'get_article_summary': handle_article_summary_state,
            'get_news_suggestion': handle_news_suggestion_state,
            'unsubscribe_state': handle_unsubscribe_state,
            'monthly_news_response': handle_monthly_news_response,  
        }

        # Get the appropriate handler for the current state
        handler = state_handlers.get(current_state)
        if handler:
            if handler == handle_start_state:
                return await handler(chatbot, phone_number)
            elif handler == handle_register_state:
                return await handler(chatbot, phone_number, message)
            elif handler == handle_menu_state:
                return await handler(chatbot, phone_number, message)
            elif handler == handle_about_state:
                return await handler(chatbot, phone_number)
            else:
                return await handler(chatbot, phone_number, message, chatgpt_service)

        # Handle invalid state
        await send_message(phone_number, message_loader.get_message('error.invalid_state'), next(get_db()))
        return chatbot.state

    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        await send_message(
            phone_number,
            message_loader.get_message('error.process_message', error=str(e)),
            next(get_db())
        )
        return 'start'