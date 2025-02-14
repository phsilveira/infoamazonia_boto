import httpx
import logging
from datetime import datetime
from typing import Dict
from fastapi import Depends
from sqlalchemy.orm import Session
from database import get_db
import models
from config import settings

logger = logging.getLogger(__name__)

async def send_message_official(to: str, body: str, db: Session) -> Dict:
    """Send message using official WhatsApp Cloud API"""
    try:
        url = f"{settings.API_URL}{settings.NUMBER_ID}/messages"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f"Bearer {settings.API_TOKEN}"
        }
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": body
            }
        }

        logger.debug(f"Sending message to {to} via official API")
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            response_data = response.json()

        if 'messages' in response_data and len(response_data['messages']) > 0:
            whatsapp_message_id = response_data['messages'][0]['id']
            # Log the outgoing message
            message = models.Message(
                whatsapp_message_id=whatsapp_message_id,
                phone_number=to,
                message_type='outgoing',
                message_content=body,
                status='sent',
                status_timestamp=datetime.now()
            )
            db.add(message)
            db.commit()
            logger.info(f"Successfully logged outgoing message {whatsapp_message_id}")
            return {"status": "success", "message": "Message sent successfully via official API"}
        else:
            logger.error("No message ID in response")
            return {"status": "error", "message": "No message ID in response"}

    except Exception as e:
        logger.error(f"Error sending message via official API: {str(e)}")
        return {"status": "error", "message": str(e)}

async def send_message_unofficial(to: str, body: str, db: Session) -> Dict:
    """Send message using unofficial API"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                settings.EXTERNAL_SERVICE_URL,
                json={
                    "phone": to,
                    "message": body,
                },
                headers={
                    'Client-Token': settings.UNOFFICIAL_CLIENT_TOKEN,
                    'Content-Type': 'application/json'
                },
                timeout=5
            )
            response.raise_for_status()

        # Generate a unique message ID for unofficial API
        message_id = f"unofficial-{datetime.now().timestamp()}"

        # Log the outgoing message
        message = models.Message(
            whatsapp_message_id=message_id,
            phone_number=to,
            message_type='outgoing',
            message_content=body,
            status='sent',
            status_timestamp=datetime.now()
        )
        db.add(message)
        db.commit()
        logger.info(f"Successfully logged outgoing message {message_id}")

        return {"status": "success", "message": "Message sent successfully via unofficial API"}
    except Exception as e:
        logger.error(f"Error sending message via unofficial API: {str(e)}")
        return {"status": "error", "message": str(e)}

async def send_message(to: str, body: str, db: Session = Depends(get_db)) -> Dict:
    """Unified message sending function that delegates to appropriate implementation"""
    use_official_api = settings.USE_OFFICIAL_API
    if use_official_api:
        return await send_message_official(to, body, db)
    return await send_message_unofficial(to, body, db)
