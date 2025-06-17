from fastapi import APIRouter, Depends, Request, Body, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db
import logging
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from services.search import get_article_stats_service, search_term_service, search_articles_service

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
            "query": "artificial intelligence",
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
        system_prompt=search_data.system_prompt
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
    return await search_articles_service(search_data.query, db)