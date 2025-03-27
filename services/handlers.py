import logging
from services.chatbot import ChatBot
from services.chatgpt import ChatGPTService
from utils.message_loader import message_loader
from typing import Tuple
from services.whatsapp import send_message
from database import get_db
from models import UserInteraction, Location, Subject, User, Message # Added
from datetime import datetime
from config import settings

logger = logging.getLogger(__name__)

async def handle_start_state(chatbot: ChatBot, phone_number: str) -> str:
    """Handle the start state logic"""
    if chatbot.is_new_user(phone_number):
        chatbot.register_user(phone_number)    

    chatbot.show_menu()
    message = message_loader.get_message('menu.main')
    await send_message(phone_number, message, next(get_db()))
    return chatbot.state

async def handle_register_state(chatbot: ChatBot, phone_number: str, message: str) -> str:
    """Handle the register state logic"""
    try:
        chatbot.register_user(phone_number)
        chatbot.show_menu()
        menu_message = message_loader.get_message('menu.main')
        await send_message(phone_number, menu_message, next(get_db()))
        return chatbot.state
    except Exception as e:
        error_message = message_loader.get_message('error.registration_failed', error=str(e))
        await send_message(phone_number, error_message, next(get_db()))
        return chatbot.state

async def handle_menu_state(chatbot: ChatBot, phone_number: str, message: str) -> str:
    """Handle the menu state logic with more flexible input handling"""
    message = message.lower().strip()
    db = next(get_db())

    if message in ['1', 'subscribe', 'inscrever', 'notícias']:
        chatbot.select_subscribe()
        await send_message(phone_number, message_loader.get_message('location.request'), db)
    elif message in ['2', 'termo']:
        chatbot.select_term_info()
        await send_message(phone_number, message_loader.get_message('menu.term_info'), db)
    elif message in ['3', 'resumo', 'artigo']:
        chatbot.select_article_summary()
        await send_message(phone_number, message_loader.get_message('menu.article_summary'), db)
    elif message in ['4', 'sugestão', 'pauta']:
        chatbot.select_news_suggestion()
        await send_message(phone_number, message_loader.get_message('menu.news_suggestion'), db)
    elif message in ['6', 'about', 'sobre', 'info']:
        chatbot.select_about()
        await send_message(phone_number, message_loader.get_message('about.info'), db)
        await send_message(phone_number, message_loader.get_message('return_to_menu_from_subscription'), next(get_db()))
        chatbot.end_conversation()
        
    elif message in ['5', 'desinscrever', 'cancelar']:
        chatbot.select_unsubscribe()
        await send_message(phone_number, message_loader.get_message('unsubscribe.confirm'), db)
    else:
        await send_message(phone_number, message_loader.get_message('menu.invalid_option'), db)

    return chatbot.state

async def handle_location_state(chatbot: ChatBot, phone_number: str, message: str, chatgpt_service: ChatGPTService) -> str:
    """Handle the location state logic"""
    db = next(get_db())
    user = chatbot.get_user(phone_number)

    try:
        # Check for 'voltar' keyword to go back to main menu
        if message.lower().strip() == 'voltar':
            chatbot.show_menu()
            menu_message = message_loader.get_message('menu.main')
            await send_message(phone_number, menu_message, db)
            return chatbot.state
            
        confirmation_response = chatgpt_service.parse_confirmation(message)
        if confirmation_response is not None:
            if confirmation_response:
                await send_message(phone_number, message_loader.get_message('location.add_more'), db)
                return "get_user_location"
            else:
                chatbot.proceed_to_subjects()
                await send_message(phone_number, message_loader.get_message('subject.request'), db)
                return "get_user_subject"

        from services.location import validate_locations, get_location_details
        validation_results = validate_locations(message)

        # Handle "all locations" case
        if len(validation_results) == 1 and validation_results[0][1] == "ALL_LOCATIONS":
            try:
                location = Location(
                    location_name="All Locations",
                    latitude=None,
                    longitude=None,
                    user_id=user.id
                )
                db.add(location)
                db.commit()
                await send_message(
                    phone_number, 
                    message_loader.get_message('location.saved_all'), 
                    db
                )
                await send_message(phone_number, message_loader.get_message('subject.request'), db)
                return "get_user_subject"
            except Exception as e:
                db.rollback()
                logger.error(f"Error saving 'All Locations': {str(e)}")
                await send_message(phone_number, message_loader.get_message('error.save_location', error=str(e)), db)
                return chatbot.state

        # Get details for valid locations
        valid_locations = [result[1] for result in validation_results if result[0]]
        if not valid_locations:
            invalid_locations = [result[1] for result in validation_results if not result[0]]
            await send_message(
                phone_number, 
                message_loader.get_message('location.invalid', message=", ".join(invalid_locations)), 
                db
            )
            return chatbot.state

        # Get details and save valid locations
        locations_details = await get_location_details(message)
        saved_locations = []

        try:
            for location_detail in locations_details:
                location = Location(
                    location_name=location_detail["corrected_name"],
                    latitude=location_detail["latitude"],
                    longitude=location_detail["longitude"],
                    user_id=user.id
                )
                db.add(location)
                saved_locations.append(location_detail["corrected_name"])

            db.commit()

            # Notify about saved locations
            if len(saved_locations) == 1:
                await send_message(
                    phone_number, 
                    message_loader.get_message('location.saved', location=saved_locations[0]), 
                    db
                )
            else:
                await send_message(
                    phone_number, 
                    message_loader.get_message('location.saved_multiple', locations=", ".join(saved_locations)), 
                    db
                )
        except Exception as e:
            db.rollback()
            logger.error(f"Error saving locations: {str(e)}")
            await send_message(phone_number, message_loader.get_message('error.save_location', error=str(e)), db)

    except Exception as e:
        logger.error(f"Error in handle_location_state: {str(e)}")
        await send_message(phone_number, message_loader.get_message('error.process_message', error=str(e)), db)

    return chatbot.state

async def handle_subject_state(chatbot: ChatBot, phone_number: str, message: str, chatgpt_service: ChatGPTService) -> str:
    """Handle the subject state logic"""
    db = next(get_db())
    user = chatbot.get_user(phone_number)
    if not user:
        await send_message(phone_number, message_loader.get_message('error.user_not_found'), db)
        return chatbot.state

    try:
        confirmation_response = chatgpt_service.parse_confirmation(message)
        if confirmation_response is not None:
            if confirmation_response:
                await send_message(phone_number, message_loader.get_message('subject.add_more'), db)
            else:
                chatbot.proceed_to_schedule()
                await send_message(phone_number, message_loader.get_message('schedule.request'), db)
                return "get_user_schedule"

        is_valid, corrected_subject = await chatgpt_service.validate_subject(message)
        if not is_valid:
            await send_message(phone_number, message_loader.get_message('subject.invalid', message=corrected_subject), db)
            return chatbot.state

        if corrected_subject == "ALL_SUBJECTS":
            chatbot.save_subject(user.id, corrected_subject)
            await send_message(phone_number, message_loader.get_message('subject.saved_all'), db)
            chatbot.proceed_to_schedule()
            await send_message(phone_number, message_loader.get_message('schedule.request'), db)
            return "get_user_schedule"
    
        chatbot.save_subject(user.id, corrected_subject)
        await send_message(phone_number, message_loader.get_message('subject.saved', subject=corrected_subject), db)
        

    except Exception as e:
        logger.error(f"Error in handle_subject_state: {str(e)}")
        await send_message(phone_number, message_loader.get_message('error.save_subject', error=str(e)), db)
    

    return chatbot.state

async def handle_schedule_state(chatbot: ChatBot, phone_number: str, message: str, chatgpt_service: ChatGPTService) -> str:
    """Handle the schedule state logic with improved validation and Portuguese schedule names"""
    db = next(get_db())
    user = chatbot.get_user(phone_number)
    if not user:
        await send_message(phone_number, message_loader.get_message('error.user_not_found'), db)
        return chatbot.state

    # Simple mapping for display purposes only
    schedule_display = {
        'daily': 'Diário',
        'weekly': 'Semanal',
        'monthly': 'Mensal',
        'immediately': 'Assim que a notícia for publicada'
    }

    try:
        # Let the LLM validate and normalize the input
        is_valid, schedule_key = await chatgpt_service.validate_schedule(message)

        if not is_valid:
            await send_message(phone_number, message_loader.get_message('schedule.invalid_option'), db)
            return chatbot.state

        # Save the standardized key
        chatbot.save_schedule(user.id, schedule_key)
        chatbot.end_conversation()

        # Retrieve the user's location name and subject name
        locations = db.query(Location).filter(Location.user_id == user.id).all()
        location_names = ", ".join([str(loc.location_name) for loc in locations if loc.location_name is not None])

        subjects = db.query(Subject).filter(Subject.user_id == user.id).all()
        subject_names = ", ".join([str(sub.subject_name) for sub in subjects if sub.subject_name is not None])


        # Display the Portuguese version in the confirmation
        display_text = schedule_display.get(schedule_key, schedule_key)
        await send_message(
            phone_number, 
            message_loader.get_message(
                'schedule.confirmation', 
                schedule=display_text,
                location=location_names,
                subject=subject_names
            ), 
            db
        )
        await send_message(phone_number, message_loader.get_message('return_to_menu_from_subscription'), db)

    except Exception as e:
        logger.error(f"Error in handle_schedule_state: {str(e)}")
        await send_message(phone_number, message_loader.get_message('error.save_schedule', error=str(e)), db)

    return chatbot.state

async def handle_about_state(chatbot: ChatBot, phone_number: str) -> str:
    """Handle the about state logic"""
    await send_message(phone_number, message_loader.get_message('return_to_menu_from_subscription'), next(get_db()))
    chatbot.end_conversation()
    return chatbot.state

async def handle_term_info_state(chatbot: ChatBot, phone_number: str, message: str, chatgpt_service: ChatGPTService) -> str:
    """Handle the term info state logic"""
    db = next(get_db())
    try:
        import httpx
        api_url = f"{settings.SEARCH_BASE_URL}/api/v1/search/term"
        payload = {"query": message, "generate_summary": True}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(api_url, json=payload)
            data = response.json()

            if data.get("success") and data.get("summary") and int(data.get('count')) > 0:
                # Get user if exists
                user = chatbot.get_user(phone_number)
                user_id = user.id if user else None

                # Create user interaction record
                interaction = UserInteraction(
                    user_id=user_id,
                    phone_number=phone_number,
                    category='term',
                    query=message,
                    response=data["summary"]
                )
                db.add(interaction)
                db.commit()

                # Store interaction ID in chatbot state for feedback
                chatbot.set_current_interaction_id(interaction.id)

                await send_message(phone_number, data["summary"], db)
                chatbot.get_feedback()
                await send_message(phone_number, message_loader.get_message('feedback.request'), next(get_db()))
            else:
                await send_message(phone_number, message_loader.get_message('error.term_not_found'), db)
                await send_message(phone_number, message_loader.get_message('return_to_menu_from_subscription'), next(get_db()))
                chatbot.end_conversation()

    except Exception as e:
        logger.error(f"Error in term info handler: {str(e)}")
        await send_message(phone_number, message_loader.get_message('error.general_error'), db)

    return chatbot.state

async def handle_feedback_state(chatbot: ChatBot, phone_number: str, message: str, chatgpt_service: ChatGPTService) -> str:
    """Handle the feedback state logic"""
    db = next(get_db())
    try:
        message = message.strip()
        if message in ['1', '2']:
            # Get the interaction ID from chatbot state
            interaction_id = chatbot.get_current_interaction_id()
            if interaction_id:
                interaction = db.query(UserInteraction).filter(UserInteraction.id == interaction_id).first()
                if interaction:
                    interaction.feedback = message == '1'  # True for '1', False for '2'
                    interaction.updated_at = datetime.utcnow()
                    db.commit()
                    logger.info(f"Updated feedback for interaction {interaction_id}: {interaction.feedback}")
                else:
                    logger.error(f"Interaction {interaction_id} not found")
            else:
                logger.error("No interaction ID in chatbot state")

            chatbot.end_conversation()
            await send_message(phone_number, message_loader.get_message('return_to_menu_from_subscription'), db)
        else:
            await send_message(phone_number, message_loader.get_message('feedback.request'), db)
    except Exception as e:
        logger.error(f"Error in feedback handler: {str(e)}")
        await send_message(phone_number, message_loader.get_message('error.general_error'), db)

    return chatbot.state

async def handle_article_summary_state(chatbot: ChatBot, phone_number: str, message: str, chatgpt_service: ChatGPTService) -> str:
    """Handle the article info state logic"""
    db = next(get_db())
    try:
        import httpx
        api_url = f"{settings.SEARCH_BASE_URL}/api/v1/search/articles"
        payload = {"query": message}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(api_url, json=payload)
            data = response.json()

            if data.get("success") and data.get('count') > 0:
                # Get user if exists
                user = chatbot.get_user(phone_number)
                user_id = user.id if user else None

                # Create user interaction record
                interaction = UserInteraction(
                    user_id=user_id,
                    phone_number=phone_number,
                    category='article',
                    query=message,
                    response=data["results"][0]["summary_content"]
                )
                db.add(interaction)
                db.commit()

                # Store interaction ID in chatbot state for feedback
                chatbot.set_current_interaction_id(interaction.id)

                await send_message(phone_number, data["results"][0]["summary_content"], db)
                chatbot.get_feedback()
                await send_message(phone_number, message_loader.get_message('feedback.request'), next(get_db()))
            else:
                await send_message(phone_number, message_loader.get_message('error.article_not_found'), db)
                await send_message(phone_number, message_loader.get_message('return_to_menu_from_subscription'), db)
                chatbot.end_conversation()

    except Exception as e:
        logger.error(f"Error in article summary handler: {str(e)}")
        await send_message(phone_number, message_loader.get_message('error.general_error'), db)

    return chatbot.state

async def handle_news_suggestion_state(chatbot: ChatBot, phone_number: str, message: str, chatgpt_service: ChatGPTService) -> str:
    """Handle the news suggestion state logic"""
    db = next(get_db())
    try:
        # Get user if exists
        user = chatbot.get_user(phone_number)
        user_id = user.id if user else None

        # Create user interaction record for news suggestion
        interaction = UserInteraction(
            user_id=user_id,
            phone_number=phone_number,
            category='news_suggestion',
            query=message,
            response=message_loader.get_message('menu.news_suggestion_reply')
        )
        db.add(interaction)
        db.commit()

        # Store interaction ID in chatbot state for potential future feedback
        chatbot.set_current_interaction_id(interaction.id)

        chatbot.end_conversation()
        await send_message(phone_number, message_loader.get_message('menu.news_suggestion_reply'), db)
    except Exception as e:
        logger.error(f"Error in news suggestion handler: {str(e)}")
        await send_message(phone_number, message_loader.get_message('error.general_error'), db)

    return chatbot.state

async def handle_unsubscribe_state(chatbot: ChatBot, phone_number: str, message: str, chatgpt_service: ChatGPTService) -> str:
    """Handle the unsubscribe state logic"""
    db = next(get_db())
    user = chatbot.get_user(phone_number)
    if not user:
        await send_message(phone_number, message_loader.get_message('error.user_not_found'), db)
        return chatbot.state

    try:
        # confirmation_response = chatgpt_service.parse_confirmation(message)
        confirmation_response = message
        if confirmation_response is not None:
            if confirmation_response == '1':
                # Deactivate the user
                user.is_active = False
                db.commit()
                await send_message(phone_number, message_loader.get_message('unsubscribe.success'), db)
            else:
                await send_message(phone_number, message_loader.get_message('unsubscribe.cancelled'), db)

            chatbot.end_conversation()
        else:
            await send_message(phone_number, message_loader.get_message('unsubscribe.invalid_option'), db)

    except Exception as e:
        logger.error(f"Error in unsubscribe handler: {str(e)}")
        await send_message(phone_number, message_loader.get_message('error.process_message', error=str(e)), db)

    return chatbot.state

async def handle_monthly_news_response(chatbot: ChatBot, phone_number: str, message: str, chatgpt_service: ChatGPTService) -> str:
    """Handle user response to monthly news template"""
    db = next(get_db())
    try:
        # Get the last outgoing template message for this user
        last_template = db.query(Message).filter(
            Message.phone_number == phone_number,
            Message.message_type == 'outgoing',
            Message.status == 'sent',
            Message.message_content.isnot(None),
            ~Message.message_content.ilike('Por favor%'),
            ~Message.message_content.ilike('Desculpe%')
        ).order_by(Message.created_at.desc()).first()

        if not last_template:
            await send_message(phone_number, message_loader.get_message('error.news_message_not_found'), db)
            chatbot.end_conversation()
            return chatbot.state

        # Get the selected article title based on user's numeric choice
        selected_title = await chatgpt_service.get_selected_article_title(message, last_template.message_content)

        if not selected_title:
            await send_message(
                phone_number, 
                message_loader.get_message('error.select_article'), 
                db
            )
            return chatbot.state

        # Reuse the article summary functionality with the selected title
        api_url = f"{settings.SEARCH_BASE_URL}/api/v1/search/articles"
        payload = {"query": selected_title}

        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(api_url, json=payload)
            data = response.json()

            if data.get("success") and data.get('count') > 0:
                # Get user if exists
                user = chatbot.get_user(phone_number)
                user_id = user.id if user else None

                # Create user interaction record
                interaction = UserInteraction(
                    user_id=user_id,
                    phone_number=phone_number,
                    category='monthly_news_response',
                    query=selected_title,
                    response=data["results"][0]["summary_content"]
                )
                db.add(interaction)
                db.commit()

                # Store interaction ID in chatbot state for feedback
                chatbot.set_current_interaction_id(interaction.id)

                await send_message(phone_number, data["results"][0]["summary_content"], db)
                chatbot.get_feedback()
                await send_message(phone_number, message_loader.get_message('feedback.request'), next(get_db()))
            else:
                await send_message(phone_number, message_loader.get_message('error.article_not_found'), db)
                await send_message(phone_number, message_loader.get_message('return_to_menu_from_subscription'), db)
                chatbot.end_conversation()

    except Exception as e:
        logger.error(f"Error in monthly news response handler: {str(e)}")
        await send_message(phone_number, message_loader.get_message('error.general_error'), db)

    return chatbot.state