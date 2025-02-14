from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import Dict, Optional
from datetime import datetime
import logging
from database import get_db
import models

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhook"])

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

def process_incoming_message(message_data: Dict, phone_number: str, db: Session) -> None:
    """Process incoming messages and queue them for handling"""
    try:
        # Log incoming message
        message = models.Message(
            whatsapp_message_id=message_data['id'],
            phone_number=phone_number,
            message_type='incoming',
            message_content=message_data['text']['body'],
            status='received',
            status_timestamp=datetime.fromtimestamp(int(message_data['timestamp']))
        )
        db.add(message)
        db.commit()

        # For now, just log the message
        logger.info(f"Received message from {phone_number}: {message_data['text']['body']}")
    except Exception as e:
        logger.error(f"Error processing incoming message: {str(e)}")
        db.rollback()

def verify_webhook(mode: str, token: str, challenge: str) -> Dict[str, str]:
    """Handle WhatsApp Cloud API webhook verification"""
    if mode == 'subscribe' and token == "SAD":
        logger.info("Webhook verified successfully!")
        return {"challenge": challenge, "status_code": "200"}
    else:
        logger.warning("Webhook verification failed.")
        return {"error": "Forbidden", "status_code": "403"}

@router.get("")
async def verify_webhook_endpoint(
    request: Request
):
    """Handle incoming webhook requests for both official and unofficial API formats"""
    if request.method == 'GET':
        mode = request.query_params.get('hub.mode')
        token = request.query_params.get('hub.verify_token')
        challenge = request.query_params.get('hub.challenge')
        # Ensure INFO log level is set for console logging
        logger.setLevel(logging.INFO)
        logger.info(f"Webhook verification request: {mode}, {token}, {challenge}")

        response = verify_webhook(mode, token, challenge)
        if response.get("status_code") == "403":
            raise HTTPException(status_code=403, detail=response.get("error"))
        return response.get("challenge")

@router.post("")
async def webhook_endpoint(
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
                                    process_incoming_message(message_data, message_data['from'], db)

        return {"status": "success", "message": "Webhook received and being processed"}

    except Exception as e:
        logger.error(f"Error in webhook endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")