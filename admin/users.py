"""
User management module for admin panel.
Handles all user-related operations including CRUD operations,
location and subject management, and status updates.
"""

from fastapi import APIRouter, Form
from fastapi.responses import StreamingResponse
from .base import *
import csv
import io

router = APIRouter()

@router.post("/create", response_class=HTMLResponse)
async def create_user(
    request: Request,
    phone_number: str = Form(...),
    status: str = Form(...),
    schedule: str = Form(...),
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
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
        await invalidate_caches_and_log(request, "user creation", str(user.id))

        return RedirectResponse(
            url=f"/admin/users/{user.id}",
            status_code=302
        )
    except Exception as e:
        await handle_database_error(e, "user creation")

@router.get("", response_class=HTMLResponse)
async def list_users(
    request: Request,
    phone_number: str = None,
    status: str = None,
    sort: str = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    from sqlalchemy import func, and_
    from sqlalchemy.orm import aliased
    
    # Subquery to get the latest incoming message for each phone number
    latest_message_subquery = (
        db.query(
            models.Message.phone_number,
            func.max(models.Message.created_at).label('max_created_at')
        )
        .filter(models.Message.message_type == 'incoming')
        .group_by(models.Message.phone_number)
        .subquery()
    )
    
    # Alias for Message table to join with subquery
    MessageAlias = aliased(models.Message)
    
    # Main query with left join to get last incoming message
    query = db.query(
        models.User,
        MessageAlias.message_content.label('last_message'),
        MessageAlias.created_at.label('last_message_time')
    ).outerjoin(
        latest_message_subquery,
        models.User.phone_number == latest_message_subquery.c.phone_number
    ).outerjoin(
        MessageAlias,
        and_(
            MessageAlias.phone_number == latest_message_subquery.c.phone_number,
            MessageAlias.created_at == latest_message_subquery.c.max_created_at,
            MessageAlias.message_type == 'incoming'
        )
    )

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

    # Apply pagination and get results
    results = query.offset(skip).limit(limit).all()
    
    # Create a list of user dictionaries with last_message and timestamp
    users_with_messages = []
    for user, last_message, last_message_time in results:
        user_dict = {
            'user': user,
            'last_message': last_message,
            'last_message_time': last_message_time
        }
        users_with_messages.append(user_dict)

    return templates.TemplateResponse(
        "admin/users.html",
        {"request": request, "users": users_with_messages}
    )

@router.get("/export")
async def export_users(
    request: Request,
    phone_number: str = None,
    status: str = None,
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    """Export users to CSV file"""
    from sqlalchemy import func, and_
    from sqlalchemy.orm import aliased
    from datetime import datetime
    
    # Subquery to get the latest incoming message for each phone number
    latest_message_subquery = (
        db.query(
            models.Message.phone_number,
            func.max(models.Message.created_at).label('max_created_at')
        )
        .filter(models.Message.message_type == 'incoming')
        .group_by(models.Message.phone_number)
        .subquery()
    )
    
    # Alias for Message table to join with subquery
    MessageAlias = aliased(models.Message)
    
    # Main query with left join to get last incoming message
    query = db.query(
        models.User,
        MessageAlias.message_content.label('last_message'),
        MessageAlias.created_at.label('last_message_time')
    ).outerjoin(
        latest_message_subquery,
        models.User.phone_number == latest_message_subquery.c.phone_number
    ).outerjoin(
        MessageAlias,
        and_(
            MessageAlias.phone_number == latest_message_subquery.c.phone_number,
            MessageAlias.created_at == latest_message_subquery.c.max_created_at,
            MessageAlias.message_type == 'incoming'
        )
    )

    # Apply filters
    if phone_number:
        query = query.filter(models.User.phone_number.ilike(f"%{phone_number}%"))
    if status == 'active':
        query = query.filter(models.User.is_active == True)
    elif status == 'inactive':
        query = query.filter(models.User.is_active == False)

    # Get all results
    results = query.all()
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'ID',
        'Número de Telefone',
        'Status',
        'Agendamento',
        'Última Mensagem',
        'Data Última Mensagem',
        'Criado Em'
    ])
    
    # Write data rows
    for user, last_message, last_message_time in results:
        writer.writerow([
            user.id,
            user.phone_number,
            'Ativo' if user.is_active else 'Inativo',
            user.schedule or '-',
            last_message or '-',
            last_message_time.strftime('%d/%m/%Y %H:%M:%S') if last_message_time else '-',
            user.created_at.strftime('%d/%m/%Y %H:%M:%S')
        ])
    
    # Prepare the response
    output.seek(0)
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"usuarios_boto_{timestamp}.csv"
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )

@router.get("/{user_id}", response_class=HTMLResponse)
async def get_user(
    request: Request,
    user_id: int,
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
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

@router.post("/{user_id}/subjects", response_class=HTMLResponse)
async def add_user_subject(
    request: Request,
    user_id: int,
    subject_name: str = Form(...),
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    try:
        subject = models.Subject(
            subject_name=subject_name,
            user_id=user_id
        )
        db.add(subject)
        db.commit()
        
        await invalidate_caches_and_log(request, "subject addition", str(user_id))
        
        return RedirectResponse(url=f"/admin/users/{user_id}", status_code=status.HTTP_302_FOUND)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{user_id}/subjects/{subject_id}/delete", response_class=HTMLResponse)
async def delete_user_subject(
    request: Request,
    user_id: int,
    subject_id: int,
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    subject = db.query(models.Subject).filter(
        models.Subject.id == subject_id, 
        models.Subject.user_id == user_id
    ).first()
    if subject:
        db.delete(subject)
        db.commit()
        await invalidate_caches_and_log(request, "subject deletion", str(user_id))
    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=status.HTTP_302_FOUND)

@router.post("/{user_id}/locations/{location_id}/delete", response_class=HTMLResponse)
async def delete_user_location(
    request: Request,
    user_id: int,
    location_id: int,
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    location = db.query(models.Location).filter(
        models.Location.id == location_id, 
        models.Location.user_id == user_id
    ).first()
    if location:
        db.delete(location)
        db.commit()
        await invalidate_caches_and_log(request, "location deletion", str(user_id))
    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=status.HTTP_302_FOUND)

@router.post("/{user_id}/location", response_class=HTMLResponse)
async def add_user_location(
    request: Request,
    user_id: int,
    location_name: str = Form(...),
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
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
            await invalidate_caches_and_log(request, "location addition", str(user_id))
            return RedirectResponse(url=f"/admin/users/{user_id}", status_code=status.HTTP_302_FOUND)

        # Get details for valid locations
        valid_locations = [result[1] for result in validation_results if result[0]]
        if not valid_locations:
            user = db.query(models.User).filter(models.User.id == user_id).first()
            locations = db.query(models.Location).filter(models.Location.user_id == user_id).all()
            subjects = db.query(models.Subject).filter(models.Subject.user_id == user_id).all()
            return templates.TemplateResponse(
                "admin/user_detail.html",
                {
                    "request": request,
                    "user": user,
                    "locations": locations,
                    "subjects": subjects,
                    "error": f"Invalid location: {location_name}. Please enter a valid location."
                }
            )

        location_details = get_location_details(valid_locations)
        for place_id, details in location_details.items():
            if details and 'geometry' in details and 'location' in details['geometry']:
                location = models.Location(
                    location_name=details.get('formatted_address', location_name),
                    latitude=details['geometry']['location']['lat'],
                    longitude=details['geometry']['location']['lng'],
                    user_id=user_id
                )
                db.add(location)

        db.commit()
        await invalidate_caches_and_log(request, "location addition", str(user_id))
        return RedirectResponse(url=f"/admin/users/{user_id}", status_code=status.HTTP_302_FOUND)
        
    except Exception as e:
        logger.error(f"Error adding location: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{user_id}/status", response_class=HTMLResponse)
async def update_user_status(
    request: Request,
    user_id: int,
    user_status: str = Form(..., alias="status"),
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user.is_active = (user_status == 'active')
        db.commit()
        
        await invalidate_caches_and_log(request, "user status update", str(user_id))

        return RedirectResponse(
            url=f"/admin/users/{user_id}",
            status_code=status.HTTP_302_FOUND
        )
    except Exception as e:
        await handle_database_error(e, "user status update")

@router.post("/{user_id}/schedule", response_class=HTMLResponse)
async def update_user_schedule(
    request: Request,
    user_id: int,
    user_schedule: str = Form(..., alias="schedule"),
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user.schedule = user_schedule
        db.commit()
        
        await invalidate_caches_and_log(request, "user schedule update", str(user_id))

        return RedirectResponse(
            url=f"/admin/users/{user_id}",
            status_code=status.HTTP_302_FOUND
        )
    except Exception as e:
        await handle_database_error(e, "user schedule update")

@router.post("/{user_id}/delete")
async def delete_user(
    request: Request,
    user_id: int,
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    """Delete a user and all related data from the database"""
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Delete related data first
        db.query(models.Location).filter(models.Location.user_id == user_id).delete()
        db.query(models.Subject).filter(models.Subject.user_id == user_id).delete()
        db.query(models.UserInteraction).filter(models.UserInteraction.user_id == user_id).delete()
        db.query(models.Message).filter(models.Message.user_id == user_id).delete()
        
        # Finally delete the user
        db.delete(user)
        db.commit()
        
        await invalidate_caches_and_log(request, "user deletion", str(user_id))
        
        return JSONResponse(
            content={"success": True, "message": f"User {user.phone_number} deleted successfully"}
        )
    except Exception as e:
        logger.error(f"Error deleting user {user_id}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"Error deleting user: {str(e)}"}
        )