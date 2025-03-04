import logging
from typing import Optional, Dict, Tuple
import httpx
from config import settings

logger = logging.getLogger(__name__)

class ChatGPTService:
    def __init__(self, ):
        # self.api_key = api_key
        self.api_url = "https://api.openai.com/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }

    async def _make_request(self, messages: list) -> Optional[Dict]:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.api_url,
                    headers=self.headers,
                    json={
                        "model": "gpt-4",
                        "messages": messages,
                        "temperature": 0.1,
                        "max_tokens": 150
                    }
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Error calling ChatGPT API: {str(e)}")
            return None

    async def validate_location(self, location: str) -> Tuple[bool, str]:
        """Validate and correct a location name"""
        messages = [
            {"role": "system", "content": "You are a helpful assistant that validates Brazilian Amazon locations."},
            {"role": "user", "content": f"Is '{location}' a valid location (city, region, state, popular expression) in the Brazil? If it's valid but has typos, correct the location_name. If it's not valid, explain why. Also the user can insert multiple locations in a same message, if any of the locations is invalid then answer with the location invalid only Response format: 'VALID|INVALID|location_names|explanation'"}
        ]

        response = await self._make_request(messages)
        if not response or not response.get('choices'):
            return False, "Could not validate location"

        result = response['choices'][0]['message']['content'].split('|')
        is_valid = result[0] == 'VALID'
        corrected_location = result[1] if len(result) > 2 else location

        return is_valid, corrected_location

    async def validate_subject(self, subject: str) -> tuple[bool, str]:
        """Validate and categorize a subject related to Amazon"""
        messages = [
            {"role": "system", "content": "You are a helpful assistant that validates and categorizes subjects related to the Amazon rainforest."},
            {"role": "user", "content": f"""Is ‘{subject}’ a valid subject related to the Amazon rainforest?
    •\tExamples of valid subjects:
    1.\tTodos assuntos
    2.\tConservação e clima
    3.\tPovos originários e territórios
    4.\tPolítica e economia amazônica
    5.\tBiodiversidade e saúde ambiental
    6.\tSaúde e educação na Amazônia
    7.\tMineração em terras indígenas
etc.
    •\tInstructions for validation:
    •\tIf the input is a number (1-7), map it to the corresponding example subject above.
    •\tIf the input is a subject text, check its relevance to the examples provided.
    •\tIf valid but needs correction, provide the corrected version of the subject.
    •\tIf invalid, explain why it does not match any valid subject.

Response format:
VALID|INVALID|subject_name|explanation"""}
        ]

        response = await self._make_request(messages)
        if not response or not response.get('choices'):
            return False, "Could not validate subject"

        result = response['choices'][0]['message']['content'].split('|')
        is_valid = result[0] == 'VALID'
        corrected_subject = result[1] if len(result) > 2 else subject

        return is_valid, corrected_subject

    def parse_confirmation(self, message: str) -> Optional[bool]:
        """Parse exact yes/no responses in English and Portuguese"""
        message = message.lower().strip()

        # Simple yes/no matching
        if message in ['yes', 'sim', 's', 'y']:
            return True
        elif message in ['no', 'não', 'nao', 'n']:
            return False

        return None
