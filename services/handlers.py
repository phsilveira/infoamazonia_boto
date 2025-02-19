import logging
from services.chatbot import ChatBot
from services.chatgpt import ChatGPTService
from utils.message_loader import message_loader
from typing import Tuple

logger = logging.getLogger(__name__)

async def handle_start_state(chatbot: ChatBot, phone_number: str) -> Tuple[str, str]:
    """Handle the start state logic"""
    if chatbot.is_new_user(phone_number):
        chatbot.verify_user(phone_number)
        return message_loader.get_message('welcome.new_user'), chatbot.state
    else:
        chatbot.show_menu()
        return message_loader.get_message('menu.main'), chatbot.state

async def handle_register_state(chatbot: ChatBot, phone_number: str, message: str) -> Tuple[str, str]:
    """Handle the register state logic"""
    try:
        chatbot.register_user(phone_number, message)
        chatbot.show_menu()
        return message_loader.get_message('menu.main'), chatbot.state
    except Exception as e:
        return message_loader.get_message('error.registration_failed', error=str(e)), chatbot.state

async def handle_menu_state(chatbot: ChatBot, message: str) -> Tuple[str, str]:
    """Handle the menu state logic with more flexible input handling"""
    message = message.lower().strip()
    if message in ['1', 'subscribe', 'inscrever', 'notícias']:
        chatbot.select_subscribe()
        return message_loader.get_message('location.request'), chatbot.state
    elif message in ['2', 'termo', ]:
        chatbot.select_term_info()
        return message_loader.get_message('menu.term_info'), chatbot.state
    elif message in ['3', 'resumo', 'artigo']:
        chatbot.select_article_summary()
        return message_loader.get_message('menu.article_summary'), chatbot.state
    elif message in ['4', 'sugestão', 'pauta']:
        chatbot.select_news_suggestion()
        return message_loader.get_message('menu.news_suggestion'), chatbot.state
    elif message in ['5', 'about', 'sobre', 'info']:
        chatbot.select_about()
        return message_loader.get_message('about.info'), chatbot.state
    else:
        return message_loader.get_message('menu.invalid_option'), chatbot.state

async def handle_location_state(chatbot: ChatBot, phone_number: str, message: str, chatgpt_service: ChatGPTService) -> Tuple[str, str]:
    """Handle the location state logic with location service validation"""
    user = chatbot.get_user(phone_number)
    if not user:
        return message_loader.get_message('error.user_not_found'), chatbot.state

    # Try to parse as a confirmation first
    try:
        confirmation_response = chatgpt_service.parse_confirmation(message)
        if confirmation_response is not None:
            if confirmation_response:  # User wants to add more
                return message_loader.get_message('location.add_more'), chatbot.state
            else:  # User doesn't want to add more
                chatbot.proceed_to_subjects()
                return message_loader.get_message('subject.request'), "get_user_subject"

        # If not a confirmation, validate and get location details using our new service
        from services.location import validate_brazilian_location, get_location_details

        is_valid, corrected_name, region_type = await validate_brazilian_location(message)
        if not is_valid:
            return message_loader.get_message('location.invalid', message=corrected_name), chatbot.state

        # Get location details including coordinates
        location_details = await get_location_details(corrected_name)

        # Save the validated location with coordinates
        from models import Location
        from database import SessionLocal

        db = SessionLocal()
        try:
            location = Location(
                location_name=location_details["corrected_name"],
                latitude=location_details["latitude"],
                longitude=location_details["longitude"],
                user_id=user.id
            )
            db.add(location)
            db.commit()
            db.refresh(location)
        except Exception as e:
            db.rollback()
            logger.error(f"Error saving location: {str(e)}")
            return message_loader.get_message('error.save_location', error=str(e)), chatbot.state
        finally:
            db.close()

        return message_loader.get_message('location.saved', location=location_details["corrected_name"]), chatbot.state

    except Exception as e:
        logger.error(f"Error in handle_location_state: {str(e)}")
        return message_loader.get_message('error.process_message', error=str(e)), chatbot.state

async def handle_subject_state(chatbot: ChatBot, phone_number: str, message: str, chatgpt_service: ChatGPTService) -> Tuple[str, str]:
    """Handle the subject state logic with ChatGPT validation"""
    user = chatbot.get_user(phone_number)
    if not user:
        return message_loader.get_message('error.user_not_found'), chatbot.state

    try:
        # Try to parse as a confirmation first
        confirmation_response = chatgpt_service.parse_confirmation(message)
        if confirmation_response is not None:
            if confirmation_response:  # User wants to add more
                return message_loader.get_message('subject.add_more'), chatbot.state
            else:  # User doesn't want to add more
                chatbot.proceed_to_schedule()
                return message_loader.get_message('schedule.request'), "get_user_schedule"

        # If not a clear yes/no, treat as subject input
        is_valid, corrected_subject = await chatgpt_service.validate_subject(message)
        if not is_valid:
            return message_loader.get_message('subject.invalid', message=corrected_subject), chatbot.state

        # Save the validated subject
        chatbot.save_subject(user.id, corrected_subject)
        return message_loader.get_message('subject.saved', subject=corrected_subject), chatbot.state
    except Exception as e:
        logger.error(f"Error in handle_subject_state: {str(e)}")
        return message_loader.get_message('error.save_subject', error=str(e)), chatbot.state

async def handle_schedule_state(chatbot: ChatBot, phone_number: str, message: str, chatgpt_service: ChatGPTService) -> Tuple[str, str]:
    """Handle the schedule state logic with more flexible input handling"""
    user = chatbot.get_user(phone_number)
    if not user:
        return message_loader.get_message('error.user_not_found'), chatbot.state

    # Map various schedule inputs to standard values
    schedule_map = {
        '1': 'daily',
        'daily': 'daily',
        'dia': 'daily',
        'diário': 'daily',
        '2': 'weekly',
        'weekly': 'weekly',
        'semana': 'weekly',
        'semanal': 'weekly',
        '3': 'monthly',
        'monthly': 'monthly',
        'mes': 'monthly',
        'mensal': 'monthly'
    }

    schedule = schedule_map.get(message.lower().strip())

    if not schedule:
        return message_loader.get_message('schedule.invalid_option'), chatbot.state

    try:
        chatbot.save_schedule(user.id, schedule)
        chatbot.end_conversation()
        return message_loader.get_message('schedule.confirmation', schedule=schedule), chatbot.state
    except Exception as e:
        return message_loader.get_message('error.save_schedule', error=str(e)), chatbot.state

async def handle_about_state(chatbot: ChatBot) -> Tuple[str, str]:
    """Handle the about state logic"""
    chatbot.end_conversation()
    return message_loader.get_message('about.return'), chatbot.state

async def handle_term_info_state(chatbot: ChatBot, phone_number: str, message: str, chatgpt_service: ChatGPTService) -> Tuple[str, str]:
    """Handle the term info state logic"""
    try:
        import httpx
        
        api_url = "https://aa109676-f2b5-40ce-9a8b-b7d95b3a219e-00-30gb0h9bugxba.spock.replit.dev/api/v1/search/term"
        payload = {
            "query": message,
            "generate_summary": True
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(api_url, json=payload)
            data = response.json()
            
            if data.get("success") and data.get("summary"):
                chatbot.state = "term_info_feedback"
                return f"{data['summary']}\n\n{message_loader.get_message('term_info.feedback')}", chatbot.state
            else:
                return message_loader.get_message('term_info.error'), chatbot.state
                
    except Exception as e:
        logger.error(f"Error in term info handler: {str(e)}")
        return message_loader.get_message('term_info.api_error'), chatbot.state

async def handle_article_summary_state(chatbot: ChatBot, phone_number: str, message: str, chatgpt_service: ChatGPTService) -> Tuple[str, str]:
    """Handle the article summary state logic"""
    chatbot.end_conversation()
    return message_loader.get_message('menu.implementation_soon'), chatbot.state

async def handle_news_suggestion_state(chatbot: ChatBot, phone_number: str, message: str, chatgpt_service: ChatGPTService) -> Tuple[str, str]:
    """Handle the news suggestion state logic"""
    chatbot.end_conversation()
    return message_loader.get_message('menu.implementation_soon'), chatbot.state