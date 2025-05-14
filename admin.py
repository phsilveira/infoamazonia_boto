from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from sqlalchemy.orm import Session
from typing import List
import models
import schemas
from database import get_db
from auth import get_current_admin, get_password_hash
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from datetime import datetime, timezone
import json
import httpx
import logging
import csv
import io
from config import settings
from sqlalchemy import desc, or_, func, select, text
from services.chatgpt import ChatGPTService # Fixed import
from cache_utils import invalidate_dashboard_caches, get_cache, set_cache  # Import cache utilities

logger = logging.getLogger(__name__)

# Create templates instance
templates = Jinja2Templates(directory="templates")

router = APIRouter(prefix="/admin", tags=["admin"])
chatgpt_service = ChatGPTService()

@router.post("/users/create", response_class=HTMLResponse)
async def create_user(
    request: Request,
    phone_number: str = Form(...),
    status: str = Form(...),
    schedule: str = Form(...),
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    try:
        # Create new user
        user = models.User(
            phone_number=phone_number,
            is_active=(status == 'active'),
            schedule=schedule
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        
        # Invalidate dashboard caches after user creation
        await invalidate_dashboard_caches(request)
        logger.info(f"Cache invalidated after creating user: {user.id}")

        return RedirectResponse(
            url=f"/admin/users/{user.id}",
            status_code=302
        )
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create user: {str(e)}"
        )

@router.get("/users", response_class=HTMLResponse)
async def list_users(
    request: Request,
    phone_number: str = None,
    status: str = None,
    sort: str = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    query = db.query(models.User)

    # Apply phone number search
    if phone_number:
        query = query.filter(models.User.phone_number.ilike(f"%{phone_number}%"))

    # Apply status filter
    if status == 'active':
        query = query.filter(models.User.is_active == True)
    elif status == 'inactive':
        query = query.filter(models.User.is_active == False)

    # Apply sorting
    if sort == 'created_at_asc':
        query = query.order_by(models.User.created_at.asc())
    else:  # Default to newest first
        query = query.order_by(models.User.created_at.desc())

    users = query.offset(skip).limit(limit).all()

    return templates.TemplateResponse(
        "admin/users.html",
        {"request": request, "users": users}
    )

@router.get("/news-sources", response_class=HTMLResponse)
async def list_news_sources(
    request: Request,
    search: str = None,
    status: str = None,
    sort: str = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    # Start with a base query
    query = db.query(models.NewsSource)
    
    # Apply search filter if provided
    if search:
        query = query.filter(
            or_(
                models.NewsSource.name.ilike(f"%{search}%"),
                models.NewsSource.url.ilike(f"%{search}%")
            )
        )
    
    # Apply status filter if provided
    if status:
        is_active = status == "active"
        query = query.filter(models.NewsSource.is_active == is_active)
    
    # Apply sorting if provided
    if sort == "created_at_asc":
        query = query.order_by(models.NewsSource.created_at.asc())
    elif sort == "name_asc":
        query = query.order_by(models.NewsSource.name.asc())
    elif sort == "name_desc":
        query = query.order_by(models.NewsSource.name.desc())
    else:  # Default to newest first
        query = query.order_by(models.NewsSource.created_at.desc())
    
    sources = query.offset(skip).limit(limit).all()
    
    return templates.TemplateResponse(
        "admin/news-sources.html",
        {"request": request, "sources": sources}
    )

@router.post("/news-sources/create", response_class=HTMLResponse)
async def create_news_source(
    request: Request,
    name: str = Form(...),
    url: str = Form(...),
    status: str = Form(...),
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    try:
        # Check if a news source with this URL already exists
        existing_source = db.query(models.NewsSource).filter(models.NewsSource.url == url).first()
        if existing_source:
            # Return error
            sources = db.query(models.NewsSource).order_by(desc(models.NewsSource.created_at)).all()
            return templates.TemplateResponse(
                "admin/news-sources.html",
                {
                    "request": request, 
                    "sources": sources,
                    "error": "A news source with this URL already exists."
                }
            )
        
        # Create new news source
        source = models.NewsSource(
            name=name,
            url=url,
            is_active=(status == 'active')
        )
        db.add(source)
        db.commit()
        db.refresh(source)
        
        # Invalidate dashboard caches after news source creation
        await invalidate_dashboard_caches(request)
        logger.info(f"Cache invalidated after creating news source: {source.id}")

        return RedirectResponse(
            url="/admin/news-sources",
            status_code=302
        )
    except Exception as e:
        logger.error(f"Error creating news source: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create news source: {str(e)}"
        )

@router.get("/news-sources/{source_id}", response_class=HTMLResponse)
async def get_news_source(
    request: Request,
    source_id: int,
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    # Get the news source
    source = db.query(models.NewsSource).filter(models.NewsSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="News source not found")
    
    return templates.TemplateResponse(
        "admin/news-source-detail.html",
        {"request": request, "source": source}
    )

@router.post("/news-sources/{source_id}/status", response_class=RedirectResponse)
async def update_news_source_status(
    request: Request,
    source_id: int,
    status: str = Form(...),
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    try:
        source = db.query(models.NewsSource).filter(models.NewsSource.id == source_id).first()
        if not source:
            raise HTTPException(status_code=404, detail="News source not found")
        
        # Update status
        source.is_active = status == "active"
        db.commit()
        
        # Invalidate dashboard caches after status update
        await invalidate_dashboard_caches(request)
        
        return RedirectResponse(
            url=f"/admin/news-sources/{source_id}",
            status_code=status.HTTP_302_FOUND
        )
    except Exception as e:
        logger.error(f"Error updating news source status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update news source status: {str(e)}"
        )

@router.post("/news-sources/{source_id}/edit", response_class=RedirectResponse)
async def edit_news_source(
    request: Request,
    source_id: int,
    name: str = Form(...),
    url: str = Form(...),
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    try:
        source = db.query(models.NewsSource).filter(models.NewsSource.id == source_id).first()
        if not source:
            raise HTTPException(status_code=404, detail="News source not found")
        
        # Check if URL is already taken by another source
        existing_source = db.query(models.NewsSource).filter(
            models.NewsSource.url == url,
            models.NewsSource.id != source_id
        ).first()
        
        if existing_source:
            # Return with error
            return templates.TemplateResponse(
                "admin/news-source-detail.html",
                {
                    "request": request,
                    "source": source,
                    "error": "A news source with this URL already exists."
                }
            )
        
        # Update source details
        source.name = name
        source.url = url
        db.commit()
        
        # Invalidate dashboard caches after edit
        await invalidate_dashboard_caches(request)
        
        return RedirectResponse(
            url=f"/admin/news-sources/{source_id}",
            status_code=status.HTTP_302_FOUND
        )
    except Exception as e:
        logger.error(f"Error updating news source: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update news source: {str(e)}"
        )

@router.post("/news-sources/{source_id}/delete", response_class=RedirectResponse)
async def delete_news_source(
    request: Request,
    source_id: int,
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    try:
        source = db.query(models.NewsSource).filter(models.NewsSource.id == source_id).first()
        if not source:
            raise HTTPException(status_code=404, detail="News source not found")
        
        # Delete the source
        db.delete(source)
        db.commit()
        
        # Invalidate dashboard caches after deletion
        await invalidate_dashboard_caches(request)
        
        return RedirectResponse(
            url="/admin/news-sources",
            status_code=status.HTTP_302_FOUND
        )
    except Exception as e:
        logger.error(f"Error deleting news source: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete news source: {str(e)}"
        )

@router.post("/news-sources/{source_id}/download-articles", response_class=RedirectResponse)
async def download_articles_for_source(
    request: Request,
    source_id: int,
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    """Download articles for a specific news source using web scraping"""
    try:
        # Verify source exists
        source = db.query(models.NewsSource).filter(models.NewsSource.id == source_id).first()
        if not source:
            raise HTTPException(status_code=404, detail="News source not found")

        # Import required classes to perform download
        from services.article_ingestion import process_article, ingest_articles
        from models import Article
        import sys
        import types

        # Create a wrapper for Flask db session to work with SQLAlchemy
        class DbWrapper:
            def __init__(self, db_session):
                self.session = db_session

        # This is the key - we wrap our FastAPI session to match the Flask app.db format
        # that the article_ingestion.py code expects
        app_db = DbWrapper(db)
        
        # Patch the Article model for compatibility with Flask SQLAlchemy
        # by adding the query attribute expected by the ingestion code
        Article.query = db.query(Article)
        
        # Temporarily add the wrapper to the sys modules
        app_module = types.ModuleType("app")
        app_module.db = app_db
        sys.modules['app'] = app_module
        
        try:
            logger.info(f"Attempting to get articles from source: {source.name} ({source.url})")
            from services.news import News
            
            # Initialize the News class with our database session
            news = News()
            news.db = app_db
            
            # Fetch news from configured sources
            result = news.get_news()
            
            if not result.get('success', False):
                logger.error(f"Failed to fetch articles from sources")
                # Clean up temporary module
                if 'app' in sys.modules:
                    del sys.modules['app']
                # Return to the source detail page with error
                return RedirectResponse(
                    url=f"/admin/news-sources/{source_id}",
                    status_code=status.HTTP_302_FOUND
                )
            
            # Now call ingest_articles with our patched environment
            articles_added_count = ingest_articles(result.get('news', []))
            method_used = "process_article and ingest_articles"
            
        except Exception as e:
            logger.error(f"Failed to process articles: {str(e)}")
            # Clean up temporary module
            if 'app' in sys.modules:
                del sys.modules['app']
            raise Exception(f"Failed to process articles: {str(e)}")
        
        # Clean up temporary module
        if 'app' in sys.modules:
            del sys.modules['app']

        # Log the result
        if articles_added_count > 0:
            logger.info(f"Successfully downloaded and processed {articles_added_count} new articles via {method_used}")
        else:
            logger.info(f"No new articles were found or all articles already exist in the database ({method_used})")
        
        # Invalidate dashboard caches after adding articles
        await invalidate_dashboard_caches(request)
        
        # Return to the source detail page
        return RedirectResponse(
            url=f"/admin/news-sources/{source_id}",
            status_code=status.HTTP_302_FOUND
        )
        
    except Exception as e:
        logger.error(f"Error downloading articles: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to download articles: {str(e)}"
        )

@router.get("/metrics", response_class=HTMLResponse)
async def get_metrics(
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    metrics = db.query(models.Metrics).order_by(models.Metrics.date.desc()).all()
    return templates.TemplateResponse(
        "admin/metrics.html",
        {"request": request, "metrics": metrics}
    )

@router.get("/messages", response_class=HTMLResponse)
async def messages_page(
    request: Request,
    page: int = 1,
    page_size: int = 10,
    message_type: str = None,
    status: str = None,
    phone_number: str = None,
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    # Get message templates and scheduled messages
    templates_list = db.query(models.MessageTemplate).all()
    scheduled_messages = db.query(models.ScheduledMessage).order_by(models.ScheduledMessage.scheduled_time.desc()).all()
    hello_world_template = db.query(models.MessageTemplate).filter(models.MessageTemplate.name == "hello_world").first()
    
    # Query messages with pagination and filtering
    query = db.query(models.Message)
    
    # Apply filters if provided
    if message_type:
        query = query.filter(models.Message.message_type == message_type)
    if status:
        query = query.filter(models.Message.status == status)
    if phone_number:
        query = query.filter(models.Message.phone_number.contains(phone_number))
    
    # Get total message count for pagination
    total_messages = query.count()
    total_pages = (total_messages + page_size - 1) // page_size
    
    # Apply pagination
    messages = query.order_by(models.Message.created_at.desc()) \
        .offset((page - 1) * page_size) \
        .limit(page_size) \
        .all()
    
    # Get unique status and message type values for filters
    status_options = db.query(models.Message.status) \
        .filter(models.Message.status.isnot(None)) \
        .distinct() \
        .all()
    message_type_options = db.query(models.Message.message_type) \
        .distinct() \
        .all()
    
    return templates.TemplateResponse(
        "admin/messages.html",
        {
            "request": request,
            "message_templates": templates_list,
            "scheduled_messages": scheduled_messages,
            "hello_world_template": hello_world_template,
            "messages": messages,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "total_messages": total_messages,
            "message_type": message_type,
            "status": status,
            "phone_number": phone_number,
            "status_options": [s[0] for s in status_options if s[0]],  # Filter None values
            "message_type_options": [t[0] for t in message_type_options]
        }
    )

@router.post("/messages/template", response_class=HTMLResponse)
async def create_template(
    request: Request,
    name: str = Form(...),
    content: str = Form(...),
    variables: str = Form(...),
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    template = models.MessageTemplate(
        name=name,
        content=content,
        variables=json.loads(variables)
    )
    db.add(template)
    db.commit()
    return RedirectResponse(url="/admin/messages", status_code=status.HTTP_302_FOUND)

@router.post("/messages/schedule", response_class=HTMLResponse)
async def schedule_new_message(
    request: Request,
    template_id: int = Form(...),
    schedule_type: str = Form(...),
    scheduled_date: str = Form(None),
    target_group: str = Form(...),
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    try:
        # Calculate scheduled time based on schedule type
        if schedule_type == "just_in_time" and scheduled_date:
            scheduled_time = datetime.strptime(f"{scheduled_date} 09:00", "%Y-%m-%d %H:%M")
        else:
            scheduled_time = datetime.now(timezone.utc)

        # Create scheduled message record
        scheduled_message = models.ScheduledMessage(
            template_id=template_id,
            scheduled_time=scheduled_time,
            target_groups={"target_group": target_group},
            status="pending"
        )
        db.add(scheduled_message)
        db.commit()

        return RedirectResponse(url="/admin/messages", status_code=status.HTTP_302_FOUND)
    except Exception as e:
        logger.error(f"Error scheduling message: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to schedule message: {str(e)}"
        )

@router.get("/users/{user_id}", response_class=HTMLResponse)
async def get_user(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get user's locations and subjects
    locations = db.query(models.Location).filter(models.Location.user_id == user_id).all()
    subjects = db.query(models.Subject).filter(models.Subject.user_id == user_id).all()

    return templates.TemplateResponse(
        "admin/user_detail.html",
        {"request": request, "user": user, "locations": locations, "subjects": subjects}
    )

@router.post("/users/{user_id}/subjects", response_class=HTMLResponse)
async def add_user_subject(
    request: Request,
    user_id: int,
    subject_name: str = Form(...),
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    try:
        subject = models.Subject(
            subject_name=subject_name,
            user_id=user_id
        )
        db.add(subject)
        db.commit()
        
        # Invalidate dashboard caches
        await invalidate_dashboard_caches(request)
        logger.info(f"Cache invalidated after adding subject to user {user_id}")
        
        return RedirectResponse(url=f"/admin/users/{user_id}", status_code=status.HTTP_302_FOUND)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/users/{user_id}/subjects/{subject_id}/delete", response_class=HTMLResponse)
async def delete_user_subject(
    request: Request,
    user_id: int,
    subject_id: int,
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    subject = db.query(models.Subject).filter(models.Subject.id == subject_id, models.Subject.user_id == user_id).first()
    if subject:
        db.delete(subject)
        db.commit()
    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=status.HTTP_302_FOUND)

@router.post("/users/{user_id}/locations/{location_id}/delete", response_class=HTMLResponse)
async def delete_user_location(
    request: Request,
    user_id: int,
    location_id: int,
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    location = db.query(models.Location).filter(models.Location.id == location_id, models.Location.user_id == user_id).first()
    if location:
        db.delete(location)
        db.commit()
    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=status.HTTP_302_FOUND)

@router.post("/users/{user_id}/location", response_class=HTMLResponse)
async def add_user_location(
    request: Request,
    user_id: int,
    location_name: str = Form(...),
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    try:
        # Validate locations
        from services.location import validate_locations, get_location_details
        validation_results = validate_locations(location_name)

        # Handle "all locations" case
        if len(validation_results) == 1 and validation_results[0][1] == "ALL_LOCATIONS":
            location = models.Location(
                location_name="All Locations",
                latitude=None,
                longitude=None,
                user_id=user_id
            )
            db.add(location)
            db.commit()
            return RedirectResponse(url=f"/admin/users/{user_id}", status_code=status.HTTP_302_FOUND)

        # Get details for valid locations
        valid_locations = [result[1] for result in validation_results if result[0]]
        if not valid_locations:
            return templates.TemplateResponse(
                "admin/user_detail.html",
                {
                    "request": request,
                    "user": db.query(models.User).filter(models.User.id == user_id).first(),
                    "locations": db.query(models.Location).filter(models.Location.user_id == user_id).all(),
                    "subjects": db.query(models.Subject).filter(models.Subject.user_id == user_id).all(),
                    "error": f"Invalid location(s): {location_name}",
                    "show_location_modal": True
                }
            )

        # Get details and save valid locations
        locations_details = await get_location_details(location_name)
        for location_detail in locations_details:
            location = models.Location(
                location_name=location_detail["corrected_name"],
                latitude=location_detail["latitude"],
                longitude=location_detail["longitude"],
                user_id=user_id
            )
            db.add(location)

        db.commit()
        return RedirectResponse(url=f"/admin/users/{user_id}", status_code=status.HTTP_302_FOUND)

    except Exception as e:
        logger.error(f"Error in add_user_location: {str(e)}")
        return templates.TemplateResponse(
            "admin/user_detail.html",
            {
                "request": request,
                "user": db.query(models.User).filter(models.User.id == user_id).first(),
                "locations": db.query(models.Location).filter(models.Location.user_id == user_id).all(),
                "subjects": db.query(models.Subject).filter(models.Subject.user_id == user_id).all(),
                "error": f"Error adding location: {str(e)}",
                "show_location_modal": True
            }
        )

@router.get("/interactions", response_class=HTMLResponse)
async def list_interactions(
    request: Request,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    interactions = db.query(models.UserInteraction).order_by(
        models.UserInteraction.created_at.desc()
    ).offset(skip).limit(limit).all()
    return templates.TemplateResponse(
        "admin/interactions.html",
        {"request": request, "interactions": interactions}
    )

@router.get("/interactions/summaries/{category}") #NEW ROUTE
async def get_interaction_summaries(
    request: Request,
    category: str,
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    try:
        # Define cache key for this category
        cache_key = f"interaction_summary:{category}"
        
        # Try to get from cache first
        cached_result = await get_cache(cache_key, request)
        if cached_result:
            logger.info(f"Returning cached interaction summary for category: {category}")
            return cached_result
            
        # If not in cache, proceed with generating the summary
        # Get queries for the specified category
        queries = db.query(models.UserInteraction.query)\
            .filter(models.UserInteraction.category == category)\
            .all()

        # Extract query texts
        query_texts = [q[0] for q in queries]

        if not query_texts:
            result = {"summary": "No queries found for this category"}
            # Cache the empty result as well
            await set_cache(cache_key, result, request, expire_seconds=180)  # 3 minutes TTL
            return result

        # Generate summary using ChatGPT
        summary = await chatgpt_service.summarize_queries(query_texts, category)

        # Prepare result
        result = {"summary": summary}
        
        # Store in cache with 3-minute TTL (180 seconds)
        await set_cache(cache_key, result, request, expire_seconds=180)
        
        return result
    except Exception as e:
        logger.error(f"Error generating interaction summaries: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate summaries: {str(e)}"
        )

@router.post("/messages/send-template", response_class=HTMLResponse)
async def send_template_message(
    request: Request,
    template_name: str = Form(...),
    language_code: str = Form(...),
    phone_number: str = Form(...),
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    try:
        # Prepare the template content
        template_content = {
            "name": template_name,
            "language": language_code
        }

        # Send the template message using the updated WhatsApp service
        from services.whatsapp import send_message
        result = await send_message(
            to=phone_number,
            content=template_content,
            db=db,
            message_type="template"
        )

        if result["status"] == "success":
            return RedirectResponse(
                url="/admin/messages",
                status_code=status.HTTP_302_FOUND
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"WhatsApp API error: {result['message']}"
            )

    except Exception as e:
        logger.error(f"Error sending template message: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send template message: {str(e)}"
        )

@router.get("/scheduler", response_class=HTMLResponse)
async def scheduler_runs_page(
    request: Request,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    try:
        # Get recent scheduler runs
        scheduler_runs = db.query(models.SchedulerRun)\
            .order_by(desc(models.SchedulerRun.start_time))\
            .offset(skip)\
            .limit(limit)\
            .all()

        return templates.TemplateResponse(
            "admin/scheduler.html",
            {
                "request": request,
                "scheduler_runs": scheduler_runs
            }
        )
    except Exception as e:
        logger.error(f"Error fetching scheduler runs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch scheduler runs: {str(e)}"
        )
        
@router.get("/ctr-stats", response_class=HTMLResponse)
async def ctr_stats_page(
    request: Request,
    current_admin: models.Admin = Depends(get_current_admin)
):
    """Display detailed click-through rate statistics"""
    try:
        # Fetch CTR stats from the API endpoint
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{settings.SEARCH_BASE_URL}/api/v1/analytics/ctr-stats")
            response.raise_for_status()
            ctr_data = response.json()
            
        return templates.TemplateResponse(
            "admin/ctr-stats.html",
            {"request": request, "ctr_data": ctr_data}
        )
    except Exception as e:
        logger.error(f"Error fetching CTR stats for page: {str(e)}")
        # Instead of using a separate error template, we'll use the main template
        # with error data that can display a message
        dummy_data = {
            "totals": {
                "total_urls": 0,
                "total_impressions": 0,
                "total_clicks": 0,
                "overall_ctr": 0
            },
            "stats": []
        }
        return templates.TemplateResponse(
            "admin/ctr-stats.html",
            {
                "request": request, 
                "ctr_data": dummy_data,
                "error": f"Failed to fetch CTR statistics: {str(e)}"
            }
        )
    
@router.get("/articles/export-csv")
async def export_articles_csv(
    request: Request,
    search: str = None,
    news_source: str = None,
    language: str = None,
    sort: str = None,
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    """Export articles to CSV with current filters applied."""
    # Setup logging
    logger = logging.getLogger(__name__)
    
    # Start building the query
    query = db.query(models.Article)
    
    # Apply filters if provided
    if search:
        query = query.filter(
            or_(
                models.Article.title.ilike(f"%{search}%"),
                models.Article.content.ilike(f"%{search}%"),
                models.Article.description.ilike(f"%{search}%")
            )
        )
    if news_source:
        query = query.filter(models.Article.news_source == news_source)
    if language:
        query = query.filter(models.Article.language == language)
    
    # Apply sorting if provided
    if sort == "date_asc":
        query = query.order_by(models.Article.published_date.asc())
    elif sort == "date_desc":
        query = query.order_by(models.Article.published_date.desc())
    elif sort == "title_asc":
        query = query.order_by(models.Article.title.asc())
    elif sort == "title_desc":
        query = query.order_by(models.Article.title.desc())
    else:
        # Default sorting by published date (newest first)
        query = query.order_by(models.Article.published_date.desc())
    
    # Get all articles with filters applied (no pagination for export)
    articles = query.all()
    
    # Create a CSV output
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write CSV header
    writer.writerow([
        'ID', 'Title', 'Source', 'Published Date', 'Language', 'URL', 
        'Author', 'Description', 'Topics', 'Keywords'
    ])
    
    # Write article data
    for article in articles:
        # Format lists and dates for CSV export
        topics = ', '.join(article.topics) if article.topics and isinstance(article.topics, list) else ''
        keywords = ', '.join(article.keywords) if article.keywords and isinstance(article.keywords, list) else ''
        published_date = article.published_date.strftime('%Y-%m-%d') if article.published_date else ''
        
        writer.writerow([
            str(article.id),
            article.title,
            article.news_source or '',
            published_date,
            article.language or '',
            article.url or '',
            article.author or '',
            article.description or '',
            topics,
            keywords
        ])
    
    # Prepare the response
    output.seek(0)
    
    # Generate a filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"articles_export_{timestamp}.csv"
    
    # Log the export
    logger.info(f"Exported {len(articles)} articles to CSV by admin {current_admin.username}")
    
    # Return the CSV file as a downloadable attachment
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )

@router.get("/articles", response_class=HTMLResponse)
async def list_articles(
    request: Request,
    search: str = None,
    news_source: str = None,
    language: str = None,
    sort: str = None,
    page: int = 1,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    """List all articles with filtering options."""
    # Setup logging
    logger = logging.getLogger(__name__)
    
    # Track if we used advanced search
    used_advanced_search = False
    search_results = []
    
    # Start building the query
    query = db.query(models.Article)
    articles = []
    total_articles = 0
    total_pages = 1
    
    # Apply filters if provided
    if search and len(search) > 3:
        try:
            # Import required modules
            import unicodedata
            
            # Use advanced search with similarity
            used_advanced_search = True
            logger.info(f"Using advanced search for query: {search}")
            
            # Make sure pg_trgm extension is enabled
            db.execute(text('CREATE EXTENSION IF NOT EXISTS pg_trgm;'))
            
            # Set similarity threshold
            similarity_threshold = 0.1  # Lower threshold for more results
            
            # Normalize the query - consistent with search_term in api_endpoints.py
            query_normalized = ''.join(e for e in search if e.isalnum() or e.isspace()).lower()
            query_normalized = unicodedata.normalize("NFKD", query_normalized).encode("ASCII", "ignore").decode("utf-8")
            
            # Build the query
            similarity_query = select(
                models.Article,
                func.similarity(models.Article.title, search).label('similarity_score')
            ).filter(
                or_(
                    func.similarity(models.Article.title, search) > similarity_threshold,
                    models.Article.title.ilike(f"%{search}%"),
                    models.Article.content.ilike(f"%{search}%"), 
                    models.Article.description.ilike(f"%{search}%")
                )
            )
            
            # Apply additional filters
            if news_source:
                similarity_query = similarity_query.filter(models.Article.news_source == news_source)
            if language:
                similarity_query = similarity_query.filter(models.Article.language == language)
                
            # Apply sorting based on similarity
            similarity_query = similarity_query.order_by(
                func.similarity(models.Article.title, search).desc()
            )
            
            # Execute the query and get all matching articles
            result = db.execute(similarity_query).all()
            
            # Process results
            articles_with_scores = [(article, score) for article, score in result]
            
            # Count total articles for pagination
            total_articles = len(articles_with_scores)
            total_pages = (total_articles + limit - 1) // limit if total_articles > 0 else 1
            
            # Apply pagination manually
            start_idx = (page - 1) * limit
            end_idx = min(start_idx + limit, total_articles)
            paginated_articles = articles_with_scores[start_idx:end_idx]
            
            # Extract articles and scores
            articles = [article for article, _ in paginated_articles]
            
            # Format search results to match search_term function output
            search_results = []
            for article, similarity_score in paginated_articles:
                # Create a simplified URL for the frontend
                short_url = f"/admin/articles/{article.id}"
                
                # Make sure we have a URL
                article_url = article.url if article.url else short_url
                
                # Add the article to results with the same structure as search_term
                search_results.append({
                    "id": str(article.id),
                    "title": article.title,
                    "similarity": float(similarity_score),
                    "url": article_url,
                    "short_url": short_url,
                    "published_date": article.published_date.strftime('%Y-%m-%d') if article.published_date else None,
                    "author": article.author or "Unknown",
                    "description": article.description or "No description available",
                    "key_words": article.keywords if hasattr(article, 'keywords') and article.keywords else []
                })
            
            logger.info(f"Advanced search found {total_articles} results")
            
        except Exception as e:
            logger.error(f"Error in advanced search: {str(e)}")
            used_advanced_search = False
            # Fall back to standard search if advanced search fails
            
    # Use standard search if:
    # 1. No search term provided
    # 2. Search term is too short
    # 3. Advanced search failed
    if not used_advanced_search:
        # Apply filters
        if search:
            query = query.filter(
                or_(
                    models.Article.title.ilike(f"%{search}%"),
                    models.Article.content.ilike(f"%{search}%"),
                    models.Article.description.ilike(f"%{search}%")
                )
            )
        if news_source:
            query = query.filter(models.Article.news_source == news_source)
        if language:
            query = query.filter(models.Article.language == language)
        
        # Apply sorting if provided
        if sort == "date_asc":
            query = query.order_by(models.Article.published_date.asc())
        elif sort == "date_desc":
            query = query.order_by(models.Article.published_date.desc())
        elif sort == "title_asc":
            query = query.order_by(models.Article.title.asc())
        elif sort == "title_desc":
            query = query.order_by(models.Article.title.desc())
        else:
            # Default sorting by published date (newest first)
            query = query.order_by(models.Article.published_date.desc())
        
        # Count total articles for pagination
        total_articles = query.count()
        total_pages = (total_articles + limit - 1) // limit if total_articles > 0 else 1
        
        # Apply pagination
        articles = query.offset((page - 1) * limit).limit(limit).all()
    
    # Get unique sources and languages for filter dropdowns
    sources = db.query(models.Article.news_source).distinct().all()
    languages = db.query(models.Article.language).distinct().all()
    
    # Construct pagination URL
    pagination_url = f"/admin/articles?news_source={news_source or ''}&language={language or ''}&search={search or ''}"
    
    return templates.TemplateResponse(
        "admin/articles.html",
        {
            "request": request,
            "articles": articles,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
            "total_articles": total_articles,
            "search": search,
            "news_source": news_source,
            "language": language,
            "sort": sort,
            "sources": sources,
            "languages": languages,
            "pagination_url": pagination_url,
            "used_advanced_search": used_advanced_search,
            "search_results": search_results
        }
    )

@router.get("/articles/{article_id}", response_class=HTMLResponse)
async def get_article(
    request: Request,
    article_id: str,
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    """Display article details."""
    article = db.query(models.Article).filter(models.Article.id == article_id).first()
    
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    return templates.TemplateResponse(
        "admin/article-detail.html",
        {
            "request": request,
            "article": article
        }
    )

@router.post("/users/{user_id}/status", response_class=HTMLResponse)
async def update_user_status(
    request: Request,
    user_id: int,
    status: str = Form(...),
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user.is_active = (status == 'active')
        db.commit()
        
        # Invalidate dashboard caches
        await invalidate_dashboard_caches(request)
        logger.info(f"Cache invalidated after updating user status: {user_id}")

        return RedirectResponse(
            url=f"/admin/users/{user_id}",
            status_code=302
        )
    except Exception as e:
        logger.error(f"Error updating user status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update user status: {str(e)}"
        )

@router.post("/users/{user_id}/schedule", response_class=HTMLResponse)
async def update_user_schedule(
    request: Request,
    user_id: int,
    schedule: str = Form(...),
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Validate schedule value
        valid_schedules = ['daily', 'weekly', 'monthly', 'immediately']
        if schedule not in valid_schedules:
            raise HTTPException(status_code=400, detail="Invalid schedule value")

        user.schedule = schedule
        db.commit()
        
        # Invalidate dashboard caches
        await invalidate_dashboard_caches(request)
        logger.info(f"Cache invalidated after updating user schedule: {user_id}")

        return RedirectResponse(
            url=f"/admin/users/{user_id}",
            status_code=status.HTTP_302_FOUND
        )
    except Exception as e:
        logger.error(f"Error updating user schedule: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update user schedule: {str(e)}"
        )
@router.get("/admin-users", response_class=HTMLResponse)
async def list_admin_users(
    request: Request,
    search: str = None,
    status: str = None,
    sort: str = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    """List all admin users with filtering options."""
    # Start with a base query
    query = db.query(models.Admin)
    
    # Apply search filter if provided
    if search:
        query = query.filter(
            or_(
                models.Admin.username.ilike(f"%{search}%"),
                models.Admin.email.ilike(f"%{search}%")
            )
        )
    
    # Apply status filter if provided
    if status:
        is_active = status == "active"
        query = query.filter(models.Admin.is_active == is_active)
    
    # Apply sorting if provided
    if sort:
        if sort == "id_asc":
            query = query.order_by(models.Admin.id.asc())
        elif sort == "id_desc":
            query = query.order_by(models.Admin.id.desc())
        elif sort == "username_asc":
            query = query.order_by(models.Admin.username.asc())
        elif sort == "username_desc":
            query = query.order_by(models.Admin.username.desc())
        else:
            query = query.order_by(models.Admin.id.asc())
    else:
        # Default sorting
        query = query.order_by(models.Admin.id.asc())
    
    # Apply pagination
    admins = query.offset(skip).limit(limit).all()
    
    return templates.TemplateResponse(
        "admin/admin-users.html",
        {"request": request, "admins": admins}
    )


@router.post("/admin-users/create", response_class=HTMLResponse)
async def create_admin_user(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    role: str = Form(...),
    is_active: str = Form(...),
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    """Create a new admin user."""
    # Get all admins for potential error response
    all_admins = db.query(models.Admin).all()
    
    # Check if the admin already exists
    existing_admin = db.query(models.Admin).filter(
        or_(
            models.Admin.username == username,
            models.Admin.email == email
        )
    ).first()
    
    if existing_admin:
        # Redirect back with error
        return templates.TemplateResponse(
            "admin/admin-users.html",
            {
                "request": request,
                "admins": all_admins,
                "error": f"Admin with that username or email already exists."
            }
        )
    
    # Check if passwords match
    if password != confirm_password:
        return templates.TemplateResponse(
            "admin/admin-users.html",
            {
                "request": request,
                "admins": all_admins,
                "error": "Passwords do not match."
            }
        )
    
    # Check password length
    if len(password) < 6:
        return templates.TemplateResponse(
            "admin/admin-users.html",
            {
                "request": request,
                "admins": all_admins,
                "error": "Password must be at least 6 characters long."
            }
        )
    
    # Create the new admin
    new_admin = models.Admin(
        username=username,
        email=email,
        hashed_password=get_password_hash(password),
        role=role,
        is_active=is_active.lower() == "true"
    )
    
    db.add(new_admin)
    db.commit()
    db.refresh(new_admin)
    
    return RedirectResponse(url="/admin/admin-users", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/admin-users/{admin_id}", response_class=HTMLResponse)
async def get_admin_user(
    request: Request,
    admin_id: int,
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    """Get admin user details."""
    admin_user = db.query(models.Admin).filter(models.Admin.id == admin_id).first()
    if not admin_user:
        raise HTTPException(status_code=404, detail="Admin user not found")
    
    return templates.TemplateResponse(
        "admin/admin-user-detail.html",
        {"request": request, "admin_user": admin_user}
    )


@router.post("/admin-users/{admin_id}/role", response_class=RedirectResponse)
async def update_admin_role(
    request: Request,
    admin_id: int,
    role: str = Form(...),
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    """Update admin user role."""
    admin_user = db.query(models.Admin).filter(models.Admin.id == admin_id).first()
    if not admin_user:
        raise HTTPException(status_code=404, detail="Admin user not found")
    
    # Don't allow changing your own role
    if admin_user.id == current_admin.id:
        return RedirectResponse(
            url=f"/admin/admin-users/{admin_id}?error=Cannot change your own role",
            status_code=status.HTTP_303_SEE_OTHER
        )
    
    admin_user.role = role
    db.commit()
    
    return RedirectResponse(url=f"/admin/admin-users/{admin_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/admin-users/{admin_id}/status", response_class=RedirectResponse)
async def update_admin_status(
    request: Request,
    admin_id: int,
    is_active: str = Form(...),
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    """Update admin user status."""
    admin_user = db.query(models.Admin).filter(models.Admin.id == admin_id).first()
    if not admin_user:
        raise HTTPException(status_code=404, detail="Admin user not found")
    
    # Don't allow deactivating yourself
    if admin_user.id == current_admin.id:
        return RedirectResponse(
            url=f"/admin/admin-users/{admin_id}?error=Cannot change your own status",
            status_code=status.HTTP_303_SEE_OTHER
        )
    
    admin_user.is_active = is_active.lower() == "true"
    db.commit()
    
    return RedirectResponse(url=f"/admin/admin-users/{admin_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/admin-users/{admin_id}/reset-password", response_class=RedirectResponse)
async def reset_admin_password(
    request: Request,
    admin_id: int,
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    """Reset admin user password."""
    admin_user = db.query(models.Admin).filter(models.Admin.id == admin_id).first()
    if not admin_user:
        raise HTTPException(status_code=404, detail="Admin user not found")
    
    # Verify passwords match
    if new_password != confirm_password:
        return RedirectResponse(
            url=f"/admin/admin-users/{admin_id}?error=Passwords do not match",
            status_code=status.HTTP_303_SEE_OTHER
        )
    
    # Check password length
    if len(new_password) < 6:
        return RedirectResponse(
            url=f"/admin/admin-users/{admin_id}?error=Password must be at least 6 characters long",
            status_code=status.HTTP_303_SEE_OTHER
        )
    
    admin_user.hashed_password = get_password_hash(new_password)
    db.commit()
    
    return RedirectResponse(
        url=f"/admin/admin-users/{admin_id}?success=Password updated successfully",
        status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/admin-users/{admin_id}/delete", response_class=RedirectResponse)
async def delete_admin_user(
    request: Request,
    admin_id: int,
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    """Delete admin user."""
    admin_user = db.query(models.Admin).filter(models.Admin.id == admin_id).first()
    if not admin_user:
        raise HTTPException(status_code=404, detail="Admin user not found")
    
    # Don't allow deleting yourself
    if admin_user.id == current_admin.id:
        return RedirectResponse(
            url=f"/admin/admin-users/{admin_id}?error=Cannot delete your own account",
            status_code=status.HTTP_303_SEE_OTHER
        )
    
    db.delete(admin_user)
    db.commit()
    
    return RedirectResponse(url="/admin/admin-users", status_code=status.HTTP_303_SEE_OTHER)
