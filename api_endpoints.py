from fastapi import APIRouter, Depends, Request, Body, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
import logging
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from services.search import get_article_stats_service, search_term_service, search_articles_service, search_term_service_async, search_articles_service_async
from services.redis_helper import RedisHelper
import urllib.parse

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
    short_id: str = Field(..., description="Short URL identifier")
    short_url: str = Field(..., description="Short URL path")
    original_url: str = Field(..., description="Original article URL")
    impressions: int = Field(..., description="Number of times the link was shown")
    clicks: int = Field(..., description="Number of times the link was clicked")
    ctr: float = Field(..., description="Click-through rate as percentage")

class CTRTotals(BaseModel):
    """Overall CTR statistics totals"""
    total_urls: int = Field(..., description="Total number of tracked URLs")
    total_impressions: int = Field(..., description="Total impressions across all URLs")
    total_clicks: int = Field(..., description="Total clicks across all URLs")
    overall_ctr: float = Field(..., description="Overall click-through rate as percentage")

class CTRResponse(BaseModel):
    """Response model for CTR statistics"""
    success: bool = Field(..., description="Whether the operation was successful")
    stats: List[CTRStatItem] = Field(default=[], description="List of CTR statistics")
    totals: CTRTotals = Field(..., description="Overall statistics totals")
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
    result = await search_term_service_async(
        query=search_data.query,
        db=db,
        request=request,
        generate_summary=search_data.generate_summary,
        system_prompt=search_data.system_prompt
    )
    return SearchResponse(**result)


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
    result = await search_articles_service_async(search_data.query, db, request)
    return ArticleSearchResponse(**result)


@router.get(
    "/api/ctr-stats",
    response_model=CTRResponse,
    summary="Get CTR Statistics",
    description="Retrieve comprehensive click-through rate statistics for all shortened URLs",
    responses={
        200: {
            "description": "CTR statistics retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "stats": [
                            {
                                "short_id": "abc123",
                                "short_url": "/r/abc123",
                                "original_url": "https://example.com/article/123",
                                "impressions": 100,
                                "clicks": 15,
                                "ctr": 15.0
                            }
                        ],
                        "totals": {
                            "total_urls": 1,
                            "total_impressions": 100,
                            "total_clicks": 15,
                            "overall_ctr": 15.0
                        }
                    }
                }
            }
        },
        500: {"description": "Internal server error"}
    },
    tags=["Analytics"]
)
async def get_ctr_stats(request: Request):
    """
    Get comprehensive Click-Through Rate statistics for all shortened URLs.
    
    This endpoint provides detailed analytics for URL shortening performance:
    - **Individual URL Stats**: Impressions, clicks, and CTR for each shortened URL
    - **Overall Metrics**: Total impressions, clicks, and aggregate CTR
    - **Performance Ranking**: URLs sorted by CTR performance
    
    All data is retrieved from Redis cache with 30-day retention.
    Requires authentication via session token.
    """
    try:
        # Get all impression keys from Redis
        impression_keys = await RedisHelper.get_keys_pattern("impressions:*", request)
        stats = []
        
        for key in impression_keys:
            short_id = key.replace("impressions:", "")
            impressions = await RedisHelper.get_value(f"impressions:{short_id}", request) or 0
            clicks = await RedisHelper.get_value(f"clicks:{short_id}", request) or 0
            
            # Convert to integers if they're strings
            impressions = int(impressions) if impressions else 0
            clicks = int(clicks) if clicks else 0
            
            # Calculate CTR (avoid division by zero)
            ctr = (clicks / impressions * 100) if impressions > 0 else 0
            
            # Get the original URL for reference
            original_url = await RedisHelper.get_value(f"url:{short_id}", request)
            
            if original_url:  # Only include if URL still exists
                stats.append(CTRStatItem(
                    short_id=short_id,
                    short_url=f"/r/{short_id}",
                    original_url=original_url,
                    impressions=impressions,
                    clicks=clicks,
                    ctr=round(ctr, 2)  # Round to 2 decimal places
                ))
        
        # Sort by CTR (highest first)
        stats.sort(key=lambda x: x.ctr, reverse=True)
        
        # Calculate overall totals
        total_impressions = sum(item.impressions for item in stats)
        total_clicks = sum(item.clicks for item in stats)
        overall_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
        
        totals = CTRTotals(
            total_urls=len(stats),
            total_impressions=total_impressions,
            total_clicks=total_clicks,
            overall_ctr=round(overall_ctr, 2)
        )
        
        return CTRResponse(
            success=True,
            stats=stats,
            totals=totals,
            error=None
        )
    except Exception as e:
        logger.error(f"Error fetching CTR stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/r/{short_id}",
    summary="Redirect Shortened URL",
    description="Redirect to original article URL with UTM tracking and click analytics",
    responses={
        302: {"description": "Redirect to original URL with UTM parameters"},
        404: {"description": "Short URL not found or expired"},
        500: {"description": "Internal server error"}
    },
    tags=["URL Shortening"]
)
async def redirect_to_article(short_id: str, request: Request):
    """
    Redirect to the original article URL with UTM tracking parameters.
    
    This endpoint handles URL shortening redirection with analytics tracking:
    - **Click Tracking**: Increments click counter for CTR analysis
    - **UTM Parameters**: Adds WhatsApp and news tracking parameters
    - **Expiration Handling**: Returns 404 for expired or invalid links
    
    The redirection preserves existing query parameters while adding:
    - utmSource: whatsapp
    - utmMedium: news
    
    Link expiration is handled automatically by Redis TTL (30 days).
    """
    try:
        # Get the original URL from Redis
        original_url = await RedisHelper.get_value(f"url:{short_id}", request)
        
        if not original_url:
            # Handle case when URL is not found (expired or invalid ID)
            raise HTTPException(status_code=404, detail="Link expired or not found")
        
        # Track the click
        await RedisHelper.increment(f"clicks:{short_id}", request, expire=86400 * 30)
        
        # Parse the original URL
        parsed_url = urllib.parse.urlparse(original_url)
        
        # Get existing query parameters
        query_params = dict(urllib.parse.parse_qsl(parsed_url.query))
        
        # Add UTM parameters
        query_params.update({
            "utmSource": "whatsapp",
            "utmMedium": "news"
        })
        
        # Build the new query string
        new_query = urllib.parse.urlencode(query_params)
        
        # Construct the new URL with UTM parameters
        new_url = urllib.parse.urlunparse((
            parsed_url.scheme,
            parsed_url.netloc,
            parsed_url.path,
            parsed_url.params,
            new_query,
            parsed_url.fragment
        ))
        
        # Redirect to the new URL
        return RedirectResponse(url=new_url, status_code=302)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error redirecting short URL {short_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")