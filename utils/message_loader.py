import os
import yaml
import logging
from string import Formatter

logger = logging.getLogger(__name__)

class MessageLoader:
    _instance = None
    _messages = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MessageLoader, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if self._messages is None:
            self._load_messages()

    def _load_messages(self):
        """Load messages from YAML file"""
        try:
            # Look for messages.yml in the root directory
            messages_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'messages.yml')
            with open(messages_path, 'r', encoding='utf-8') as file:
                self._messages = yaml.safe_load(file)
                if not self._messages:
                    raise ValueError("Empty messages file")
        except Exception as e:
            logger.error(f"Error loading messages: {e}")
            self._messages = {}

    def get_message(self, key_path: str, **kwargs) -> str:
        """
        Get a message by its key path with optional formatting
        Example: get_message('menu.main') or get_message('location.saved', location='New York')
        """
        try:
            if not self._messages:
                self._load_messages()

            # Split the key path and traverse the messages dict
            keys = key_path.split('.')
            message = self._messages

            for key in keys:
                if not isinstance(message, dict):
                    raise ValueError(f"Invalid message structure at key: {key}")
                if key not in message:
                    raise KeyError(f"Message key not found: {key}")
                message = message[key]

            if not isinstance(message, str):
                raise ValueError(f"Message value is not a string for key: {key_path}")

            # Format the message if kwargs are provided
            if kwargs:
                return message.format(**kwargs)
            return message
        except Exception as e:
            logger.error(f"Error getting message for key '{key_path}': {e}")
            return f"Message not found for key: {key_path}"

# Create a singleton instance
message_loader = MessageLoader()