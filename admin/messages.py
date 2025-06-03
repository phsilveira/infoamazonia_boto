"""
Messages management module for admin panel.
Handles message templates, scheduling, and message history operations.
"""

from fastapi import APIRouter, Form
from .base import *

router = APIRouter()

@router.get("", response_class=HTMLResponse)
async def messages_page(
    request: Request,
    page: int = 1,
    page_size: int = 10,
    message_type: str = None,
    status: str = None,
    phone_number: str = None,
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    # Start with base query
    query = db.query(models.UserMessage)
    
    # Apply filters
    if message_type and message_type != "all":
        query = query.filter(models.UserMessage.message_type == message_type)
    
    if status and status != "all":
        query = query.filter(models.UserMessage.status == status)
    
    if phone_number:
        query = query.join(models.User).filter(models.User.phone_number.ilike(f"%{phone_number}%"))
    
    # Order by creation date (newest first)
    query = query.order_by(desc(models.UserMessage.created_at))
    
    # Calculate pagination
    total_messages = query.count()
    skip = (page - 1) * page_size
    messages = query.offset(skip).limit(page_size).all()
    
    # Calculate pagination info
    total_pages = (total_messages + page_size - 1) // page_size
    has_prev = page > 1
    has_next = page < total_pages
    prev_page = page - 1 if has_prev else None
    next_page = page + 1 if has_next else None
    
    return templates.TemplateResponse(
        "admin/messages.html",
        {
            "request": request,
            "messages": messages,
            "current_page": page,
            "total_pages": total_pages,
            "has_prev": has_prev,
            "has_next": has_next,
            "prev_page": prev_page,
            "next_page": next_page,
            "page_size": page_size,
            "total_messages": total_messages
        }
    )

@router.post("/template", response_class=HTMLResponse)
async def create_template(
    request: Request,
    name: str = Form(...),
    content: str = Form(...),
    variables: str = Form(...),
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    try:
        template = models.MessageTemplate(
            name=name,
            content=content,
            variables=variables
        )
        db.add(template)
        db.commit()
        
        await invalidate_caches_and_log(request, "template creation")
        
        return RedirectResponse(url="/admin/messages", status_code=302)
    except Exception as e:
        await handle_database_error(e, "template creation")

@router.post("/schedule", response_class=HTMLResponse)
async def schedule_new_message(
    request: Request,
    template_id: int = Form(...),
    schedule_type: str = Form(...),
    scheduled_date: str = Form(None),
    target_group: str = Form(...),
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    try:
        # Get the template
        template = db.query(models.MessageTemplate).filter(models.MessageTemplate.id == template_id).first()
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        
        # Parse scheduled date if provided
        scheduled_datetime = None
        if scheduled_date:
            scheduled_datetime = datetime.fromisoformat(scheduled_date.replace('T', ' '))
        
        # Create scheduled message
        scheduled_message = models.ScheduledMessage(
            template_id=template_id,
            schedule_type=schedule_type,
            scheduled_date=scheduled_datetime,
            target_group=target_group,
            status="pending"
        )
        db.add(scheduled_message)
        db.commit()
        
        await invalidate_caches_and_log(request, "message scheduling")
        
        return RedirectResponse(url="/admin/messages", status_code=302)
    except Exception as e:
        await handle_database_error(e, "message scheduling")

@router.post("/send-template", response_class=HTMLResponse)
async def send_template_message(
    request: Request,
    template_name: str = Form(...),
    language_code: str = Form(...),
    phone_number: str = Form(...),
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    try:
        # Find the user
        user = db.query(models.User).filter(models.User.phone_number == phone_number).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Import WhatsApp service
        from services.whatsapp import WhatsAppService
        whatsapp_service = WhatsAppService()
        
        # Send template message
        result = whatsapp_service.send_template_message(
            phone_number=phone_number,
            template_name=template_name,
            language_code=language_code
        )
        
        if result.get('success'):
            # Log the message
            user_message = models.UserMessage(
                user_id=user.id,
                content=f"Template: {template_name}",
                message_type="template",
                status="sent",
                direction="outbound"
            )
            db.add(user_message)
            db.commit()
            
            await invalidate_caches_and_log(request, "template message send")
            
            return RedirectResponse(url="/admin/messages?success=Message sent successfully", status_code=302)
        else:
            return RedirectResponse(url=f"/admin/messages?error={result.get('error', 'Failed to send message')}", status_code=302)
            
    except Exception as e:
        logger.error(f"Error sending template message: {str(e)}")
        return RedirectResponse(url=f"/admin/messages?error=Failed to send message: {str(e)}", status_code=302)