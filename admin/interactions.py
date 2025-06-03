"""
Interactions management module for admin panel.
Handles user interaction tracking, analytics, and export functionality.
"""

from fastapi import APIRouter, Form, Query
from .base import *

router = APIRouter()

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
            "feedback": feedback
        }
    )

@router.get("/summaries/{category}")
async def get_interaction_summaries(
    request: Request,
    category: str,
    db: Session = get_db_dependency(),
    current_admin: models.Admin = get_current_admin_dependency()
):
    """Generate AI summaries of user interactions for a specific category."""
    try:
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
        
        # Load the appropriate prompt for the category
        system_prompt = prompt_loader.get_prompt(f"interaction_summary_{category}")
        if not system_prompt:
            system_prompt = prompt_loader.get_prompt("interaction_summary_default")
        
        # Generate summary using ChatGPT
        user_prompt = f"Analyze the following {len(interaction_data)} user interactions and provide insights:\n\n"
        user_prompt += json.dumps(interaction_data, indent=2)
        
        summary = await chatgpt_service.get_completion(
            system_prompt=system_prompt,
            user_prompt=user_prompt
        )
        
        return JSONResponse(content={
            "success": True,
            "summary": summary,
            "interaction_count": len(interaction_data),
            "category": category
        })
        
    except Exception as e:
        logger.error(f"Error generating interaction summary: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"Failed to generate summary: {str(e)}"}
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
        
        summary = await chatgpt_service.get_completion(
            system_prompt=custom_prompt,
            user_prompt=user_prompt
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