from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from sqlalchemy.orm import Session
from typing import List
import models
import schemas
from database import get_db
from auth import get_current_admin
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from datetime import datetime, timezone
import json
import httpx
import logging
from config import settings
from sqlalchemy import desc
from services.chatgpt import ChatGPTService # Fixed import

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="templates")
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
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    sources = db.query(models.NewsSource).offset(skip).limit(limit).all()
    return templates.TemplateResponse(
        "admin/news-sources.html",
        {"request": request, "sources": sources}
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
    category: str,
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    try:
        # Get queries for the specified category
        queries = db.query(models.UserInteraction.query)\
            .filter(models.UserInteraction.category == category)\
            .all()

        # Extract query texts
        query_texts = [q[0] for q in queries]

        if not query_texts:
            return {"summary": "No queries found for this category"}

        # Generate summary using ChatGPT
        summary = await chatgpt_service.summarize_queries(query_texts, category)

        return {"summary": summary}
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