import logging
from typing import Optional, Dict, Tuple, List
import openai
from config import settings
from utils.prompt_loader import prompt_loader

logger = logging.getLogger(__name__)

class ChatGPTService:
    def __init__(self):
        # Initialize OpenAI client with API key
        try:
            # Create client for OpenAI version 1.3.3
            from openai import OpenAI
            self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
            logger.info("OpenAI client initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing OpenAI client: {str(e)}")
            # As a fallback, use the module-level client configuration
            openai.api_key = settings.OPENAI_API_KEY
            self.client = openai
            logger.info("Using module-level OpenAI client")

    async def summarize_queries(self, queries: List[str], interaction_type: str) -> str:
        """Summarize a list of user queries for a specific interaction type"""
        try:
            # Get the summarize_queries prompt from the prompt loader
            prompt = prompt_loader.get_prompt('gpt-4.summarize_queries', 
                                             interaction_type=interaction_type, 
                                             queries=queries)
            
            completion = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": prompt['system']},
                    {"role": "user", "content": prompt['user']}
                ],
                temperature=prompt.get('temperature', 0.3),
                max_tokens=prompt.get('max_tokens', 250)
            )
            return completion.choices[0].message.content
        except Exception as e:
            logger.error(f"Error summarizing queries: {str(e)}")
            return "Could not generate summary due to an error"

    async def get_selected_article_title(self, user_input: str, template_message: str) -> Optional[str]:
        """Parse user's numeric selection and get corresponding article title from template message via ChatGPT"""
        try:
            # Get the get_selected_article_title prompt from the prompt loader
            prompt = prompt_loader.get_prompt('gpt-4.get_selected_article_title', 
                                             user_input=user_input, 
                                             template_message=template_message)
            
            completion = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": prompt['system']},
                    {"role": "user", "content": prompt['user']}
                ],
                temperature=prompt.get('temperature', 0.1),
                max_tokens=prompt.get('max_tokens', 150)
            )
            return completion.choices[0].message.content
        except Exception as e:
            logger.error(f"Error calling ChatGPT API: {str(e)}")
            return None

    async def validate_location(self, location: str) -> Tuple[bool, str]:
        """Validate and correct a location name"""
        try:
            # Get the validate_location prompt from the prompt loader
            prompt = prompt_loader.get_prompt('gpt-4.validate_location', location=location)
            
            completion = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": prompt['system']},
                    {"role": "user", "content": prompt['user']}
                ],
                temperature=prompt.get('temperature', 0.1),
                max_tokens=prompt.get('max_tokens', 150)
            )
            result = completion.choices[0].message.content.split('|')
            is_valid = result[0] == 'VALID'
            corrected_location = result[1] if len(result) > 2 else location
            return is_valid, corrected_location
        except Exception as e:
            logger.error(f"Error validating location: {str(e)}")
            return False, "Could not validate location"

    async def validate_subject(self, subject: str) -> tuple[bool, str]:
        """Validate and categorize a subject related to Amazon"""
        # Check for "all locations" variations
        all_locations_variations = [
            "todas", "todos", "todas as", "all",
            "todas as localizações", "todas localizações", "all locations", "1"
        ]

        if any(subject.lower().strip().startswith(v) for v in all_locations_variations):
            return True, "Todos temas"

        try:
            # Get the validate_subject prompt from the prompt loader
            prompt = prompt_loader.get_prompt('gpt-4.validate_subject', subject=subject)
            
            completion = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": prompt['system']},
                    {"role": "user", "content": prompt['user']}
                ],
                temperature=prompt.get('temperature', 0.1),
                max_tokens=prompt.get('max_tokens', 150)
            )
            result = completion.choices[0].message.content.split('|')
            is_valid = result[0] == 'VALID'
            corrected_subject = result[1] if len(result) > 2 else subject
            return is_valid, corrected_subject
        except Exception as e:
            logger.error(f"Error validating subject: {str(e)}")
            return False, "Could not validate subject"

    def parse_confirmation(self, message: str) -> Optional[bool]:
        """Parse exact yes/no responses in English and Portuguese"""
        message = message.lower().strip()

        # Simple yes/no matching
        if message in ['yes', 'sim', 's', 'y']:
            return True
        elif message in ['no', 'não', 'nao', 'n']:
            return False

        return None

    async def validate_schedule(self, schedule: str) -> tuple[bool, str]:
        """Validate user schedule input and return standardized key"""
        try:
            # Get the validate_schedule prompt from the prompt loader
            prompt = prompt_loader.get_prompt('gpt-4.validate_schedule', schedule=schedule)
            
            completion = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": prompt['system']},
                    {"role": "user", "content": prompt['user']}
                ],
                temperature=prompt.get('temperature', 0.1),
                max_tokens=prompt.get('max_tokens', 150)
            )
            result = completion.choices[0].message.content.split('|')
            is_valid = result[0] == 'VALID'
            key = result[1] if len(result) > 1 else schedule
            return is_valid, key
        except Exception as e:
            logger.error(f"Error validating schedule: {str(e)}")
            return False, "Could not validate schedule"