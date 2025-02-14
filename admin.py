from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import List
import models
import schemas
from database import get_db
from auth import get_current_admin
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="templates")

@router.get("/users", response_class=HTMLResponse)
async def list_users(
    request: Request,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    users = db.query(models.User).offset(skip).limit(limit).all()
    return templates.TemplateResponse(
        "admin/users.html",
        {"request": request, "users": users}
    )

@router.get("/news-sources", response_model=List[schemas.NewsSource])
async def list_news_sources(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    sources = db.query(models.NewsSource).offset(skip).limit(limit).all()
    return sources

@router.get("/metrics", response_model=List[schemas.Metrics])
async def get_metrics(
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(get_current_admin)
):
    metrics = db.query(models.Metrics).all()
    return metrics