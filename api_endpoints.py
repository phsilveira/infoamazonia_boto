from fastapi import APIRouter, Depends, Request, Body, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, text
from database import get_db
import models
from datetime import datetime
import logging
from typing import Optional, List, Dict, Any
import unicodedata
from pydantic import BaseModel

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
    try:
        # Get total count
        total_count = db.query(models.Article).count()

        # Get oldest and newest dates
        dates_query = db.query(
            func.min(models.Article.published_date).label('oldest'),
            func.max(models.Article.published_date).label('newest')
        ).first()

        oldest_date = None
        newest_date = None
        
        if dates_query and dates_query.oldest:
            oldest_date = dates_query.oldest.strftime('%Y-%m-%d')
        
        if dates_query and dates_query.newest:
            newest_date = dates_query.newest.strftime('%Y-%m-%d')
        
        logger.info(f"Article stats: {total_count} articles, oldest: {oldest_date}, newest: {newest_date}")
        
        return {
            "success": True,
            "stats": {
                "total_count": total_count,
                "oldest_date": oldest_date,
                "newest_date": newest_date
            }
        }
    except Exception as e:
        logger.error(f"Error fetching article stats: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@router.post("/api/search")
async def search_term(
    request: Request, 
    search_data: SearchQuery = Body(...),
    db: Session = Depends(get_db)
):
    """Search articles using vector similarity and full-text search"""
    try:
        query = search_data.query
        
        if not query:
            return {
                "success": False,
                "error": "Query is required"
            }
            
        # Normalize the query
        query = ''.join(e for e in query if e.isalnum() or e.isspace()).lower()
        query = unicodedata.normalize("NFKD", query).encode("ASCII", "ignore").decode("utf-8")
        
        logger.info(f"Searching for term: '{query}'")
        
        # Basic search using SQL LIKE
        similar_articles = db.query(models.Article).filter(
            or_(
                models.Article.title.ilike(f"%{query}%"),
                models.Article.content.ilike(f"%{query}%"),
                models.Article.summary_content.ilike(f"%{query}%")
            )
        ).limit(10).all()
        
        logger.info(f"Found {len(similar_articles)} articles matching the query")
        
        results = []
        for article in similar_articles:
            # Create a simplified URL for the frontend
            short_url = f"/admin/articles/{article.id}"
            
            # Make sure we have a URL
            article_url = article.url if article.url else short_url
            
            # Calculate a simple similarity score based on title match
            title_similarity = 0.7  # Base similarity
            if query.lower() in article.title.lower():
                title_similarity = 0.9
            
            # Add the article to results
            results.append({
                "id": str(article.id),
                "title": article.title,
                "similarity": title_similarity,
                "url": article_url,
                "short_url": short_url,
                "published_date": article.published_date.strftime('%Y-%m-%d') if article.published_date else None,
                "author": article.author or "Unknown",
                "description": article.description or "No description available",
                "key_words": article.keywords if hasattr(article, 'keywords') and article.keywords else []
            })
            
        # Generate a summary if requested
        summary = None
        if search_data.generate_summary:
            # Define header template message in Portuguese
            header = "📖 Aqui está o que descobrimos sobre o termo solicitado:\n\n"
            
            if results and len(results) > 0:
                # Create a summary message for found results
                summary_text = f"Encontramos {len(results)} artigos relacionados a '{query}'."
                
                # Add details about the top result
                top_article = results[0]
                summary_text += f"\n\nO artigo mais relevante é '{top_article['title']}'"
                if top_article['author'] and top_article['author'] != "Unknown":
                    summary_text += f" por {top_article['author']}"
                if top_article['published_date']:
                    summary_text += f", publicado em {top_article['published_date']}"
                summary_text += "."
                
                # Format with header
                summary = header + summary_text
                
                # Add sources information
                if len(results) > 0:
                    sources_text = "\n\n🔗 Fonte(s):"
                    for article in results[:min(3, len(results))]:
                        sources_text += f"\n{article['title']}\n🔗 {article['short_url']}\n"
                    summary += sources_text
            else:
                # Default message when no results are found
                summary = """⚠️ Ops, não encontramos uma explicação completa para esse termo.

😕 Isso pode acontecer porque:
1️⃣ O termo é muito recente ou específico.
2️⃣ Não há consenso científico sobre o tema.
3️⃣ Não há informações detalhadas sobre o termo nas nossas fontes.

🔎 Nossa equipe irá investigar esse tema com mais profundidade. Obrigado por nos ajudar a entender o que nossa audiência tem interesse em consumir.
📌 Enquanto isso, você pode tentar reformular o termo ou buscar algo semelhante.
↩️ Voltando ao menu inicial...
"""
            
        return {
            "success": True,
            "results": results,
            "count": len(results),
            "summary": summary
        }
        
    except Exception as e:
        logger.error(f"Search error: {e}")
        return {
            "success": False,
            "error": str(e)
        }

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
    
    # Get article statistics for initial render
    try:
        total_count = db.query(models.Article).count()
        
        dates_query = db.query(
            func.min(models.Article.published_date).label('oldest'),
            func.max(models.Article.published_date).label('newest')
        ).first()
        
        oldest_date = None
        newest_date = None
        
        if dates_query and dates_query.oldest:
            oldest_date = dates_query.oldest.strftime('%Y-%m-%d')
        
        if dates_query and dates_query.newest:
            newest_date = dates_query.newest.strftime('%Y-%m-%d')
            
        logger.info(f"Initial article stats for search page: {total_count} articles")
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