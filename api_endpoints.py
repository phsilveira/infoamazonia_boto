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
from pydantic import BaseModel, Field

router = APIRouter(
    prefix="/api",
    tags=["API Endpoints"],
    responses={404: {"description": "Not found"}},
)
logger = logging.getLogger(__name__)

class SearchQuery(BaseModel):
    """Search query model for article search requests"""
    query: str = Field(..., description="Search term or phrase to find articles")
    generate_summary: bool = Field(False, description="Whether to generate an AI-powered summary of search results")
    system_prompt: Optional[str] = Field(None, description="Custom system prompt for summary generation")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "mudanças climáticas",
                "generate_summary": True,
                "system_prompt": "Provide a detailed analysis"
            }
        }

class SearchResult(BaseModel):
    """Individual search result model"""
    id: str = Field(..., description="Unique article identifier")
    title: str = Field(..., description="Article title")
    similarity: float = Field(..., description="Similarity score (0.0 to 1.0)")
    url: str = Field(..., description="Original article URL")
    short_url: str = Field(..., description="Internal admin URL for the article")
    published_date: Optional[str] = Field(None, description="Publication date in YYYY-MM-DD format")
    author: Optional[str] = Field(None, description="Article author")
    description: Optional[str] = Field(None, description="Article description or excerpt")
    key_words: Optional[List[str]] = Field(None, description="Article keywords/tags")

class SearchResponse(BaseModel):
    """Search response model containing results and metadata"""
    success: bool = Field(..., description="Whether the search was successful")
    results: List[SearchResult] = Field(default_factory=list, description="List of matching articles")
    count: int = Field(0, description="Number of results found")
    summary: Optional[str] = Field(None, description="AI-generated summary of results (if requested)")
    error: Optional[str] = Field(None, description="Error message if search failed")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "results": [
                    {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "title": "Impactos das Mudanças Climáticas na Amazônia",
                        "similarity": 0.85,
                        "url": "https://example.com/article",
                        "short_url": "/admin/articles/123e4567-e89b-12d3-a456-426614174000",
                        "published_date": "2024-06-15",
                        "author": "João Silva",
                        "description": "Análise detalhada dos efeitos...",
                        "key_words": ["clima", "amazônia", "meio ambiente"]
                    }
                ],
                "count": 1,
                "summary": "Encontrado 1 artigo sobre mudanças climáticas...",
                "error": None
            }
        }

class ArticleStats(BaseModel):
    """Article statistics model"""
    total_count: int = Field(..., description="Total number of articles in database")
    oldest_date: Optional[str] = Field(None, description="Date of oldest article (DD/MM/YYYY format)")
    newest_date: Optional[str] = Field(None, description="Date of newest article (DD/MM/YYYY format)")

class ArticleStatsResponse(BaseModel):
    """Article statistics response model"""
    success: bool = Field(..., description="Whether the request was successful")
    stats: Optional[ArticleStats] = Field(None, description="Article statistics")
    error: Optional[str] = Field(None, description="Error message if request failed")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "stats": {
                    "total_count": 1250,
                    "oldest_date": "15/01/2024",
                    "newest_date": "10/06/2025"
                },
                "error": None
            }
        }

@router.get("/article-stats", 
           response_model=ArticleStatsResponse,
           summary="Get Article Statistics",
           description="Retrieve comprehensive statistics about articles in the database including total count, oldest and newest publication dates")
async def get_article_stats(
    request: Request, 
    db: Session = Depends(get_db)
) -> ArticleStatsResponse:
    """
    Get article statistics for display in admin panel.
    
    Returns:
        ArticleStatsResponse: Statistics including total count and date range
    """
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
            oldest_date = dates_query.oldest.strftime('%d/%m/%Y')
        
        if dates_query and dates_query.newest:
            newest_date = dates_query.newest.strftime('%d/%m/%Y')
        
        logger.info(f"Article stats: {total_count} articles, oldest: {oldest_date}, newest: {newest_date}")
        
        return ArticleStatsResponse(
            success=True,
            stats=ArticleStats(
                total_count=total_count,
                oldest_date=oldest_date,
                newest_date=newest_date
            ),
            error=None
        )
    except Exception as e:
        logger.error(f"Error fetching article stats: {e}")
        return ArticleStatsResponse(
            success=False,
            error=str(e)
        )

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
            oldest_date = dates_query.oldest.strftime('%d/%m/%Y')
        
        if dates_query and dates_query.newest:
            newest_date = dates_query.newest.strftime('%d/%m/%Y')
            
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