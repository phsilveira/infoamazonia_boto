import os
import yaml
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class PromptLoader:
    _instance = None
    _prompts = None

    def __new__(cls):
        """Singleton pattern to ensure only one instance of PromptLoader exists"""
        if cls._instance is None:
            cls._instance = super(PromptLoader, cls).__new__(cls)
            cls._instance._load_prompts()
        return cls._instance

    def __init__(self):
        """Initialize is empty because everything is handled in __new__"""
        pass

    def _load_prompts(self):
        """Load prompts from YAML file"""
        try:
            prompts_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'prompts.yml')
            with open(prompts_path, 'r', encoding='utf-8') as file:
                self._prompts = yaml.safe_load(file)
            logger.info(f"Loaded prompts from {prompts_path}")
        except Exception as e:
            logger.error(f"Error loading prompts: {str(e)}")
            self._prompts = {}

    def get_prompt(self, key_path: str, **kwargs) -> Dict[str, Any]:
        """
        Get a prompt by its key path with optional formatting
        Example: get_prompt('gpt-4.summarize_queries') 
        
        Returns a dictionary with prompt components:
        {
            'system': '...',
            'user': '...',
            'temperature': 0.3,
            'max_tokens': 250
        }
        
        Any prompt text values will be formatted with the kwargs provided.
        """
        if not self._prompts:
            logger.warning("No prompts loaded")
            return {}

        # Split the key path and navigate through the nested dictionaries
        parts = key_path.split('.')
        current = self._prompts
        
        for part in parts:
            if part in current:
                current = current[part]
            else:
                logger.warning(f"Prompt key not found: {key_path}")
                return {}
        
        # Apply formatting to system and user prompt texts if kwargs provided
        if isinstance(current, dict):
            result = current.copy()
            
            # Format the system prompt if it exists
            if 'system' in result and kwargs:
                try:
                    result['system'] = result['system'].format(**kwargs)
                except KeyError as e:
                    logger.warning(f"Missing format key in system prompt: {e}")
            
            # Format the user prompt if it exists
            if 'user' in result and kwargs:
                try:
                    result['user'] = result['user'].format(**kwargs)
                except KeyError as e:
                    logger.warning(f"Missing format key in user prompt: {e}")
            
            return result
        
        logger.warning(f"Prompt key {key_path} does not contain a valid prompt structure")
        return {}


# Singleton instance
prompt_loader = PromptLoader()