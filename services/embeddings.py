"""
Embeddings service for FastAPI
"""
import logging
from services.chatgpt import ChatGPTService

logger = logging.getLogger(__name__)

# Initialize ChatGPT service
chatgpt_service = ChatGPTService()

def generate_embedding(text: str) -> list:
    """Generate embedding using ChatGPT service"""
    return chatgpt_service.generate_embedding(text)

def generate_term_summary(title: str, content: str) -> str:
    """Generate term summary using ChatGPT service"""
    return chatgpt_service.generate_term_summary(title, content)

def generate_completion(query: str, context: str, system_prompt: str = None) -> str:
    """Generate completion using ChatGPT service"""
    return chatgpt_service.generate_completion(query, context, system_prompt)

def generate_article_summary(title: str, content: str, url: str) -> str:
    """Generate article summary using ChatGPT service"""
    return chatgpt_service.generate_article_summary(title, content, url)