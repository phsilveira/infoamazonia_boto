import logging
from typing import Optional, Dict, Tuple, List
from openai import OpenAI
from config import settings

logger = logging.getLogger(__name__)

class ChatGPTService:
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    async def summarize_queries(self, queries: List[str], interaction_type: str) -> str:
        """Summarize a list of user queries for a specific interaction type"""
        try:
            completion = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that summarizes user interactions and identifies common patterns."},
                    {"role": "user", "content": f"""
                    Please analyze and summarize these user queries for {interaction_type}:

                    {queries}

                    Provide a concise summary that includes:
                    1. Most common topics or themes
                    2. Types of information users are seeking
                    3. Notable patterns in user behavior

                    Keep the summary short and focused on key insights.
                    """}
                ],
                temperature=0.3,
                max_tokens=250
            )
            return completion.choices[0].message.content
        except Exception as e:
            logger.error(f"Error summarizing queries: {str(e)}")
            return "Could not generate summary due to an error"

    async def get_selected_article_title(self, user_input: str, template_message: str) -> Optional[str]:
        """Parse user's numeric selection and get corresponding article title from template message via ChatGPT"""
        try:
            completion = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that retrieves article titles based on user selection."},
                    {"role": "user", "content": f"""
                    Using the following user input '{user_input}', and the JSON structure provided, determine which article title corresponds to the user's numeric selection or article name based on the key 'parameters', a list. If the user chooses 1 or provides text matching the first element of the list, return the text of the first element. If the user chooses 2 or provides text matching the second element, return the text of that item and so on:
                    
                    {template_message}
                    
                    RETURN ONLY THE TITLE OF THE ARTICLE CHOSEN, DO NOT RETURN ANY JUSTIFICATION OR ANYTHING ELSE.
                    """}
                ],
                temperature=0.1,
                max_tokens=150
            )
            return completion.choices[0].message.content
        except Exception as e:
            logger.error(f"Error calling ChatGPT API: {str(e)}")
            return None

    async def validate_location(self, location: str) -> Tuple[bool, str]:
        """Validate and correct a location name"""
        try:
            completion = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that validates Brazilian Amazon locations."},
                    {"role": "user", "content": f"Is '{location}' a valid location (city, region, state, popular expression) in the Brazil? If it's valid but has typos, correct the location_name. If it's not valid, explain why. Also the user can insert multiple locations in a same message, if any of the locations is invalid then answer with the location invalid only Response format: 'VALID|INVALID|location_names|explanation'"}
                ],
                temperature=0.1,
                max_tokens=150
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
            return True, "ALL_SUBJECTS"

        try:
            completion = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that validates and categorizes subjects related to the Amazon rainforest."},
                    {"role": "user", "content": f"""Is '{subject}' a valid subject related to the Amazon rainforest?
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
                ],
                temperature=0.1,
                max_tokens=150
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
            completion = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a scheduling assistant that validates schedule preferences."},
                    {"role": "user", "content": f"""Map the given schedule preference '{schedule}' to one of the following standard keys:

            - 'daily' for daily notifications (option 1)
            - 'weekly' for weekly notifications (option 2)
            - 'monthly' for monthly notifications (option 3)
            - 'immediately' for immediate notifications (option 4)

            **Valid inputs include:**
            - Numbers (1-4)
            - Portuguese words (diário, semanal, mensal, imediato)
            - Phrases like "Assim que a notícia for publicada"
            - English words (daily, weekly, monthly, immediate)

            **STRICT Output format (only return the following, nothing else):**
            - If the input is valid, return: `VALID|<key>` (Example: `VALID|immediately`)
            - If the input is invalid, return: `INVALID`

            **Do not return numbers. Do not explain. Do not provide any extra text.**
            """}
                ],
                temperature=0.1,
                max_tokens=150
            )
            result = completion.choices[0].message.content.split('|')
            is_valid = result[0] == 'VALID'
            key = result[1] if len(result) > 1 else schedule
            return is_valid, key
        except Exception as e:
            logger.error(f"Error validating schedule: {str(e)}")
            return False, "Could not validate schedule"