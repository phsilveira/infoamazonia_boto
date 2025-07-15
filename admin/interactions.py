
"""
Interactions management module for admin panel.
Handles user interaction tracking, analytics, and export functionality.
"""

import io
import csv
import json
from datetime import datetime
from fastapi import APIRouter, Request, Query, Body, HTTPException
from fastapi.responses import HTMLResponse, Response, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, case, or_
from .base import *
import models
from auth import get_current_admin
from database import get_db
from cache_utils import get_cache, set_cache
from services.chatgpt import ChatGPTService
from utils.prompt_loader import prompt_loader
import logging

logger = logging.getLogger(__name__)

# Initialize ChatGPT service instance
chatgpt_service = ChatGPTService()

router = APIRouter()

def get_db_dependency():
    """Database dependency function"""
    return Depends(get_db)

def get_current_admin_dependency():
    """Current admin dependency function"""
    return Depends(get_current_admin)

@router.get("/export-csv")
async def export_interactions_csv(
    request: Request,
    category: str = None,
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    """Export interactions to CSV with optional category filter."""
    try:
        # Build query
        query = db.query(models.UserInteraction)
        
        if category and category != "all":
            query = query.filter(models.UserInteraction.category == category)
        
        # Order by creation date
        interactions = query.order_by(desc(models.UserInteraction.created_at)).all()
        
        # Create CSV content
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'ID', 'User Phone', 'Query', 'Category', 'Response', 
            'Feedback', 'Created At', 'Processing Time'
        ])
        
        # Write data
        for interaction in interactions:
            user_phone = interaction.user.phone_number if interaction.user else "Unknown"
            writer.writerow([
                interaction.id,
                user_phone,
                interaction.query,
                interaction.category,
                interaction.response[:100] + "..." if len(interaction.response) > 100 else interaction.response,
                interaction.feedback,
                interaction.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                f"{interaction.processing_time:.2f}s" if interaction.processing_time else "N/A"
            ])
        
        csv_content = output.getvalue()
        output.close()
        
        # Return CSV response
        response = Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=interactions_{category or 'all'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"}
        )
        return response
        
    except Exception as e:
        logger.error(f"Error exporting interactions: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")

@router.get("", response_class=HTMLResponse)
async def list_interactions(
    request: Request,
    category: str = "term",
    page: int = 1,
    page_size: int = 20,
    search: str = None,
    feedback: str = None,
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    try:
        # Build query
        query = db.query(models.UserInteraction)
        
        # Apply category filter
        if category and category != "all":
            query = query.filter(models.UserInteraction.category == category)
        
        # Apply search filter
        if search:
            query = query.filter(
                or_(
                    models.UserInteraction.query.ilike(f"%{search}%"),
                    models.UserInteraction.response.ilike(f"%{search}%")
                )
            )
        
        # Apply feedback filter
        if feedback and feedback != "all":
            query = query.filter(models.UserInteraction.feedback == feedback)
        
        # Order by creation date (newest first)
        query = query.order_by(desc(models.UserInteraction.created_at))
        
        # Calculate pagination
        total_interactions = query.count()
        skip = (page - 1) * page_size
        interactions = query.offset(skip).limit(page_size).all()
        
        # Calculate pagination info
        total_pages = (total_interactions + page_size - 1) // page_size
        has_prev = page > 1
        has_next = page < total_pages
        prev_page = page - 1 if has_prev else None
        next_page = page + 1 if has_next else None
        
        # Get category counts for tabs
        category_counts = {}
        categories_data = {}
        
        for cat in ["term", "article", "news_suggestion"]:
            count = db.query(models.UserInteraction).filter(models.UserInteraction.category == cat).count()
            category_counts[cat] = count
            
            # Get interactions for this category
            cat_interactions = db.query(models.UserInteraction).filter(
                models.UserInteraction.category == cat
            ).order_by(desc(models.UserInteraction.created_at)).limit(10).all()
            
            # Calculate pagination for this category
            cat_total_pages = (count + page_size - 1) // page_size if count > 0 else 1
            
            categories_data[cat] = {
                "interactions": cat_interactions,
                "count": count,
                "total_count": count,
                "total_pages": cat_total_pages
            }
        
        # Feedback options for filter
        feedback_options = ["positive", "negative", "none"]
        
        return templates.TemplateResponse(
            "admin/interactions.html",
            {
                "request": request,
                "interactions": interactions,
                "current_page": page,
                "total_pages": total_pages,
                "has_prev": has_prev,
                "has_next": has_next,
                "prev_page": prev_page,
                "next_page": next_page,
                "page_size": page_size,
                "total_interactions": total_interactions,
                "current_category": category,
                "category_counts": category_counts,
                "categories_data": categories_data,
                "feedback_options": feedback_options,
                "current_search": search,
                "current_feedback": feedback,
                "category": category,
                "search": search,
                "feedback": feedback,
                "page": page
            }
        )
    except Exception as e:
        logger.error(f"Error listing interactions: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to load interactions: {str(e)}")

@router.get("/summaries/{category}")
async def get_interaction_summaries(
    request: Request,
    category: str,
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    """Generate AI summaries of user interactions for a specific category."""
    try:
        # Define cache key for this category
        cache_key = f"interaction_summary:{category}"

        # Try to get from cache first
        cached_result = await get_cache(cache_key, request)
        if cached_result:
            logger.info(f"Returning cached interaction summary for category: {category}")
            return cached_result

        # For 'article' category, implement the new query grouping instead of ChatGPT summary
        if category == 'article':
            # Get the last 50 interactions for article category
            recent_interactions = db.query(models.UserInteraction)\
                .filter(models.UserInteraction.category == 'article')\
                .order_by(models.UserInteraction.created_at.desc())\
                .limit(50)\
                .all()

            # Extract query texts from recent interactions
            recent_query_texts = [interaction.query for interaction in recent_interactions]

            if not recent_query_texts:
                result = {"summary": "No queries found for this category"}
                await set_cache(cache_key, result, request, expire_seconds=180)
                return result

            # Aggregate the queries to get statistics
            query_stats = db.query(
                models.UserInteraction.query, 
                func.count(models.UserInteraction.id).label('query_count'),
                func.sum(case(
                    (models.UserInteraction.feedback == True, 1), 
                    else_=0
                )).label('positive_feedback'),
                func.sum(case(
                    (models.UserInteraction.feedback == False, 1), 
                    else_=0
                )).label('negative_feedback')
            ).filter(
                models.UserInteraction.query.in_(recent_query_texts)
            ).group_by(
                models.UserInteraction.query
            ).order_by(
                func.count(models.UserInteraction.id).desc()
            ).all()

            if not query_stats:
                result = {"summary": "No query statistics available for this category"}
                await set_cache(cache_key, result, request, expire_seconds=180)
                return result

            # Create an HTML table with the top 10 query statistics
            table_rows = ""
            for query, count, positive, negative in query_stats[:10]:  # Only show top 10
                # Truncate query if it's too long for display
                display_query = query[:100] + "..." if len(query) > 100 else query
                table_rows += f"""
                <tr>
                    <td>{display_query}</td>
                    <td class="text-center">{count}</td>
                    <td class="text-center">{positive or 0}</td>
                    <td class="text-center">{negative or 0}</td>
                </tr>
                """

            summary_html = f"""
            <div class="mb-3">
                <p class="text-muted">Showing top 10 queries from the last 50 interactions</p>
            </div>
            <div class="table-responsive">
                <table class="table table-striped table-bordered">
                    <thead>
                        <tr>
                            <th>Query/Article URL</th>
                            <th class="text-center">Total Queries</th>
                            <th class="text-center">Positive Feedback</th>
                            <th class="text-center">Negative Feedback</th>
                        </tr>
                    </thead>
                    <tbody>
                        {table_rows}
                    </tbody>
                </table>
            </div>
            """

            result = {"summary": summary_html}
            await set_cache(cache_key, result, request, expire_seconds=180)
            return result

        else:
            # For other categories, continue with the original ChatGPT summary
            # Get last 50 queries for the specified category
            queries = db.query(models.UserInteraction.query)\
                .filter(models.UserInteraction.category == category)\
                .order_by(models.UserInteraction.created_at.desc())\
                .limit(50)\
                .all()

            # Extract query texts
            query_texts = [q[0] for q in queries]

            if not query_texts:
                result = {"summary": "No queries found for this category"}
                # Cache the empty result as well
                await set_cache(cache_key, result, request, expire_seconds=180)  # 3 minutes TTL
                return result

            # Generate summary using ChatGPT
            summary = await chatgpt_service.summarize_queries(query_texts, category)

            # Add system prompt to the summary result
            result = {
                "summary": summary,
                "query_count": len(query_texts)
            }

            # Store in cache with 3-minute TTL (180 seconds)
            await set_cache(cache_key, result, request, expire_seconds=180)

            return result

    except Exception as e:
        logger.error(f"Error generating interaction summaries: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate summaries: {str(e)}"
        )

@router.post("/summaries/{category}/custom")
async def get_interaction_summaries_custom_prompt(
    request: Request,
    category: str,
    custom_prompt_data: dict = Body(...),
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    """Generate interaction summaries using a custom system prompt"""
    try:
        custom_prompt = custom_prompt_data.get("custom_prompt", "").strip()
        if not custom_prompt:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "Custom prompt cannot be empty"}
            )
        
        # Get interactions for the category
        interactions = db.query(models.UserInteraction).filter(
            models.UserInteraction.category == category
        ).order_by(desc(models.UserInteraction.created_at)).limit(100).all()
        
        if not interactions:
            return JSONResponse(
                content={"success": False, "message": f"No interactions found for category: {category}"}
            )
        
        # Prepare interaction data for analysis
        interaction_data = []
        for interaction in interactions:
            interaction_data.append({
                "query": interaction.query,
                "response": interaction.response,
                "feedback": interaction.feedback,
                "created_at": interaction.created_at.isoformat()
            })
        
        # Generate summary using custom prompt
        user_prompt = f"Analyze the following {len(interaction_data)} user interactions:\n\n"
        user_prompt += json.dumps(interaction_data, indent=2)
        
        summary = chatgpt_service.generate_completion(
            query=user_prompt,
            context="",
            system_prompt=custom_prompt
        )
        
        return JSONResponse(content={
            "success": True,
            "summary": summary,
            "interaction_count": len(interaction_data),
            "category": category,
            "custom_prompt_used": True
        })
        
    except Exception as e:
        logger.error(f"Error generating custom interaction summary: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"Failed to generate summary: {str(e)}"}
        )
