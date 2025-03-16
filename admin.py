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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="templates")

# Existing view endpoints remain unchanged
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
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    templates_list = db.query(models.MessageTemplate).all()
    scheduled_messages = db.query(models.ScheduledMessage).order_by(models.ScheduledMessage.scheduled_time.desc()).all()
    hello_world_template = db.query(models.MessageTemplate).filter(models.MessageTemplate.name == "hello_world").first()

    return templates.TemplateResponse(
        "admin/messages.html",
        {
            "request": request,
            "message_templates": templates_list,
            "scheduled_messages": scheduled_messages,
            "hello_world_template": hello_world_template
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