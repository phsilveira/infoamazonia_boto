"""
Articles management module for admin panel.
Handles article listing, search, filtering, and export functionality.
"""

from fastapi import APIRouter, Query
from .base import *

router = APIRouter()

@router.get("/export-csv")
async def export_articles_csv(
    request: Request,
    search: str = None,
    news_source: str = None,
    language: str = None,
    sort: str = None,
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    """Export articles to CSV with current filters applied."""
    try:
        # Build query with same filters as list_articles
        query = db.query(models.Article)
        
        # Apply search filter
        if search:
            query = query.filter(
                or_(
                    models.Article.title.ilike(f"%{search}%"),
                    models.Article.description.ilike(f"%{search}%")
                )
            )
        
        # Apply news source filter
        if news_source and news_source != "all":
            query = query.filter(models.Article.news_source == news_source)
        
        # Apply language filter
        if language and language != "all":
            query = query.filter(models.Article.language == language)
        
        # Apply sorting
        if sort == "title_asc":
            query = query.order_by(models.Article.title.asc())
        elif sort == "title_desc":
            query = query.order_by(models.Article.title.desc())
        elif sort == "date_asc":
            query = query.order_by(models.Article.published_date.asc())
        else:  # Default: newest first
            query = query.order_by(models.Article.published_date.desc())
        
        articles = query.all()
        
        # Create CSV content
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'ID', 'Title', 'Author', 'News Source', 'Language', 
            'Published Date', 'URL', 'Description'
        ])
        
        # Write data
        for article in articles:
            writer.writerow([
                article.id,
                article.title,
                article.author or "Unknown",
                article.news_source,
                article.language,
                article.published_date.strftime('%Y-%m-%d %H:%M:%S') if article.published_date else "N/A",
                article.url,
                article.description[:200] + "..." if article.description and len(article.description) > 200 else article.description or ""
            ])
        
        csv_content = output.getvalue()
        output.close()
        
        # Return CSV response
        response = Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=articles_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"}
        )
        return response
        
    except Exception as e:
        logger.error(f"Error exporting articles: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")

@router.get("", response_class=HTMLResponse)
async def list_articles(
    request: Request,
    search: str = None,
    news_source: str = None,
    language: str = None,
    sort: str = None,
    page: int = 1,
    limit: int = 20,
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    """List all articles with filtering options."""
    # Build query
    query = db.query(models.Article)
    
    # Apply search filter
    if search:
        query = query.filter(
            or_(
                models.Article.title.ilike(f"%{search}%"),
                models.Article.description.ilike(f"%{search}%")
            )
        )
    
    # Apply news source filter
    if news_source and news_source != "all":
        query = query.filter(models.Article.news_source == news_source)
    
    # Apply language filter
    if language and language != "all":
        query = query.filter(models.Article.language == language)
    
    # Apply sorting
    if sort == "title_asc":
        query = query.order_by(models.Article.title.asc())
    elif sort == "title_desc":
        query = query.order_by(models.Article.title.desc())
    elif sort == "date_asc":
        query = query.order_by(models.Article.published_date.asc())
    else:  # Default: newest first
        query = query.order_by(models.Article.published_date.desc())
    
    # Calculate pagination
    total_articles = query.count()
    skip = (page - 1) * limit
    articles = query.offset(skip).limit(limit).all()
    
    # Calculate pagination info
    total_pages = (total_articles + limit - 1) // limit
    has_prev = page > 1
    has_next = page < total_pages
    prev_page = page - 1 if has_prev else None
    next_page = page + 1 if has_next else None
    
    # Get filter options
    news_sources = db.query(models.Article.news_source).distinct().all()
    news_sources = [source[0] for source in news_sources if source[0]]
    
    languages = db.query(models.Article.language).distinct().all()
    languages = [lang[0] for lang in languages if lang[0]]
    
    return templates.TemplateResponse(
        "admin/articles.html",
        {
            "request": request,
            "articles": articles,
            "current_page": page,
            "total_pages": total_pages,
            "has_prev": has_prev,
            "has_next": has_next,
            "prev_page": prev_page,
            "next_page": next_page,
            "limit": limit,
            "total_articles": total_articles,
            "current_search": search,
            "current_news_source": news_source,
            "current_language": language,
            "current_sort": sort,
            "news_sources": news_sources,
            "languages": languages,
            "page": page
        }
    )

@router.get("/{article_id}", response_class=HTMLResponse)
async def get_article(
    request: Request,
    article_id: str,
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    """Display article details."""
    article = db.query(models.Article).filter(models.Article.id == article_id).first()
    
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    return templates.TemplateResponse(
        "admin/article-detail.html",
        {
            "request": request,
            "article": article
        }
    )