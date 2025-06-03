from fastapi import APIRouter, Depends, Request, Body, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from database import get_db
import models
from datetime import datetime
import logging
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from services.search_fastapi import (
    search_term_vector, 
    search_articles_similarity, 
    get_article_stats as search_get_article_stats,
    get_ctr_stats as search_get_ctr_stats,
    redirect_to_article
)

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
    result = await search_get_article_stats(db)
    
    # Convert date format from YYYY-MM-DD to DD/MM/YYYY for display
    if result.get("success") and result.get("stats"):
        stats = result["stats"]
        if stats.get("oldest_date"):
            try:
                from datetime import datetime
                oldest = datetime.strptime(stats["oldest_date"], '%Y-%m-%d')
                stats["oldest_date"] = oldest.strftime('%d/%m/%Y')
            except:
                pass
        if stats.get("newest_date"):
            try:
                from datetime import datetime
                newest = datetime.strptime(stats["newest_date"], '%Y-%m-%d')
                stats["newest_date"] = newest.strftime('%d/%m/%Y')
            except:
                pass
        
        logger.info(f"Article stats: {stats['total_count']} articles, oldest: {stats.get('oldest_date')}, newest: {stats.get('newest_date')}")
    
    return result

@router.post("/api/search")
async def search_term(
    request: Request, 
    search_data: SearchQuery = Body(...),
    db: Session = Depends(get_db)
):
    """Search articles using vector similarity and full-text search"""
    return await search_term_vector(
        query=search_data.query,
        db=db,
        request=request,
        generate_summary=search_data.generate_summary,
        system_prompt=search_data.system_prompt
    )

@router.post("/api/search-articles")
async def search_articles_api(
    request: Request,
    search_data: SearchQuery = Body(...),
    db: Session = Depends(get_db)
):
    """Search articles using fuzzy matching and trigram similarity"""
    return await search_articles_similarity(
        query=search_data.query,
        db=db,
        request=request
    )

@router.get("/api/ctr-stats")
async def get_ctr_stats_api(request: Request):
    """Get Click-Through Rate statistics for all shortened URLs"""
    return await search_get_ctr_stats()

@router.get("/r/{short_id}")
async def redirect_short_url(short_id: str):
    """Redirect to the original article URL with UTM parameters"""
    redirect_url = redirect_to_article(short_id)
    if not redirect_url:
        raise HTTPException(status_code=404, detail="Link expired or not found")
    
    return RedirectResponse(url=redirect_url, status_code=302)

# Endpoint to render the search_articles.html template
@router.get("/search-articles")
async def search_articles_page(request: Request, db: Session = Depends(get_db)):
    """Render the search articles page"""
    from fastapi.templating import Jinja2Templates
    from fastapi.responses import RedirectResponse
    from auth import get_current_admin
    
    # Check if the user is authenticated
    try:
        # Import the auth-related functions
        from auth import get_token_from_cookie, verify_token
        
        # Get the token from cookie
        token = get_token_from_cookie(request)
        if not token:
            return RedirectResponse(url="/login", status_code=302)
        
        # Verify the token
        admin = verify_token(token, db)
        if not admin:
            return RedirectResponse(url="/login", status_code=302)
    except Exception as e:
        logger.error(f"Authentication error in search page: {e}")
        return RedirectResponse(url="/login", status_code=302)
    
    templates = Jinja2Templates(directory="templates")
    
    # Get article statistics using the refactored service
    try:
        stats_result = await search_get_article_stats(db)
        if stats_result.get("success") and stats_result.get("stats"):
            stats = stats_result["stats"]
            total_count = stats.get("total_count", 0)
            oldest_date = stats.get("oldest_date")
            newest_date = stats.get("newest_date")
            
            # Convert date format from YYYY-MM-DD to DD/MM/YYYY for display
            if oldest_date:
                try:
                    oldest = datetime.strptime(oldest_date, '%Y-%m-%d')
                    oldest_date = oldest.strftime('%d/%m/%Y')
                except:
                    pass
            if newest_date:
                try:
                    newest = datetime.strptime(newest_date, '%Y-%m-%d')
                    newest_date = newest.strftime('%d/%m/%Y')
                except:
                    pass
            
            logger.info(f"Initial article stats for search page: {total_count} articles")
        else:
            total_count = 0
            oldest_date = None
            newest_date = None
    except Exception as e:
        logger.error(f"Error fetching initial article stats: {e}")
        total_count = 0
        oldest_date = None
        newest_date = None
    
    # Pass admin to the template
    return templates.TemplateResponse(
        "search_articles.html", 
        {
            "request": request,
            "total_articles": total_count,
            "oldest_date": oldest_date,
            "newest_date": newest_date,
            "current_admin": admin  # Pass the admin user to the template
        }
    )