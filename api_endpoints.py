from fastapi import APIRouter, Depends, Request, Body, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
import logging
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from services.search import get_article_stats_service, search_term_service, search_articles_service, get_ctr_stats_service

router = APIRouter()
logger = logging.getLogger(__name__)

class SearchQuery(BaseModel):
    """Request model for article search"""
    query: str = Field(
        description="Search query string to find relevant articles",
        min_length=1
    )
    generate_summary: bool = Field(
        default=False,
        description="Whether to generate an AI-powered summary of search results"
    )
    system_prompt: Optional[str] = Field(
        default=None,
        description="Custom system prompt for AI summary generation"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "query": "artificial intelligence",
                "generate_summary": True,
                "system_prompt": "Summarize the following articles about technology trends"
            }
        }

class ArticleSearchQuery(BaseModel):
    """Request model for article search with query parameter"""
    query: str = Field(
        description="Search query to find specific articles",
        min_length=1
    )

    class Config:
        json_schema_extra = {
            "example": {
                "query": "machine learning"
            }
        }

class SearchResult(BaseModel):
    """Individual search result model"""
    id: str = Field(..., description="Unique article identifier")
    title: str = Field(..., description="Article title")
    similarity: float = Field(..., description="Similarity score between 0 and 1", ge=0, le=1)
    url: str = Field(..., description="Original article URL")
    short_url: str = Field(..., description="Shortened URL for tracking")
    published_date: Optional[str] = Field(None, description="Publication date in YYYY-MM-DD format")
    author: Optional[str] = Field(None, description="Article author name")
    description: Optional[str] = Field(None, description="Article description or excerpt")
    summary_content: Optional[str] = Field(None, description="AI-generated summary of article content")
    key_words: Optional[List[str]] = Field(None, description="Article keywords/tags")

class ArticleStats(BaseModel):
    """Article statistics model"""
    total_count: int = Field(..., description="Total number of articles in database")
    oldest_date: Optional[str] = Field(None, description="Oldest article date in DD/MM/YYYY format")
    newest_date: Optional[str] = Field(None, description="Newest article date in DD/MM/YYYY format")

class SearchResponse(BaseModel):
    """Response model for search operations"""
    success: bool = Field(..., description="Whether the operation was successful")
    results: List[SearchResult] = Field(default=[], description="List of search results")
    count: int = Field(default=0, description="Number of results returned")
    summary: Optional[str] = Field(None, description="AI-generated summary of results")
    error: Optional[str] = Field(None, description="Error message if operation failed")

class ArticleStatsResponse(BaseModel):
    """Response model for article statistics"""
    success: bool = Field(..., description="Whether the operation was successful")
    stats: Optional[ArticleStats] = Field(None, description="Article statistics")
    error: Optional[str] = Field(None, description="Error message if operation failed")

class ArticleSearchResponse(BaseModel):
    """Response model for article search operations"""
    success: bool = Field(..., description="Whether the search was successful")
    results: List[SearchResult] = Field(default=[], description="List of matching articles")
    count: int = Field(default=0, description="Number of articles found")
    error: Optional[str] = Field(None, description="Error message if search failed")

class CTRStatItem(BaseModel):
    """Individual CTR statistics item"""
    short_id: str = Field(..., description="Shortened URL identifier")
    short_url: str = Field(..., description="Shortened URL path")
    original_url: Optional[str] = Field(None, description="Original URL")
    impressions: int = Field(..., description="Number of times URL was shown")
    clicks: int = Field(..., description="Number of times URL was clicked")
    ctr: float = Field(..., description="Click-through rate as percentage")

class CTRTotals(BaseModel):
    """CTR statistics totals"""
    total_urls: int = Field(..., description="Total number of URLs tracked")
    total_impressions: int = Field(..., description="Total impressions across all URLs")
    total_clicks: int = Field(..., description="Total clicks across all URLs")
    overall_ctr: float = Field(..., description="Overall click-through rate as percentage")

class CTRStatsResponse(BaseModel):
    """Response model for CTR statistics"""
    success: bool = Field(..., description="Whether the operation was successful")
    stats: List[CTRStatItem] = Field(default=[], description="List of CTR statistics")
    totals: Optional[CTRTotals] = Field(None, description="Overall statistics totals")
    pagination: Optional[Dict[str, Any]] = Field(None, description="Pagination information")
    error: Optional[str] = Field(None, description="Error message if operation failed")

class ArticleItem(BaseModel):
    """Individual article item model"""
    id: str = Field(..., description="Unique article identifier")
    title: str = Field(..., description="Article title")
    url: str = Field(..., description="Shortened URL for the article")
    published_date: Optional[str] = Field(None, description="Publication date in YYYY-MM-DD format")
    author: Optional[str] = Field(None, description="Article author name")
    description: Optional[str] = Field(None, description="Article description or excerpt")
    summary_content: Optional[str] = Field(None, description="AI-generated summary of article content")
    news_source: Optional[str] = Field(None, description="News source name")
    language: Optional[str] = Field(None, description="Article language")

class ArticleListResponse(BaseModel):
    """Response model for article list operations"""
    success: bool = Field(..., description="Whether the operation was successful")
    articles: List[ArticleItem] = Field(default=[], description="List of articles")
    total: int = Field(..., description="Total number of articles matching the criteria")
    pages: int = Field(..., description="Total number of pages")
    current_page: int = Field(..., description="Current page number")
    error: Optional[str] = Field(None, description="Error message if operation failed")

@router.get(
    "/api/article-stats",
    response_model=ArticleStatsResponse,
    summary="Get Article Statistics",
    description="Retrieve comprehensive statistics about articles in the database including total count, oldest and newest publication dates",
    responses={
        200: {
            "description": "Successfully retrieved article statistics",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "stats": {
                            "total_count": 1250,
                            "oldest_date": "01/01/2020",
                            "newest_date": "10/06/2025"
                        }
                    }
                }
            }
        },
        302: {"description": "Redirect to login - authentication required"},
        500: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "error": "Database connection failed"
                    }
                }
            }
        }
    },
    tags=["Statistics"]
)
async def get_article_stats(request: Request, db: Session = Depends(get_db)):
    """
    Get comprehensive article statistics for admin dashboard display.
    
    This endpoint provides essential metrics about the article database:
    - Total number of articles
    - Publication date range (oldest to newest)
    - Database health indicators
    
    Requires authentication via session token.
    """
    return await get_article_stats_service(db)

@router.post(
    "/api/search",
    response_model=SearchResponse,
    summary="Advanced Article Search",
    description="Perform intelligent article search using vector similarity and full-text search with optional AI-generated summaries",
    responses={
        200: {
            "description": "Search completed successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "results": [
                            {
                                "id": "123",
                                "title": "Understanding Artificial Intelligence",
                                "similarity": 0.95,
                                "url": "https://example.com/article/123",
                                "short_url": "/admin/articles/123",
                                "published_date": "2024-06-10",
                                "author": "Dr. Jane Smith",
                                "description": "A comprehensive guide to AI concepts",
                                "key_words": ["AI", "machine learning", "technology"]
                            }
                        ],
                        "count": 1,
                        "summary": "📖 Aqui está o que descobrimos sobre o termo solicitado..."
                    }
                }
            }
        },
        302: {"description": "Redirect to login - authentication required"},
        400: {
            "description": "Bad request - invalid search parameters",
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "error": "Query is required"
                    }
                }
            }
        },
        500: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "error": "Search service unavailable"
                    }
                }
            }
        }
    },
    tags=["Search"]
)
async def search_term(
    request: Request, 
    search_data: SearchQuery = Body(
        ...,
        example={
            "query": "amazonas",
            "generate_summary": True,
            "system_prompt": "Provide a brief technical summary"
        }
    ),
    db: Session = Depends(get_db)
):
    """
    Perform advanced article search with AI-powered features.
    
    This endpoint provides sophisticated search capabilities:
    - **Vector Similarity Search**: Uses embeddings for semantic matching
    - **Full-Text Search**: Traditional keyword-based search
    - **AI Summaries**: Optional AI-generated summaries of results
    - **Custom Prompts**: Personalized summary generation
    
    The search algorithm combines multiple techniques to find the most relevant articles
    and can optionally generate intelligent summaries in Portuguese.
    
    Requires authentication via session token.
    """
    return await search_term_service(
        query=search_data.query,
        db=db,
        generate_summary=search_data.generate_summary,
        system_prompt=search_data.system_prompt,
        redis_client=getattr(request.app.state, 'redis', None)
    )


@router.post(
    "/api/search-articles",
    response_model=ArticleSearchResponse,
    summary="Search Articles by Query",
    description="Search for specific articles using a text query with similarity matching",
    responses={
        200: {
            "description": "Search completed successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "results": [
                            {
                                "id": "456",
                                "title": "Machine Learning Applications",
                                "similarity": 0.88,
                                "url": "https://example.com/article/456",
                                "short_url": "/admin/articles/456",
                                "published_date": "2024-06-09",
                                "author": "Prof. John Doe",
                                "description": "Exploring practical ML applications",
                                "key_words": ["machine learning", "applications", "AI"]
                            }
                        ],
                        "count": 1
                    }
                }
            }
        },
        302: {"description": "Redirect to login - authentication required"},
        400: {
            "description": "Bad request - missing or invalid query",
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "error": "Query is required"
                    }
                }
            }
        },
        500: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "error": "Search service unavailable"
                    }
                }
            }
        }
    },
    tags=["Search"]
)
async def search_articles_api(
    request: Request,
    search_data: ArticleSearchQuery = Body(
        ...,
        example={"query": "machine learning"}
    ),
    db: Session = Depends(get_db)
):
    """Search articles with query parameter"""
    return await search_articles_service(search_data.query, db, redis_client=getattr(request.app.state, 'redis', None))

@router.get(
    "/api/ctr-stats",
    response_model=CTRStatsResponse,
    summary="Get CTR Statistics",
    description="Retrieve comprehensive click-through rate statistics for shortened URLs",
    responses={
        200: {
            "description": "CTR statistics retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "stats": [
                            {
                                "short_id": "abc123de",
                                "short_url": "/r/abc123de",
                                "original_url": "https://example.com/article/123",
                                "impressions": 150,
                                "clicks": 45,
                                "ctr": 30.0
                            },
                            {
                                "short_id": "def456gh",
                                "short_url": "/r/def456gh", 
                                "original_url": "https://example.com/article/456",
                                "impressions": 200,
                                "clicks": 20,
                                "ctr": 10.0
                            }
                        ],
                        "totals": {
                            "total_urls": 2,
                            "total_impressions": 350,
                            "total_clicks": 65,
                            "overall_ctr": 18.57
                        },
                        "pagination": {
                            "page": 1,
                            "page_size": 20,
                            "total_items": 2,
                            "total_pages": 1,
                            "has_next": False,
                            "has_prev": False
                        }
                    }
                }
            }
        },
        302: {"description": "Redirect to login - authentication required"},
        500: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "error": "Unable to retrieve CTR statistics"
                    }
                }
            }
        }
    },
    tags=["Analytics"]
)
async def get_ctr_stats(
    request: Request,
    page: int = Query(1, ge=1, description="Page number (starting from 1)"),
    page_size: int = Query(20, ge=1, le=100, description="Number of items per page (1-100)")
):
    """
    Get comprehensive CTR statistics for shortened URLs with pagination.
    
    This endpoint provides detailed click-through rate analytics:
    - **Individual URL Performance**: Stats for each shortened URL
    - **Impression Tracking**: Number of times URLs were shown
    - **Click Tracking**: Number of times URLs were clicked
    - **CTR Calculation**: Click-through rate as percentage
    - **Overall Summary**: Aggregated statistics across all URLs
    - **Pagination**: Support for paginated results
    
    Data is retrieved from both Redis cache and in-memory fallback storage.
    
    Requires authentication via session token.
    """
    # Get Redis client from app state
    redis_client = getattr(request.app.state, 'redis', None)
    
    return await get_ctr_stats_service(redis_client, page=page, page_size=page_size)

@router.get(
    "/api/articles",
    response_model=ArticleListResponse,
    summary="List Articles with Filters",
    description="Retrieve a paginated list of articles with optional filtering by search query, date range, and summary content",
    responses={
        200: {
            "description": "Articles retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "articles": [
                            {
                                "id": "123e4567-e89b-12d3-a456-426614174000",
                                "title": "Understanding Climate Change in the Amazon",
                                "url": "/r/abc123de",
                                "published_date": "2024-06-10",
                                "author": "Dr. Maria Silva",
                                "description": "A comprehensive study of climate impacts in the Amazon rainforest",
                                "summary_content": "This article explores the various effects of climate change on the Amazon ecosystem...",
                                "news_source": "Environmental Science Journal",
                                "language": "pt"
                            },
                            {
                                "id": "456e7890-e12b-34c5-d678-901234567890",
                                "title": "New Species Discovery in Brazil",
                                "url": "/r/def456gh",
                                "published_date": "2024-06-09",
                                "author": "Prof. João Santos",
                                "description": "Scientists discover new species in the Amazon basin",
                                "summary_content": "Researchers have identified a previously unknown species of bird...",
                                "news_source": "Biology Today",
                                "language": "pt"
                            }
                        ],
                        "total": 245,
                        "pages": 25,
                        "current_page": 1
                    }
                }
            }
        },
        302: {"description": "Redirect to login - authentication required"},
        400: {
            "description": "Bad request - invalid parameters",
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "error": "Invalid date format. Use YYYY-MM-DD format."
                    }
                }
            }
        },
        500: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "error": "Database connection failed"
                    }
                }
            }
        }
    },
    tags=["Articles"]
)
async def list_articles_api(
    request: Request,
    page: int = Query(1, ge=1, description="Page number (starting from 1)"),
    search: str = Query(None, description="Search query to filter articles by title"),
    date_from: str = Query(None, description="Start date filter in YYYY-MM-DD format"),
    date_to: str = Query(None, description="End date filter in YYYY-MM-DD format"),
    summary: str = Query(None, description="Search query to filter articles by summary content"),
    db: Session = Depends(get_db)
):
    """
    Retrieve a paginated list of articles with comprehensive filtering options.
    
    This endpoint provides flexible article listing capabilities:
    - **Pagination**: Navigate through large article collections
    - **Search Filter**: Find articles by title using case-insensitive search
    - **Date Range**: Filter articles by publication date range
    - **Summary Search**: Search within article summary content
    - **Sorting**: Articles are sorted by publication date (newest first)
    
    All filters can be combined for precise article discovery.
    Each article includes shortened URLs for tracking and analytics.
    
    Requires authentication via session token.
    """
    from services.search import list_articles_service
    
    try:
        # Get Redis client for URL shortening
        redis_client = getattr(request.app.state, 'redis', None)
        
        # Use the service function to get articles
        result = await list_articles_service(
            db=db,
            page=page,
            search=search,
            date_from=date_from,
            date_to=date_to,
            summary=summary,
            redis_client=redis_client
        )
        
        # Convert articles to ArticleItem objects
        formatted_articles = []
        for article_data in result.get("articles", []):
            formatted_articles.append(ArticleItem(
                id=article_data["id"],
                title=article_data["title"],
                url=article_data["url"],
                published_date=article_data["published_date"],
                author=article_data["author"],
                description=article_data["description"],
                summary_content=article_data["summary_content"],
                news_source=article_data["news_source"],
                language=article_data["language"]
            ))
        
        return ArticleListResponse(
            success=result["success"],
            articles=formatted_articles,
            total=result["total"],
            pages=result["pages"],
            current_page=result["current_page"],
            error=result.get("error")
        )
        
    except Exception as e:
        logger.error(f"Error in list_articles_api: {str(e)}")
        return ArticleListResponse(
            success=False,
            articles=[],
            total=0,
            pages=0,
            current_page=page,
            error=f"Internal server error: {str(e)}"
        )