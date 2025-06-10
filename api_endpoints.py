from fastapi import APIRouter, Depends, Request, Body, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
import logging
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from services.search import get_article_stats_service, search_term_service, search_articles_service, search_articles_page_service

router = APIRouter()
logger = logging.getLogger(__name__)

class SearchQuery(BaseModel):
    query: str
    generate_summary: bool = False
    system_prompt: Optional[str] = None

class SearchResult(BaseModel):
    id: str
    title: str
    similarity: float
    url: str
    short_url: str
    published_date: Optional[str] = None
    author: Optional[str] = None
    description: Optional[str] = None
    key_words: Optional[List[str]] = None

class SearchResponse(BaseModel):
    success: bool
    results: List[SearchResult] = []
    count: int = 0
    summary: Optional[str] = None
    error: Optional[str] = None

@router.get("/api/article-stats")
async def get_article_stats(request: Request, db: Session = Depends(get_db)):
    """Get article statistics for display in admin panel"""
    return await get_article_stats_service(db)

@router.post("/api/search")
async def search_term(
    request: Request, 
    search_data: SearchQuery = Body(...),
    db: Session = Depends(get_db)
):
    """Search articles using vector similarity and full-text search"""
    return await search_term_service(
        query=search_data.query,
        db=db,
        generate_summary=search_data.generate_summary,
        system_prompt=search_data.system_prompt
    )

# Endpoint to render the search_articles.html template
@router.get("/search-articles")
async def search_articles_page(request: Request, db: Session = Depends(get_db)):
    """Render the search articles page"""
    templates = Jinja2Templates(directory="templates")
    
    # Use the page service function to get data
    result = await search_articles_page_service(request, db)
    
    # Handle redirect case
    if "redirect" in result:
        return RedirectResponse(url=result["redirect"], status_code=302)
    
    # Return template response with data from service
    return templates.TemplateResponse(
        "search_articles.html", 
        {
            "request": request,
            "total_articles": result["total_articles"],
            "oldest_date": result["oldest_date"],
            "newest_date": result["newest_date"],
            "current_admin": result["current_admin"]
        }
    )

# Endpoint to search articles with query parameter
@router.post("/api/search-articles")
async def search_articles_api(
    request: Request,
    search_data: dict = Body(...),
    db: Session = Depends(get_db)
):
    """Search articles with query parameter"""
    query = search_data.get('query', '')
    return await search_articles_service(query, db)