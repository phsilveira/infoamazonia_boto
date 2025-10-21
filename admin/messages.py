"""
Messages management module for admin panel.
Handles message templates, scheduling, and message history operations.
"""

from fastapi import APIRouter, Form
from fastapi.responses import StreamingResponse
from .base import *
import csv
import io

router = APIRouter()

@router.get("", response_class=HTMLResponse)
async def messages_page(
    request: Request,
    page: int = 1,
    page_size: int = 50,
    message_type: str = None,
    status: str = None,
    phone_number: str = None,
    date_from: str = None,
    date_to: str = None,
    sort: str = None,
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    # Define filter options
    message_type_options = ['incoming', 'outgoing']
    status_options = ['sent', 'delivered', 'read', 'received', 'failed']
    sort_options = [
        ('created_at_desc', 'Criado Em (Mais Recente)'),
        ('created_at_asc', 'Criado Em (Mais Antigo)'),
        ('phone_number_asc', 'Número de Telefone (A-Z)'),
        ('phone_number_desc', 'Número de Telefone (Z-A)'),
        ('content_asc', 'Conteúdo (A-Z)'),
        ('content_desc', 'Conteúdo (Z-A)')
    ]
    
    # Start with base query
    query = db.query(models.Message)
    
    # Apply filters
    if message_type and message_type != "all":
        query = query.filter(models.Message.message_type == message_type)
    
    if status and status != "all":
        query = query.filter(models.Message.status == status)
    
    if phone_number:
        query = query.join(models.User).filter(models.User.phone_number.ilike(f"%{phone_number}%"))
    
    # Apply date range filter
    if date_from:
        try:
            from datetime import datetime
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(models.Message.created_at >= date_from_obj)
        except ValueError:
            pass
    
    if date_to:
        try:
            from datetime import datetime
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
            # Add one day to include the entire end date
            from datetime import timedelta
            date_to_obj = date_to_obj + timedelta(days=1)
            query = query.filter(models.Message.created_at < date_to_obj)
        except ValueError:
            pass
    
    # Apply sorting
    if sort == 'created_at_asc':
        query = query.order_by(models.Message.created_at.asc())
    elif sort == 'phone_number_asc':
        query = query.order_by(models.Message.phone_number.asc())
    elif sort == 'phone_number_desc':
        query = query.order_by(models.Message.phone_number.desc())
    elif sort == 'content_asc':
        query = query.order_by(models.Message.message_content.asc())
    elif sort == 'content_desc':
        query = query.order_by(models.Message.message_content.desc())
    else:  # Default: created_at_desc
        query = query.order_by(desc(models.Message.created_at))
    
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
            "total_messages": total_messages,
            "page": page,
            "message_type": message_type,
            "status": status,
            "phone_number": phone_number,
            "date_from": date_from,
            "date_to": date_to,
            "sort": sort,
            "message_type_options": message_type_options,
            "status_options": status_options,
            "sort_options": sort_options
        }
    )

@router.get("/export")
async def export_messages(
    request: Request,
    message_type: str = None,
    status: str = None,
    phone_number: str = None,
    date_from: str = None,
    date_to: str = None,
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    """Export messages to CSV file"""
    from datetime import datetime, timedelta
    
    # Start with base query
    query = db.query(models.Message)
    
    # Apply filters
    if message_type and message_type != "all":
        query = query.filter(models.Message.message_type == message_type)
    
    if status and status != "all":
        query = query.filter(models.Message.status == status)
    
    if phone_number:
        query = query.join(models.User).filter(models.User.phone_number.ilike(f"%{phone_number}%"))
    
    # Apply date range filter
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(models.Message.created_at >= date_from_obj)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
            date_to_obj = date_to_obj + timedelta(days=1)
            query = query.filter(models.Message.created_at < date_to_obj)
        except ValueError:
            pass
    
    # Order by creation date (newest first)
    query = query.order_by(desc(models.Message.created_at))
    
    # Get all results
    messages = query.all()
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'ID',
        'ID WhatsApp',
        'Número de Telefone',
        'Tipo',
        'Status',
        'Conteúdo',
        'Criado Em',
        'Timestamp do Status'
    ])
    
    # Write data rows
    for message in messages:
        writer.writerow([
            message.id,
            message.whatsapp_message_id or '-',
            message.phone_number,
            message.message_type,
            message.status or 'desconhecido',
            message.message_content,
            message.created_at.strftime('%d/%m/%Y %H:%M:%S'),
            message.status_timestamp.strftime('%d/%m/%Y %H:%M:%S') if message.status_timestamp else 'N/D'
        ])
    
    # Prepare the response
    output.seek(0)
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"mensagens_boto_{timestamp}.csv"
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
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
            user_message = models.Message(
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