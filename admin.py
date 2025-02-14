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