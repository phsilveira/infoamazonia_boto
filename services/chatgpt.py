import logging
import os
import base64
from typing import Optional, Dict, Tuple, List, Union
from config import settings
from utils.prompt_loader import prompt_loader

logger = logging.getLogger(__name__)

class ChatGPTService:
    def __init__(self):
        try:
            # Check if we should use Azure OpenAI
            if settings.USE_AZURE_OPENAI:
                from openai import AzureOpenAI
                
                # Initialize Azure OpenAI client
                self.client = AzureOpenAI(
                    azure_endpoint=settings.AZURE_ENDPOINT_URL,
                    api_key=settings.AZURE_OPENAI_API_KEY,
                    api_version=settings.AZURE_API_VERSION
                )
                self.azure_deployment = settings.AZURE_DEPLOYMENT_NAME
                self.use_azure = True
                logger.info(f"Azure OpenAI client initialized successfully with deployment {self.azure_deployment}")
            else:
                # Use standard OpenAI client
                from openai import OpenAI
                self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
                self.use_azure = False
                logger.info("Standard OpenAI client initialized successfully")
                
        except Exception as e:
            logger.error(f"Error initializing OpenAI client: {str(e)}")
            raise

    def generate_embedding(self, text: str) -> list:
        """Generate an embedding vector for the given text using OpenAI's API."""
        try:
            # For embeddings, the API interface is the same between standard and Azure OpenAI
            # Just use a different model name if using Azure
            model = "text-embedding-3-small"
            
            response = self.client.embeddings.create(
                model=model,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            raise

    def generate_completion(self, query: str, context: str, system_prompt: str = None) -> str:
        """Generate a completion using OpenAI's chat API."""
        try:
            if not system_prompt:
                system_prompt = prompt_loader.get_prompt('gpt-4.default_system_prompt')['system']

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Query: {query}\n\nContext: {context}"}
            ]

            # Common parameters
            params = {
                "messages": messages,
                "temperature": 0.2,
                "max_tokens": 800
            }
            
            # Set the model based on whether we're using Azure or standard OpenAI
            if self.use_azure:
                params["model"] = self.azure_deployment
            else:
                params["model"] = "gpt-4"
                
            response = self.client.chat.completions.create(**params)
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error generating completion: {e}")
            raise

    def generate_term_summary(self, title: str, content: str) -> str:
        """Generate a summary for a term using OpenAI's chat API."""
        try:
            prompt = prompt_loader.get_prompt('gpt-4.term_summary')
            messages = [
                {"role": "system", "content": prompt['system']},
                {"role": "user", "content": f"Title: {title}\n\nContent: {content}"}
            ]

            # Common parameters
            params = {
                "messages": messages,
                "temperature": 0.5,
                "max_tokens": 800
            }
            
            # Set the model based on whether we're using Azure or standard OpenAI
            if self.use_azure:
                params["model"] = self.azure_deployment
            else:
                params["model"] = "gpt-4"
                
            response = self.client.chat.completions.create(**params)
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error generating term summary: {e}")
            raise

    def generate_article_summary(self, title: str, content: str, url: str) -> str:
        """Generate a summary for an article using OpenAI's chat API."""
        try:
            prompt = prompt_loader.get_prompt('gpt-4.article_summary')
            messages = [
                {"role": "system", "content": prompt['system']},
                {"role": "user", "content": f"Title: {title}\n\nContent: {content}\n\nURL: {url}"}
            ]

            # Common parameters
            params = {
                "messages": messages,
                "temperature": 0.5,
                # "max_tokens": 800
            }
            
            # Set the model based on whether we're using Azure or standard OpenAI
            if self.use_azure:
                params["model"] = self.azure_deployment
            else:
                params["model"] = "gpt-4"
                
            response = self.client.chat.completions.create(**params)
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error generating article summary: {e}")
            raise

    async def summarize_queries(self, queries: List[str], interaction_type: str) -> str:
        """Summarize a list of user queries for a specific interaction type"""
        try:
            # Get the summarize_queries prompt from the prompt loader
            prompt = prompt_loader.get_prompt('gpt-4.summarize_queries', 
                                             interaction_type=interaction_type, 
                                             queries=queries)
            
            # Common parameters
            params = {
                "messages": [
                    {"role": "system", "content": prompt['system']},
                    {"role": "user", "content": prompt['user']}
                ],
                "temperature": prompt.get('temperature', 0.3),
                "max_tokens": prompt.get('max_tokens', 250)
            }
            
            # Set the model based on whether we're using Azure or standard OpenAI
            if self.use_azure:
                params["model"] = self.azure_deployment
            else:
                params["model"] = "gpt-4"
                
            completion = self.client.chat.completions.create(**params)
            return completion.choices[0].message.content
        except Exception as e:
            logger.error(f"Error summarizing queries: {str(e)}")
            return "Could not generate summary due to an error"

    async def summarize_queries_with_custom_prompt(self, queries: List[str], interaction_type: str, custom_system_prompt: str) -> str:
        """Summarize a list of user queries using a custom system prompt"""
        try:
            # Get the base prompt structure for the user prompt
            base_prompt = prompt_loader.get_prompt('gpt-4.summarize_queries', 
                                                 interaction_type=interaction_type, 
                                                 queries=queries)
            
            # Use custom system prompt with existing user prompt
            params = {
                "messages": [
                    {"role": "system", "content": custom_system_prompt},
                    {"role": "user", "content": base_prompt.get('user', f"Please analyze these {interaction_type} queries: {queries}")}
                ],
                "temperature": base_prompt.get('temperature', 0.3),
                "max_tokens": base_prompt.get('max_tokens', 250)
            }
            
            # Set the model based on whether we're using Azure or standard OpenAI
            if self.use_azure:
                params["model"] = self.azure_deployment
            else:
                params["model"] = "gpt-4"
                
            completion = self.client.chat.completions.create(**params)
            return completion.choices[0].message.content
        except Exception as e:
            logger.error(f"Error summarizing queries with custom prompt: {str(e)}")
            return "Could not generate summary with custom prompt due to an error"

    async def get_selected_article_title(self, user_input: str, template_message: str) -> Optional[str]:
        """Parse user's numeric selection and get corresponding article title from template message via ChatGPT"""
        try:
            # Get the get_selected_article_title prompt from the prompt loader
            prompt = prompt_loader.get_prompt('gpt-4.get_selected_article_title', 
                                             user_input=user_input, 
                                             template_message=template_message)
            
            # Common parameters
            params = {
                "messages": [
                    {"role": "system", "content": prompt['system']},
                    {"role": "user", "content": prompt['user']}
                ],
                "temperature": prompt.get('temperature', 0.1),
                "max_tokens": prompt.get('max_tokens', 150)
            }
            
            # Set the model based on whether we're using Azure or standard OpenAI
            if self.use_azure:
                params["model"] = self.azure_deployment
            else:
                params["model"] = "gpt-4"
                
            completion = self.client.chat.completions.create(**params)
            return completion.choices[0].message.content
        except Exception as e:
            logger.error(f"Error calling ChatGPT API: {str(e)}")
            return None

    async def validate_location(self, location: str) -> Tuple[bool, str]:
        """Validate and correct a location name"""
        try:
            # Get the validate_location prompt from the prompt loader
            prompt = prompt_loader.get_prompt('gpt-4.validate_location', location=location)
            
            # Common parameters
            params = {
                "messages": [
                    {"role": "system", "content": prompt['system']},
                    {"role": "user", "content": prompt['user']}
                ],
                "temperature": prompt.get('temperature', 0.1),
                "max_tokens": prompt.get('max_tokens', 150)
            }
            
            # Set the model based on whether we're using Azure or standard OpenAI
            if self.use_azure:
                params["model"] = self.azure_deployment
            else:
                params["model"] = "gpt-4"
                
            completion = self.client.chat.completions.create(**params)
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
            
            # Common parameters
            params = {
                "messages": [
                    {"role": "system", "content": prompt['system']},
                    {"role": "user", "content": prompt['user']}
                ],
                "temperature": prompt.get('temperature', 0.1),
                "max_tokens": prompt.get('max_tokens', 150)
            }
            
            # Set the model based on whether we're using Azure or standard OpenAI
            if self.use_azure:
                params["model"] = self.azure_deployment
            else:
                params["model"] = "gpt-4"
                
            completion = self.client.chat.completions.create(**params)
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
            
            # Common parameters
            params = {
                "messages": [
                    {"role": "system", "content": prompt['system']},
                    {"role": "user", "content": prompt['user']}
                ],
                "temperature": prompt.get('temperature', 0.1),
                "max_tokens": prompt.get('max_tokens', 150)
            }
            
            # Set the model based on whether we're using Azure or standard OpenAI
            if self.use_azure:
                params["model"] = self.azure_deployment
            else:
                params["model"] = "gpt-4"
                
            completion = self.client.chat.completions.create(**params)
            result = completion.choices[0].message.content.split('|')
            is_valid = result[0] == 'VALID'
            key = result[1] if len(result) > 1 else schedule
            return is_valid, key
        except Exception as e:
            logger.error(f"Error validating schedule: {str(e)}")
            return False, "Could not validate schedule"
            
    def process_image(self, image_path: str, prompt: str = None, system_prompt: str = None) -> str:
        """
        Process an image using vision capabilities of the model.
        Compatible with both Azure OpenAI and standard OpenAI.
        
        Args:
            image_path: Path to the image file
            prompt: Optional prompt to guide the image analysis
            system_prompt: Optional system prompt to set context
            
        Returns:
            The model's response as a string
        """
        try:
            # Read and encode the image
            with open(image_path, "rb") as image_file:
                encoded_image = base64.b64encode(image_file.read()).decode('ascii')
            
            # Prepare messages with the image
            messages = []
            
            # Add system message if provided
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            
            # Create content array with text and image
            content = []
            
            # Add text prompt if provided
            if prompt:
                content.append({"type": "text", "text": prompt})
            
            # Add image content
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{encoded_image}"
                }
            })
            
            # Add the user message with content
            messages.append({"role": "user", "content": content})
            
            # Common parameters
            params = {
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 800
            }
            
            # Set the model based on whether we're using Azure or standard OpenAI
            if self.use_azure:
                # For Azure, use the vision-capable deployment
                params["model"] = self.azure_deployment
            else:
                # For standard OpenAI, use GPT-4 Vision
                params["model"] = "gpt-4-vision-preview"
            
            # Make the API call
            response = self.client.chat.completions.create(**params)
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error processing image: {e}")
            raise
            
    async def generate_streaming_completion(self, messages: List[Dict], model: str = None, 
                                           temperature: float = 0.7, 
                                           max_tokens: int = 800):
        """
        Generate a streaming completion that works with both Azure and OpenAI APIs.
        
        Args:
            messages: List of message dictionaries (system, user, assistant)
            model: Optional model override
            temperature: Controls randomness (0 to 1)
            max_tokens: Maximum number of tokens to generate
            
        Returns:
            An asynchronous generator that yields response chunks
        """
        try:
            # Common parameters
            params = {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True
            }
            
            # Set the model based on whether we're using Azure or standard OpenAI
            if self.use_azure:
                params["model"] = model or self.azure_deployment
            else:
                params["model"] = model or "gpt-4"
            
            # Make the streaming API call
            stream = self.client.chat.completions.create(**params)
            
            # Process the stream
            for chunk in stream:
                if hasattr(chunk.choices[0].delta, "content"):
                    if chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        yield content
            
        except Exception as e:
            logger.error(f"Error generating streaming completion: {e}")
            raise
            
    async def generate_completion_with_full_response(self, messages: List[Dict], model: str = None, 
                                                    temperature: float = 0.7,
                                                    max_tokens: int = 800) -> str:
        """
        Generate a completion and return the full response as a string.
        This is a separate method from the streaming version that yields chunks.
        
        Args:
            messages: List of message dictionaries (system, user, assistant)
            model: Optional model override
            temperature: Controls randomness (0 to 1)
            max_tokens: Maximum number of tokens to generate
            
        Returns:
            The full response as a string
        """
        try:
            # Common parameters
            params = {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            
            # Set the model based on whether we're using Azure or standard OpenAI
            if self.use_azure:
                params["model"] = model or self.azure_deployment
            else:
                params["model"] = model or "gpt-4"
            
            # Make the API call (non-streaming)
            response = self.client.chat.completions.create(**params)
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error generating completion: {e}")
            raise
            