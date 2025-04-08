import httpx
import logging
from datetime import datetime
from typing import Dict, Optional, List, Union
from fastapi import Depends
from sqlalchemy.orm import Session
from database import get_db
import models
from config import settings

logger = logging.getLogger(__name__)

async def send_message(
    to: str,
    content: Union[str, Dict],
    db: Session,
    message_type: str = "text"
) -> Dict:
    """Send message using WhatsApp Cloud API with support for text, template, and interactive messages"""
    try:
        url = f"{settings.API_URL}{settings.NUMBER_ID}/messages"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f"Bearer {settings.API_TOKEN}"
        }

        # Base payload structure
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to
        }

        # Handle different message types
        if message_type == "text":
            payload.update({
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": content if isinstance(content, str) else str(content)
                }
            })
        elif message_type == "interactive":
            if not isinstance(content, dict):
                raise ValueError("Interactive content must be a dictionary")
                
            payload.update({
                "type": "interactive",
                "interactive": content
            })
        elif message_type == "template":
            if not isinstance(content, dict):
                raise ValueError("Template content must be a dictionary")

            payload.update({
                "type": "template",
                "template": {
                    "name": content.get("name"),
                    "language": {
                        "code": content.get("language", "en_US")
                    }
                }
            })

            # Add components if provided
            if "components" in content:
                payload["template"]["components"] = content["components"]

        logger.debug(f"Sending {message_type} message to {to}")
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
                message_content=str(content),
                status='sent',
                status_timestamp=datetime.now()
            )
            db.add(message)
            db.commit()
            logger.info(f"Successfully logged outgoing message {whatsapp_message_id}")
            return {
                "status": "success",
                "message": "Message sent successfully",
                "whatsapp_message_id": whatsapp_message_id,
                "response": response_data
            }
        else:
            logger.error("No message ID in response")
            return {"status": "error", "message": "No message ID in response"}

    except httpx.HTTPStatusError as e:
        error_msg = f"HTTP error sending message: {str(e.response.json() if e.response else e)}"
        logger.error(error_msg)
        return {"status": "error", "message": error_msg}
    except Exception as e:
        error_msg = f"Error sending message: {str(e)}"
        logger.error(error_msg)
        return {"status": "error", "message": error_msg}

# Example usage for template message:
# template_content = {
#     "name": "hello_world",
#     "language": "en_US",
#     "components": [
#         {
#             "type": "body",
#             "parameters": [
#                 {
#                     "type": "text",
#                     "text": "John"
#                 }
#             ]
#         }
#     ]
# }
# result = await send_message(to="1234567890", content=template_content, db=db, message_type="template")