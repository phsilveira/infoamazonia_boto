from fastapi import APIRouter, Depends, HTTPException, Request, Form, Query, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import List, Optional
import logging
from pydantic import BaseModel, EmailStr

from database import get_db
import models
import auth
from auth import get_current_admin
from cache_utils import invalidate_dashboard_caches

router = APIRouter(prefix="/admin-management", tags=["admin_management"])

# Get Jinja2 templates
templates = Jinja2Templates(directory="templates")

logger = logging.getLogger(__name__)

# Pydantic models for data validation
class AdminCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: str
    
class AdminUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None

class AdminResponse(BaseModel):
    id: int
    username: str
    email: str
    role: str
    is_active: bool
    
    class Config:
        from_attributes = True

# Admin management UI routes
@router.get("/admins", response_class=HTMLResponse)
async def admin_list(
    request: Request,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    """Display list of admin users with management options"""
    # Check if current admin has appropriate role
    if current_admin.role != "superadmin":
        raise HTTPException(status_code=403, detail="Not authorized to view admin list")
    
    admins = db.query(models.Admin).offset(skip).limit(limit).all()
    
    return templates.TemplateResponse(
        "admin/admin_list.html",
        {"request": request, "admins": admins, "current_admin": current_admin}
    )

@router.get("/admins/create", response_class=HTMLResponse)
async def create_admin_form(
    request: Request,
    current_admin: models.Admin = Depends(get_current_admin)
):
    """Display form to create a new admin user"""
    # Check if current admin has appropriate role
    if current_admin.role != "superadmin":
        raise HTTPException(status_code=403, detail="Not authorized to create admins")
    
    return templates.TemplateResponse(
        "admin/admin_create.html",
        {"request": request, "current_admin": current_admin}
    )

@router.post("/admins/create", response_class=HTMLResponse)
async def create_admin(
    request: Request,
    username: str = Form(...),
    email: EmailStr = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    """Create a new admin user"""
    # Check if current admin has appropriate role
    if current_admin.role != "superadmin":
        raise HTTPException(status_code=403, detail="Not authorized to create admins")
    
    # Check if username or email already exists
    existing_admin = db.query(models.Admin).filter(
        (models.Admin.username == username) | (models.Admin.email == email)
    ).first()
    
    if existing_admin:
        return templates.TemplateResponse(
            "admin/admin_create.html",
            {
                "request": request,
                "error": "Username or email already exists",
                "username": username,
                "email": email,
                "role": role,
                "current_admin": current_admin
            }
        )
    
    # Create new admin
    hashed_password = auth.get_password_hash(password)
    new_admin = models.Admin(
        username=username,
        email=email,
        hashed_password=hashed_password,
        role=role,
        is_active=True
    )
    
    db.add(new_admin)
    db.commit()
    db.refresh(new_admin)
    
    # Redirect to admin list with success message
    response = RedirectResponse(url="/admin-management/admins", status_code=status.HTTP_302_FOUND)
    return response

@router.get("/admins/{admin_id}/edit", response_class=HTMLResponse)
async def edit_admin_form(
    request: Request,
    admin_id: int,
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    """Display form to edit an admin user"""
    # Check if current admin has appropriate role or is editing themselves
    if current_admin.role != "superadmin" and current_admin.id != admin_id:
        raise HTTPException(status_code=403, detail="Not authorized to edit this admin")
    
    admin = db.query(models.Admin).filter(models.Admin.id == admin_id).first()
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found")
    
    return templates.TemplateResponse(
        "admin/admin_edit.html",
        {"request": request, "admin": admin, "current_admin": current_admin}
    )

@router.post("/admins/{admin_id}/edit", response_class=HTMLResponse)
async def update_admin(
    request: Request,
    admin_id: int,
    username: str = Form(...),
    email: EmailStr = Form(...),
    role: str = Form(...),
    is_active: bool = Form(False),
    password: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    """Update an admin user"""
    # Check if current admin has appropriate role or is editing themselves
    if current_admin.role != "superadmin" and current_admin.id != admin_id:
        raise HTTPException(status_code=403, detail="Not authorized to edit this admin")
    
    # Get the admin to edit
    admin = db.query(models.Admin).filter(models.Admin.id == admin_id).first()
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found")
    
    # Check if username or email already exists for another admin
    existing_admin = db.query(models.Admin).filter(
        ((models.Admin.username == username) | (models.Admin.email == email)) &
        (models.Admin.id != admin_id)
    ).first()
    
    if existing_admin:
        return templates.TemplateResponse(
            "admin/admin_edit.html",
            {
                "request": request,
                "admin": admin,
                "error": "Username or email already exists for another admin",
                "current_admin": current_admin
            }
        )
    
    # Update admin fields
    admin.username = username
    admin.email = email
    
    # Only superadmins can change roles and active status
    if current_admin.role == "superadmin":
        admin.role = role
        admin.is_active = is_active
    
    # Update password if provided
    if password:
        admin.hashed_password = auth.get_password_hash(password)
    
    db.commit()
    
    # Redirect to admin list with success message
    response = RedirectResponse(url="/admin-management/admins", status_code=status.HTTP_302_FOUND)
    return response

@router.get("/admins/{admin_id}/delete", response_class=HTMLResponse)
async def delete_admin_confirmation(
    request: Request,
    admin_id: int,
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    """Display confirmation page for admin deletion"""
    # Check if current admin has appropriate role
    if current_admin.role != "superadmin":
        raise HTTPException(status_code=403, detail="Not authorized to delete admins")
    
    # Cannot delete yourself
    if current_admin.id == admin_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    
    admin = db.query(models.Admin).filter(models.Admin.id == admin_id).first()
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found")
    
    return templates.TemplateResponse(
        "admin/admin_delete.html",
        {"request": request, "admin": admin, "current_admin": current_admin}
    )

@router.post("/admins/{admin_id}/delete", response_class=HTMLResponse)
async def delete_admin(
    request: Request,
    admin_id: int,
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    """Delete an admin user"""
    # Check if current admin has appropriate role
    if current_admin.role != "superadmin":
        raise HTTPException(status_code=403, detail="Not authorized to delete admins")
    
    # Cannot delete yourself
    if current_admin.id == admin_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    
    admin = db.query(models.Admin).filter(models.Admin.id == admin_id).first()
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found")
    
    db.delete(admin)
    db.commit()
    
    # Redirect to admin list with success message
    response = RedirectResponse(url="/admin-management/admins", status_code=status.HTTP_302_FOUND)
    return response

# Add these API endpoints if you need programmatic access

@router.get("/api/admins", response_model=List[AdminResponse])
async def get_admins(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    """Get list of admin users (API endpoint)"""
    # Only superadmins can list all admins
    if current_admin.role != "superadmin":
        raise HTTPException(status_code=403, detail="Not authorized to list admin users")
    
    admins = db.query(models.Admin).offset(skip).limit(limit).all()
    return admins

@router.post("/api/admins", response_model=AdminResponse)
async def create_admin_api(
    admin: AdminCreate,
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    """Create a new admin user (API endpoint)"""
    # Only superadmins can create admins
    if current_admin.role != "superadmin":
        raise HTTPException(status_code=403, detail="Not authorized to create admin users")
    
    # Check if username or email already exists
    existing_admin = db.query(models.Admin).filter(
        (models.Admin.username == admin.username) | (models.Admin.email == admin.email)
    ).first()
    
    if existing_admin:
        raise HTTPException(status_code=400, detail="Username or email already registered")
    
    # Create new admin
    hashed_password = auth.get_password_hash(admin.password)
    new_admin = models.Admin(
        username=admin.username,
        email=admin.email,
        hashed_password=hashed_password,
        role=admin.role,
        is_active=True
    )
    
    db.add(new_admin)
    db.commit()
    db.refresh(new_admin)
    
    return new_admin

@router.get("/api/admins/{admin_id}", response_model=AdminResponse)
async def get_admin(
    admin_id: int,
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    """Get a specific admin user (API endpoint)"""
    # Admins can only view their own details unless they're superadmins
    if current_admin.role != "superadmin" and current_admin.id != admin_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this admin")
    
    admin = db.query(models.Admin).filter(models.Admin.id == admin_id).first()
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found")
    
    return admin

@router.put("/api/admins/{admin_id}", response_model=AdminResponse)
async def update_admin_api(
    admin_id: int,
    admin_update: AdminUpdate,
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    """Update an admin user (API endpoint)"""
    # Admins can only update their own details unless they're superadmins
    if current_admin.role != "superadmin" and current_admin.id != admin_id:
        raise HTTPException(status_code=403, detail="Not authorized to update this admin")
    
    admin = db.query(models.Admin).filter(models.Admin.id == admin_id).first()
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found")
    
    # Check for username or email conflicts
    if admin_update.username or admin_update.email:
        existing_admin = db.query(models.Admin).filter(
            ((models.Admin.username == admin_update.username) | 
             (models.Admin.email == admin_update.email)) &
            (models.Admin.id != admin_id)
        ).first()
        
        if existing_admin:
            raise HTTPException(status_code=400, detail="Username or email already exists")
    
    # Update fields if provided
    if admin_update.username:
        admin.username = admin_update.username
    if admin_update.email:
        admin.email = admin_update.email
    if admin_update.password:
        admin.hashed_password = auth.get_password_hash(admin_update.password)
    
    # Only superadmins can change roles and active status
    if current_admin.role == "superadmin":
        if admin_update.role:
            admin.role = admin_update.role
        if admin_update.is_active is not None:
            admin.is_active = admin_update.is_active
    
    db.commit()
    db.refresh(admin)
    
    return admin

@router.delete("/api/admins/{admin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin_api(
    admin_id: int,
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    """Delete an admin user (API endpoint)"""
    # Only superadmins can delete admins
    if current_admin.role != "superadmin":
        raise HTTPException(status_code=403, detail="Not authorized to delete admin users")
    
    # Cannot delete yourself
    if current_admin.id == admin_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    
    admin = db.query(models.Admin).filter(models.Admin.id == admin_id).first()
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found")
    
    db.delete(admin)
    db.commit()
    
    return None