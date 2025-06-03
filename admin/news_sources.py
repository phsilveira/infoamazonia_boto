"""
News sources management module for admin panel.
Handles all news source operations including CRUD operations,
status updates, and article downloading functionality.
"""

from fastapi import APIRouter, Form
from .base import *
import types
import sys

router = APIRouter()

@router.get("", response_class=HTMLResponse)
async def list_news_sources(
    request: Request,
    search: str = None,
    status: str = None,
    sort: str = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    # Start with a base query
    query = db.query(models.NewsSource)
    
    # Apply search filter if provided
    if search:
        query = query.filter(
            or_(
                models.NewsSource.name.ilike(f"%{search}%"),
                models.NewsSource.url.ilike(f"%{search}%")
            )
        )
    
    # Apply status filter
    query = apply_status_filter(query, models.NewsSource.is_active, status)
    
    # Apply sorting if provided
    if sort == "created_at_asc":
        query = query.order_by(models.NewsSource.created_at.asc())
    elif sort == "name_asc":
        query = query.order_by(models.NewsSource.name.asc())
    elif sort == "name_desc":
        query = query.order_by(models.NewsSource.name.desc())
    else:  # Default to newest first
        query = query.order_by(models.NewsSource.created_at.desc())
    
    sources = apply_pagination(query, skip, limit).all()
    
    return templates.TemplateResponse(
        "admin/news-sources.html",
        {"request": request, "sources": sources}
    )

@router.post("/create", response_class=HTMLResponse)
async def create_news_source(
    request: Request,
    name: str = Form(...),
    url: str = Form(...),
    status: str = Form(...),
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    try:
        # Check if a news source with this URL already exists
        existing_source = db.query(models.NewsSource).filter(models.NewsSource.url == url).first()
        if existing_source:
            # Return error
            sources = db.query(models.NewsSource).order_by(desc(models.NewsSource.created_at)).all()
            return templates.TemplateResponse(
                "admin/news-sources.html",
                {
                    "request": request, 
                    "sources": sources,
                    "error": "A news source with this URL already exists."
                }
            )
        
        # Create new news source
        source = models.NewsSource(
            name=name,
            url=url,
            is_active=(status == 'active')
        )
        db.add(source)
        db.commit()
        db.refresh(source)
        
        await invalidate_caches_and_log(request, "news source creation", str(source.id))

        return RedirectResponse(
            url="/admin/news-sources",
            status_code=302
        )
    except Exception as e:
        await handle_database_error(e, "news source creation")

@router.get("/{source_id}", response_class=HTMLResponse)
async def get_news_source(
    request: Request,
    source_id: int,
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    # Get the news source
    source = db.query(models.NewsSource).filter(models.NewsSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="News source not found")
    
    return templates.TemplateResponse(
        "admin/news-source-detail.html",
        {"request": request, "source": source}
    )

@router.post("/{source_id}/status", response_class=RedirectResponse)
async def update_news_source_status(
    request: Request,
    source_id: int,
    status: str = Form(...),
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    try:
        source = db.query(models.NewsSource).filter(models.NewsSource.id == source_id).first()
        if not source:
            raise HTTPException(status_code=404, detail="News source not found")
        
        # Update status
        source.is_active = status == "active"
        db.commit()
        
        await invalidate_caches_and_log(request, "news source status update", str(source_id))
        
        return RedirectResponse(
            url=f"/admin/news-sources/{source_id}",
            status_code=status.HTTP_302_FOUND
        )
    except Exception as e:
        await handle_database_error(e, "news source status update")

@router.post("/{source_id}/edit", response_class=RedirectResponse)
async def edit_news_source(
    request: Request,
    source_id: int,
    name: str = Form(...),
    url: str = Form(...),
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    try:
        source = db.query(models.NewsSource).filter(models.NewsSource.id == source_id).first()
        if not source:
            raise HTTPException(status_code=404, detail="News source not found")
        
        # Check if URL is already taken by another source
        existing_source = db.query(models.NewsSource).filter(
            models.NewsSource.url == url,
            models.NewsSource.id != source_id
        ).first()
        
        if existing_source:
            # Return with error
            return templates.TemplateResponse(
                "admin/news-source-detail.html",
                {
                    "request": request,
                    "source": source,
                    "error": "A news source with this URL already exists."
                }
            )
        
        # Update source details
        source.name = name
        source.url = url
        db.commit()
        
        await invalidate_caches_and_log(request, "news source edit", str(source_id))
        
        return RedirectResponse(
            url=f"/admin/news-sources/{source_id}",
            status_code=status.HTTP_302_FOUND
        )
    except Exception as e:
        await handle_database_error(e, "news source update")

@router.post("/{source_id}/delete", response_class=RedirectResponse)
async def delete_news_source(
    request: Request,
    source_id: int,
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    try:
        source = db.query(models.NewsSource).filter(models.NewsSource.id == source_id).first()
        if not source:
            raise HTTPException(status_code=404, detail="News source not found")
        
        # Delete the source
        db.delete(source)
        db.commit()
        
        await invalidate_caches_and_log(request, "news source deletion", str(source_id))
        
        return RedirectResponse(
            url="/admin/news-sources",
            status_code=status.HTTP_302_FOUND
        )
    except Exception as e:
        await handle_database_error(e, "news source deletion")

@router.post("/{source_id}/download-articles")
async def download_articles_for_source(
    request: Request,
    source_id: int,
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    """Download articles for a specific news source using web scraping"""
    # Check if this is an AJAX request
    accept_header = request.headers.get("accept", "")
    is_ajax = "application/json" in accept_header
    
    try:
        # Verify source exists
        source = db.query(models.NewsSource).filter(models.NewsSource.id == source_id).first()
        if not source:
            if is_ajax:
                return JSONResponse(
                    status_code=404,
                    content={"success": False, "message": "News source not found"}
                )
            raise HTTPException(status_code=404, detail="News source not found")

        # Import required classes to perform download
        from services.article_ingestion import process_article, ingest_articles
        from models import Article

        # Create a wrapper for Flask db session to work with SQLAlchemy
        class DbWrapper:
            def __init__(self, db_session):
                self.session = db_session

        # This is the key - we wrap our FastAPI session to match the Flask app.db format
        # that the article_ingestion.py code expects
        app_db = DbWrapper(db)
        
        # Patch the Article model for compatibility with Flask SQLAlchemy
        # by adding the query attribute expected by the ingestion code
        Article.query = db.query(Article)
        
        # Temporarily add the wrapper to the sys modules
        app_module = types.ModuleType("app")
        app_module.db = app_db
        sys.modules['app'] = app_module
        
        try:
            logger.info(f"Attempting to get articles from source: {source.name} ({source.url})")
            from services.news import News
            
            # Initialize the News class with our database session
            news = News()
            news.db = app_db
            
            # Fetch news from configured sources
            result = news.get_news()
            
            if not result.get('success', False):
                logger.error("Failed to fetch articles from sources")
                # Clean up temporary module
                if 'app' in sys.modules:
                    del sys.modules['app']
                
                # Return appropriate response based on request type
                if is_ajax:
                    return JSONResponse(
                        status_code=400,
                        content={"success": False, "message": "Failed to fetch articles from sources"}
                    )
                
                # Return to the source detail page with error for regular requests
                return RedirectResponse(
                    url=f"/admin/news-sources/{source_id}",
                    status_code=status.HTTP_302_FOUND
                )
            
            # Now call ingest_articles with our patched environment
            articles_added_count = ingest_articles(result.get('news', []))
            method_used = "process_article and ingest_articles"
            
        except Exception as e:
            logger.error(f"Failed to process articles: {str(e)}")
            # Clean up temporary module
            if 'app' in sys.modules:
                del sys.modules['app']
                
            if is_ajax:
                return JSONResponse(
                    status_code=500,
                    content={"success": False, "message": f"Failed to process articles: {str(e)}"}
                )
                
            raise Exception(f"Failed to process articles: {str(e)}")
        
        # Clean up temporary module
        if 'app' in sys.modules:
            del sys.modules['app']

        # Create success message based on result
        if articles_added_count > 0:
            success_message = f"Successfully downloaded and processed {articles_added_count} new articles"
            logger.info(f"{success_message} via {method_used}")
        else:
            success_message = "No new articles were found or all articles already exist in the database"
            logger.info(f"{success_message} ({method_used})")
        
        await invalidate_caches_and_log(request, "article download")
        
        # Return appropriate response based on request type
        if is_ajax:
            return JSONResponse(
                content={
                    "success": True,
                    "message": success_message,
                    "count": articles_added_count
                }
            )
            
        # Return to the source detail page for regular requests
        return RedirectResponse(
            url=f"/admin/news-sources/{source_id}",
            status_code=status.HTTP_302_FOUND
        )
        
    except Exception as e:
        logger.error(f"Error downloading articles: {str(e)}")
        
        if is_ajax:
            return JSONResponse(
                status_code=500,
                content={"success": False, "message": f"Error downloading articles: {str(e)}"}
            )
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to download articles: {str(e)}"
        )