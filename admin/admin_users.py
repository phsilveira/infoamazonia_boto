"""
Admin users management module for admin panel.
Handles admin user CRUD operations, role management, and password resets.
"""

from fastapi import APIRouter, Form
from .base import *

router = APIRouter()

@router.get("", response_class=HTMLResponse)
async def list_admin_users(
    request: Request,
    search: str = None,
    status: str = None,
    sort: str = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
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
    
    # Apply status filter
    query = apply_status_filter(query, models.Admin.is_active, status)
    
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
    admins = apply_pagination(query, skip, limit).all()

    return templates.TemplateResponse(
        "admin/admin-users.html",
        {"request": request, "admins": admins}
    )

@router.post("/create", response_class=HTMLResponse)
async def create_admin_user(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    role: str = Form(...),
    is_active: str = Form(...),
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
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
                "error": "Admin with that username or email already exists."
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
    
    try:
        # Create new admin user
        admin_user = models.Admin(
            username=username,
            email=email,
            hashed_password=get_password_hash(password),
            role=role,
            is_active=is_active.lower() == "true"
        )
        db.add(admin_user)
        db.commit()
        
        await invalidate_caches_and_log(request, "admin user creation", str(admin_user.id))
        
        return RedirectResponse(url="/admin/admin-users", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        await handle_database_error(e, "admin user creation")

@router.get("/{admin_id}", response_class=HTMLResponse)
async def get_admin_user(
    request: Request,
    admin_id: int,
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    """Get admin user details."""
    admin_user = db.query(models.Admin).filter(models.Admin.id == admin_id).first()
    if not admin_user:
        raise HTTPException(status_code=404, detail="Admin user not found")
    
    return templates.TemplateResponse(
        "admin/admin-user-detail.html",
        {"request": request, "admin_user": admin_user}
    )

@router.post("/{admin_id}/role", response_class=RedirectResponse)
async def update_admin_role(
    request: Request,
    admin_id: int,
    role: str = Form(...),
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
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
    
    await invalidate_caches_and_log(request, "admin role update", str(admin_id))
    
    return RedirectResponse(url=f"/admin/admin-users/{admin_id}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/{admin_id}/status", response_class=RedirectResponse)
async def update_admin_status(
    request: Request,
    admin_id: int,
    is_active: str = Form(...),
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
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
    
    await invalidate_caches_and_log(request, "admin status update", str(admin_id))
    
    return RedirectResponse(url=f"/admin/admin-users/{admin_id}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/{admin_id}/reset-password", response_class=RedirectResponse)
async def reset_admin_password(
    request: Request,
    admin_id: int,
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    """Reset admin user password."""
    admin_user = db.query(models.Admin).filter(models.Admin.id == admin_id).first()
    if not admin_user:
        raise HTTPException(status_code=404, detail="Admin user not found")
    
    # Check if passwords match
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
    
    try:
        # Update password
        admin_user.hashed_password = get_password_hash(new_password)
        db.commit()
        
        await invalidate_caches_and_log(request, "admin password reset", str(admin_id))
        
        return RedirectResponse(url=f"/admin/admin-users/{admin_id}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        await handle_database_error(e, "admin password reset")

@router.post("/{admin_id}/delete", response_class=RedirectResponse)
async def delete_admin_user(
    request: Request,
    admin_id: int,
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
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
    
    try:
        # Delete the admin user
        db.delete(admin_user)
        db.commit()
        
        await invalidate_caches_and_log(request, "admin user deletion", str(admin_id))
        
        return RedirectResponse(url="/admin/admin-users", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        await handle_database_error(e, "admin user deletion")