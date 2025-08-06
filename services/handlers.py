import logging
from services.chatbot import ChatBot
from services.chatgpt import ChatGPTService
from utils.message_loader import message_loader
from typing import Tuple
from services.whatsapp import send_message
from database import get_db
from models import UserInteraction, Location, Subject, User, Message # Added
from datetime import datetime, timedelta
from config import settings
from services.search import search_term_service, search_articles_service

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

    # If the message is "menu" or similar, show the interactive menu
    if message in ['menu', 'início', 'inicio', 'start', 'começar', 'opcoes', 'opções']:
        # Create interactive buttons for the main menu options
        menu_message = message_loader.get_message('menu.main')
        await send_message(phone_number, menu_message, next(get_db()))

    # Process the user's selection
    if message in ['1', 'subscribe', 'inscrever', 'notícias']:
        # Store the phone number first, then trigger the transition
        chatbot.set_current_phone_number(phone_number)
        chatbot.select_subscribe()
        
        # If user has a location preference, they'll be sent to modify_subscription_state, 
        # otherwise to get_user_location as before
        if chatbot.state == 'modify_subscription_state':
            await send_message(phone_number, message_loader.get_message('subscription.modify_options'), db)
        else:
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
        interactive_content = {
            "type": "button",
            "body": {
                "text": message_loader.get_message('unsubscribe.confirm').split('\n\n')[0]  # Get the main text part
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": "1",
                            "title": "Sim, descadastrar"
                        }
                    },
                    {
                        "type": "reply",
                        "reply": {
                            "id": "2",
                            "title": "Não, continuar"
                        }
                    }
                ]
            }
        }
        await send_message(phone_number, interactive_content, db, message_type="interactive")
    else:
        menu_message = message_loader.get_message('menu.main')
        await send_message(phone_number, menu_message, next(get_db()))

    return chatbot.state

async def handle_location_state(chatbot: ChatBot, phone_number: str, message: str, chatgpt_service: ChatGPTService) -> str:
    """Handle the location state logic"""
    db = next(get_db())
    user = chatbot.get_user(phone_number)

    try:
        # Check for 'voltar' keyword to go back to main menu
        if message.lower().strip() in ['voltar', 'menu']:
            chatbot.show_menu()
            menu_message = message_loader.get_message('menu.main')
            await send_message(phone_number, menu_message, db)
            return chatbot.state

        db.query(Location).filter(
            Location.user_id == user.id,
            Location.created_at <= datetime.utcnow() - timedelta(hours=1)
        ).delete()
        db.flush()
            
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
                    location_name="Todos Locais",
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

    # Check for 'voltar' keyword to go back to main menu
    if message.lower().strip() == 'voltar':
        chatbot.show_menu()
        menu_message = message_loader.get_message('menu.main')
        await send_message(phone_number, menu_message, db)
        return chatbot.state

    
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

        # db.query(Subject).filter(
        #     Subject.user_id == user.id,
        #     Subject.created_at <= datetime.utcnow() - timedelta(hours=1)
        # ).delete()
        # db.flush()
        
        is_valid, corrected_subject = await chatgpt_service.validate_subject(message)
        if not is_valid:
            await send_message(phone_number, message_loader.get_message('subject.invalid', message=corrected_subject), db)
            return chatbot.state

        if corrected_subject == "Todos temas":
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

async def handle_modify_subscription_state(chatbot: ChatBot, phone_number: str, message: str, chatgpt_service: ChatGPTService) -> str:
    """Handle the modify subscription state logic"""
    message = message.lower().strip()
    db = next(get_db())
    user = chatbot.get_user(phone_number)
    
    # Store the phone number for condition methods
    chatbot.set_current_phone_number(phone_number)
    
    if not user:
        await send_message(phone_number, message_loader.get_message('error.user_not_found'), db)
        chatbot.show_menu()
        return chatbot.state
    
    # Check for 'voltar' keyword to go back to main menu
    if message.lower().strip() == 'voltar':
        chatbot.show_menu()
        menu_message = message_loader.get_message('menu.main')
        await send_message(phone_number, menu_message, db)
        return chatbot.state
    
    # Process the user's selection for which part of subscription to modify
    if message in ['1', 'local', 'localização', 'location']:
        chatbot.select_location_modification()
        await send_message(phone_number, message_loader.get_message('location.request'), db)
    elif message in ['2', 'tema', 'assunto', 'subject']:
        chatbot.select_subject_modification()
        await send_message(phone_number, message_loader.get_message('subject.request'), db)
    elif message in ['3', 'frequência', 'schedule', 'programação']:
        chatbot.select_schedule_modification()
        await send_message(phone_number, message_loader.get_message('schedule.request'), db)
    else:
        # For invalid options, remind the user of the available choices
        interactive_content = {
            "type": "button",
            "body": {
                "text": "O que você gostaria de modificar na sua inscrição?"
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": "1",
                            "title": "Localização 📍"
                        }
                    },
                    {
                        "type": "reply",
                        "reply": {
                            "id": "2",
                            "title": "Temas de interesse 📚"
                        }
                    },
                    {
                        "type": "reply",
                        "reply": {
                            "id": "3",
                            "title": "Frequência de recebimento 🕒"
                        }
                    }
                ]
            }
        }
        await send_message(phone_number, interactive_content, db, message_type="interactive")
    
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
        chatbot.activate_subscription(user.id)
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
        # Use the search service directly instead of making HTTP request
        data = await search_term_service(query=message, db=db, generate_summary=True, redis_client=None)

        if data.get("success") and data.get("summary") and int(data.get('count', 0)) > 0:
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
            await chatbot.set_current_interaction_id(interaction.id, phone_number)

            await send_message(phone_number, data["summary"], db)
            chatbot.get_feedback()

            # Send an interactive button message for feedback
            interactive_content = {
                "type": "button",
                "body": {
                    "text": message_loader.get_message('feedback.request').split('\n')[0]  # Get only the text part
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "sim",
                                "title": "Sim"
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "não",
                                "title": "Não"
                            }
                        }
                    ]
                }
            }
            await send_message(phone_number, interactive_content, next(get_db()), message_type="interactive")
        else:
            await send_message(phone_number, message_loader.get_message('error.term_not_found'), db)
            await send_message(phone_number, message_loader.get_message('return'), next(get_db()))
            chatbot.end_conversation()

    except Exception as e:
        logger.error(f"Error in term info handler: {str(e)}")
        await send_message(phone_number, message_loader.get_message('error.general_error'), db)

    return chatbot.state

async def handle_feedback_state(chatbot: ChatBot, phone_number: str, message: str, chatgpt_service: ChatGPTService) -> str:
    """Handle the feedback state logic with interactive UI buttons"""
    db = next(get_db())
    try:
        message = message.strip()
        # Process feedback response (from button click or text message)
        if message in ['1', '2', 'sim', 'não', 'nao']:
            # Get the interaction ID from chatbot state
            interaction_id = await chatbot.get_current_interaction_id(phone_number)
            if interaction_id:
                interaction = db.query(UserInteraction).filter(UserInteraction.id == interaction_id).first()
                if interaction:
                    # True for '1' or 'sim', False for '2' or 'não'
                    interaction.feedback = message in ['1', 'sim']
                    interaction.updated_at = datetime.utcnow()
                    db.commit()
                    logger.info(f"Updated feedback for interaction {interaction_id}: {interaction.feedback}")
                else:
                    logger.error(f"Interaction {interaction_id} not found")
            else:
                logger.error("No interaction ID in chatbot state")

            chatbot.end_conversation()
            await send_message(phone_number, message_loader.get_message('return'), db)
        # else:
        #     # Send an interactive button message for feedback
        #     interactive_content = {
        #         "type": "button",
        #         "body": {
        #             "text": message_loader.get_message('feedback.request').split('\n')[0]  # Get only the text part
        #         },
        #         "action": {
        #             "buttons": [
        #                 {
        #                     "type": "reply",
        #                     "reply": {
        #                         "id": "sim",
        #                         "title": "Sim"
        #                     }
        #                 },
        #                 {
        #                     "type": "reply",
        #                     "reply": {
        #                         "id": "não",
        #                         "title": "Não"
        #                     }
        #                 }
        #             ]
        #         }
        #     }
        #     await send_message(phone_number, interactive_content, db, message_type="interactive")
    except Exception as e:
        logger.error(f"Error in feedback handler: {str(e)}")
        await send_message(phone_number, message_loader.get_message('error.general_error'), db)

    return chatbot.state


async def handle_article_summary_state(chatbot: ChatBot, phone_number: str, message: str, chatgpt_service: ChatGPTService) -> str:
    """Handle the article info state logic"""
    db = next(get_db())
    try:
        # Use the search service directly instead of making HTTP request
        data = await search_articles_service(query=message, db=db, redis_client=None)

        if data.get("success") and data.get('count', 0) > 0:
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
            await chatbot.set_current_interaction_id(interaction.id, phone_number)

            await send_message(phone_number, data["results"][0]["summary_content"], db)
            chatbot.get_feedback()

            # Send an interactive button message for feedback
            interactive_content = {
                "type": "button",
                "body": {
                    "text": message_loader.get_message('feedback.request').split('\n')[0]  # Get only the text part
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "sim",
                                "title": "Sim"
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "não",
                                "title": "Não"
                            }
                        }
                    ]
                }
            }
            await send_message(phone_number, interactive_content, next(get_db()), message_type="interactive")
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
        await chatbot.set_current_interaction_id(interaction.id, phone_number)

        chatbot.end_conversation()
        await send_message(phone_number, message_loader.get_message('menu.news_suggestion_reply'), db)
    except Exception as e:
        logger.error(f"Error in news suggestion handler: {str(e)}")
        await send_message(phone_number, message_loader.get_message('error.general_error'), db)

    return chatbot.state

async def handle_unsubscribe_state(chatbot: ChatBot, phone_number: str, message: str, chatgpt_service: ChatGPTService) -> str:
    """Handle the unsubscribe state logic with interactive buttons"""
    db = next(get_db())
    user = chatbot.get_user(phone_number)
    if not user:
        await send_message(phone_number, message_loader.get_message('error.user_not_found'), db)
        return chatbot.state

    try:
        # If this is the first call to unsubscribe (initial state), show the interactive buttons
        if message.lower() == '5' or message.lower() in ['desinscrever', 'cancelar', 'unsubscribe']:
            # Send an interactive button message for unsubscribe confirmation
            interactive_content = {
                "type": "button",
                "body": {
                    "text": message_loader.get_message('unsubscribe.confirm').split('\n\n')[0]  # Get the main text part
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "1",
                                "title": "Sim, descadastrar"
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "2",
                                "title": "Não, continuar"
                            }
                        }
                    ]
                }
            }
            await send_message(phone_number, interactive_content, db, message_type="interactive")
            return chatbot.state

        # Process the user's response
        confirmation_response = message
        if confirmation_response in ['1', '2', 'sim', 'não']:
            if confirmation_response in ['1', 'sim']:
                # Delete the user and all related data from database
                try:
                    # Delete related data first (due to foreign key constraints)
                    db.query(Location).filter(Location.user_id == user.id).delete()
                    db.query(Subject).filter(Subject.user_id == user.id).delete()
                    db.query(UserInteraction).filter(UserInteraction.user_id == user.id).delete()
                    db.query(Message).filter(Message.phone_number == phone_number).delete()
                    
                    # Finally delete the user
                    db.delete(user)
                    db.commit()
                    
                    await send_message(phone_number, message_loader.get_message('unsubscribe.success'), db)
                    logger.info(f"User {phone_number} successfully deleted from database")
                except Exception as delete_error:
                    db.rollback()
                    logger.error(f"Error deleting user {phone_number}: {str(delete_error)}")
                    await send_message(phone_number, message_loader.get_message('error.process_message', error="Erro ao processar descadastro"), db)
                    return chatbot.state
            else:
                await send_message(phone_number, message_loader.get_message('unsubscribe.cancelled'), db)

            chatbot.end_conversation()
        else:
            # For any other message, show the invalid option message and send buttons again
            await send_message(phone_number, message_loader.get_message('unsubscribe.invalid_option'), db)
            
            # Send interactive buttons again
            interactive_content = {
                "type": "button",
                "body": {
                    "text": message_loader.get_message('unsubscribe.confirm').split('\n\n')[0]  # Get the main text part
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "1",
                                "title": "Sim, descadastrar"
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "2",
                                "title": "Não, continuar"
                            }
                        }
                    ]
                }
            }
            await send_message(phone_number, interactive_content, db, message_type="interactive")

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
        logger.info(f"Selected article title: {selected_title}")

        if not selected_title:
            await send_message(
                phone_number, 
                message_loader.get_message('error.select_article'), 
                db
            )
            return chatbot.state

        if selected_title.lower() == 'menu':
            chatbot.show_menu()
            message = message_loader.get_message('menu.main')
            await send_message(phone_number, message, next(get_db()))
            return chatbot.state

        # Reuse the article summary functionality with the selected title
        data = await search_articles_service(query=selected_title, db=db, redis_client=None)

        if data.get("success") and data.get('count') > 0:
            # Get user if exists
            user = chatbot.get_user(phone_number)
            user_id = user.id if user else None

            # Create user interaction record
            interaction = UserInteraction(
                user_id=user_id,
                phone_number=phone_number,
                category='article',
                query=selected_title,
                response=data["results"][0]["summary_content"]
            )
            db.add(interaction)
            db.commit()

            # Store interaction ID in chatbot state for feedback
            await chatbot.set_current_interaction_id(interaction.id, phone_number)

            await send_message(phone_number, data["results"][0]["summary_content"], db)
            chatbot.get_feedback()

            # Send an interactive button message for feedback
            interactive_content = {
                "type": "button",
                "body": {
                    "text": message_loader.get_message('feedback.request').split('\n')[0]  # Get only the text part
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "sim",
                                "title": "Sim"
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "não",
                                "title": "Não"
                            }
                        }
                    ]
                }
            }
            await send_message(phone_number, interactive_content, next(get_db()), message_type="interactive")
        else:
            await send_message(phone_number, message_loader.get_message('error.article_not_found'), db)
            await send_message(phone_number, message_loader.get_message('return'), db)
            chatbot.end_conversation()

    except Exception as e:
        logger.error(f"Error in monthly news response handler: {str(e)}")
        await send_message(phone_number, message_loader.get_message('error.general_error'), db)

    return chatbot.state