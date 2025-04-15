from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Query
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
import models, schemas, auth
from database import engine, get_db
from admin import router as admin_router
from webhook import router as webhook_router
from routers.location import router as location_router
from datetime import timedelta
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from middleware import auth_middleware
from scheduler import start_scheduler
from config import settings, get_redis
import redis.asyncio as redis
import logging
import asyncio
import httpx
import json
from datetime import datetime, timedelta
from sqlalchemy import func, desc
from functools import wraps
from cache_utils import get_cache, set_cache, invalidate_cache, invalidate_dashboard_caches

# Configure logging with more detail
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create all database tables
models.Base.metadata.create_all(bind=engine)

def cached(expire_seconds: int = 300, prefix: str = "cache"):
    """Decorator for caching endpoint responses"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get the request object from kwargs
            request = next((kwargs[k] for k in kwargs if isinstance(kwargs[k], Request)), None)
            
            if not request or not hasattr(request.app.state, 'redis') or not request.app.state.redis:
                # No Redis connection or request, just execute the function
                return await func(*args, **kwargs)
            
            # Generate a cache key based on function name and arguments
            # Exclude certain types from the cache key
            cache_args = {}
            for k, v in kwargs.items():
                if not isinstance(v, (Request, Session, models.Admin)):
                    cache_args[k] = v
            
            # Create a cache key with function name and arguments
            cache_key = f"{prefix}:{func.__name__}:{json.dumps(cache_args, sort_keys=True)}"
            
            # Try to get from cache first
            cached_data = await get_cache(cache_key, request)
            if cached_data is not None:
                return cached_data
            
            # Execute the function and cache the result
            result = await func(*args, **kwargs)
            
            # Only cache successful responses (avoid JSONResponse with error status)
            if not isinstance(result, JSONResponse) or getattr(result, 'status_code', 200) < 400:
                await set_cache(cache_key, result, request, expire_seconds)
            
            return result
        return wrapper
    return decorator

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting application initialization...")
    try:
        # Simplified Redis connection
        app.state.redis = None
        redis_client = await get_redis()
        if redis_client:
            await redis_client.ping()
            logger.info("Redis connection established")
            app.state.redis = redis_client

        # Initialize scheduler
        logger.info("Starting scheduler initialization...")
        try:
            # Create a task to run the scheduler
            await asyncio.sleep(1)  # Brief delay to ensure app is ready
            asyncio.create_task(start_scheduler())
            logger.info("Scheduler initialization scheduled in background")
        except Exception as e:
            logger.error(f"Failed to initialize scheduler: {e}")

    except Exception as e:
        logger.error(f"Redis connection failed: {e}")

    logger.info("Application initialization completed")
    yield

    # Cleanup
    if hasattr(app.state, 'redis') and app.state.redis:
        await app.state.redis.close()
        logger.info("Redis connection closed")

app = FastAPI(
    title="InfoAmazonia Admin Dashboard",
    debug=settings.DEBUG,
    lifespan=lifespan
)

# Health check endpoint with enhanced logging
@app.get("/health")
async def health_check():
    try:
        logger.info(f"Health check endpoint called at {datetime.utcnow().isoformat()}")
        # Test database connection
        db = next(get_db())
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        logger.error(f"Database health check failed: {str(e)}")
        db_status = "error"

    response = {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "database": db_status,
        "environment": {
            "debug": settings.DEBUG,
            "log_level": settings.LOG_LEVEL
        }
    }
    logger.info(f"Health check response: {response}")
    return response

# Mount static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Add middleware
app.middleware("http")(auth_middleware)

# Include routers
app.include_router(admin_router)
app.include_router(webhook_router)
app.include_router(location_router)

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        "admin/login.html",
        {"request": request}
    )

@app.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    return templates.TemplateResponse(
        "admin/forgot_password.html",
        {"request": request}
    )

@app.post("/forgot-password", response_class=HTMLResponse)
async def request_password_reset(
    request: Request,
    email: str = Form(...),
    db: Session = Depends(get_db)
):
    # Check if email exists in database
    reset_token = await auth.create_password_reset_token(email, db, request)
    
    # Always show success message, even if email not found (security measure)
    # In a real application, you would send an email with the reset link
    # For demonstration purposes, we'll just provide the link directly
    message = f"If an account with this email exists, a password reset link has been sent."
    
    if reset_token:
        reset_link = f"{request.url_for('reset_password_page')}?token={reset_token}"
        logger.info(f"Password reset requested for {email}. Reset link: {reset_link}")
        message = f"Password reset link: {reset_link}"
    
    return templates.TemplateResponse(
        "admin/forgot_password_confirmation.html",
        {"request": request, "message": message}
    )

@app.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(
    request: Request,
    token: str = Query(...),
    db: Session = Depends(get_db)
):
    # Verify token is valid
    admin = await auth.verify_reset_token(token, db, request)
    if not admin:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    
    return templates.TemplateResponse(
        "admin/reset_password.html",
        {"request": request, "token": token}
    )

@app.post("/reset-password", response_class=HTMLResponse)
async def reset_password_submit(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db)
):
    # Check if passwords match
    if password != confirm_password:
        return templates.TemplateResponse(
            "admin/reset_password.html",
            {
                "request": request, 
                "token": token,
                "error": "Passwords do not match"
            }
        )
    
    # Reset the password
    success = await auth.reset_password(token, password, db, request)
    if not success:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    
    # Redirect to login with success message
    return templates.TemplateResponse(
        "admin/login.html",
        {"request": request, "message": "Password has been reset successfully. You can now log in."}
    )

@app.post("/token")
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    admin = db.query(models.Admin).filter(models.Admin.username == form_data.username).first()
    if not admin or not auth.verify_password(form_data.password, admin.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": admin.username}, expires_delta=access_token_expires
    )
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True)
    return response

@app.get("/", response_class=HTMLResponse)
async def root(request: Request, current_admin: models.Admin = Depends(auth.get_current_admin)):
    return templates.TemplateResponse(
        "admin/index.html",
        {"request": request, "admin": current_admin}
    )

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login")
    response.delete_cookie("access_token")
    return response

@app.get("/api/dashboard/stats")
@cached(expire_seconds=60, prefix="dashboard")  # Cache for 1 minute
async def get_dashboard_stats(request: Request, db: Session = Depends(get_db)):
    try:
        # Get latest metrics
        latest_metrics = db.query(models.Metrics).order_by(desc(models.Metrics.date)).first()

        # Get total and active users
        total_users = db.query(func.count(models.User.id)).scalar()
        active_users = db.query(func.count(models.User.id)).filter(models.User.is_active == True).scalar()

        # Get messages count for last 24 hours
        last_24h = datetime.utcnow() - timedelta(days=1)
        messages_sent = db.query(func.count(models.Message.id))\
            .filter(models.Message.message_type == 'outgoing')\
            .filter(models.Message.status == 'sent')\
            .filter(models.Message.created_at >= last_24h)\
            .scalar()

        # Calculate click rate from latest metrics if available
        click_rate = latest_metrics.click_through_rate if latest_metrics else 0

        return {
            "total_users": total_users,
            "active_users": active_users,
            "messages_sent": messages_sent,
            "click_rate": f"{click_rate:.1f}%"
        }
    except Exception as e:
        logger.error(f"Error fetching dashboard stats: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to fetch dashboard statistics"}
        )

@app.get("/api/dashboard/recent-users")
@cached(expire_seconds=60, prefix="dashboard")  # Cache for 1 minute
async def get_recent_users(request: Request, db: Session = Depends(get_db)):
    try:
        recent_users = db.query(models.User)\
            .order_by(desc(models.User.created_at))\
            .limit(5)\
            .all()

        return [{
            "phone_number": user.phone_number,
            "joined": user.created_at.strftime("%Y-%m-%d %H:%M"),
            "status": "Active" if user.is_active else "Inactive"
        } for user in recent_users]
    except Exception as e:
        logger.error(f"Error fetching recent users: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to fetch recent users"}
        )

@app.get("/api/dashboard/news-sources")
@cached(expire_seconds=60, prefix="dashboard")  # Cache for 1 minute
async def get_news_sources(request: Request, db: Session = Depends(get_db)):
    try:
        sources = db.query(models.NewsSource)\
            .order_by(desc(models.NewsSource.created_at))\
            .limit(5)\
            .all()

        return [{
            "name": source.name,
            "status": "Active" if source.is_active else "Inactive",
            "last_update": source.created_at.strftime("%Y-%m-%d %H:%M")
        } for source in sources]
    except Exception as e:
        logger.error(f"Error fetching news sources: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to fetch news sources"}
        )

@app.get("/api/dashboard/user-stats")
@cached(expire_seconds=300, prefix="dashboard")  # Cache for 5 minutes (longer since this is an expensive query)
async def get_user_stats(request: Request, db: Session = Depends(get_db)):
    try:
        # Get the last 12 weeks of data
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(weeks=12)

        # Format dates for weekly intervals
        weeks = []
        total_users = []
        new_users = []
        cancellations = []

        # Calculate stats for each week
        current_date = start_date
        while current_date <= end_date:
            week_end = current_date + timedelta(days=7)

            # Get total users up to this week
            total = db.query(func.count(models.User.id))\
                .filter(models.User.created_at <= week_end)\
                .scalar()

            # Get new users this week
            new = db.query(func.count(models.User.id))\
                .filter(
                    models.User.created_at > current_date,
                    models.User.created_at <= week_end
                )\
                .scalar()

            # Get cancellations this week (users who became inactive)
            cancelled = db.query(func.count(models.User.id))\
                .filter(
                    models.User.is_active == False,
                    # models.User.updated_at > current_date,
                    # models.User.updated_at <= week_end
                )\
                .scalar()

            # Format date for labels (e.g., "Mar 12")
            week_label = current_date.strftime("%b %d")

            weeks.append(week_label)
            total_users.append(total)
            new_users.append(new)
            cancellations.append(cancelled)

            current_date = week_end

        return {
            "weeks": weeks,
            "total_users": total_users,
            "new_users": new_users,
            "cancellations": cancellations
        }
    except Exception as e:
        logger.error(f"Error fetching user stats: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to fetch user statistics"}
        )

@app.get("/api/dashboard/message-stats")
@cached(expire_seconds=300, prefix="dashboard")  # Cache for 5 minutes (longer since this is an expensive query)
async def get_message_stats(request: Request, db: Session = Depends(get_db)):
    try:
        # Get the last 12 weeks of data
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(weeks=12)

        # Format dates for weekly intervals
        weeks = []
        outgoing_messages = []
        incoming_messages = []

        # Calculate stats for each week
        current_date = start_date
        while current_date <= end_date:
            week_end = current_date + timedelta(days=7)

            # Get outgoing messages for this week
            outgoing = db.query(func.count(models.Message.id))\
                .filter(
                    models.Message.message_type == 'outgoing',
                    models.Message.message_type == 'sent',
                    models.Message.created_at > current_date,
                    models.Message.created_at <= week_end
                )\
                .scalar()

            # Get incoming messages for this week
            incoming = db.query(func.count(models.Message.id))\
                .filter(
                    models.Message.message_type == 'incoming',
                    models.Message.created_at > current_date,
                    models.Message.created_at <= week_end
                )\
                .scalar()

            # Format date for labels (e.g., "Mar 12")
            week_label = current_date.strftime("%b %d")

            weeks.append(week_label)
            outgoing_messages.append(outgoing)
            incoming_messages.append(incoming)

            current_date = week_end

        return {
            "weeks": weeks,
            "outgoing_messages": outgoing_messages,
            "incoming_messages": incoming_messages
        }
    except Exception as e:
        logger.error(f"Error fetching message stats: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to fetch message statistics"}
        )

@app.get("/api/dashboard/status-stats")
@cached(expire_seconds=300, prefix="dashboard")  # Cache for 5 minutes (longer since this is an expensive query)
async def get_status_stats(request: Request, db: Session = Depends(get_db)):
    try:
        # Get the last 12 weeks of data
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(weeks=12)

        # Format dates for weekly intervals
        weeks = []
        received = []
        read = []
        sent = []
        delivered = []
        failed = []  # Track failed statuses

        # Calculate stats for each week
        current_date = start_date
        while current_date <= end_date:
            week_end = current_date + timedelta(days=7)

            # Get received messages for this week
            received_count = db.query(func.count(models.Message.id))\
                .filter(
                    models.Message.status == 'received',
                    models.Message.created_at > current_date,
                    models.Message.created_at <= week_end
                )\
                .scalar()

            # Get read messages for this week
            read_count = db.query(func.count(models.Message.id))\
                .filter(
                    models.Message.status == 'read',
                    models.Message.created_at > current_date,
                    models.Message.created_at <= week_end
                )\
                .scalar()

            # Get sent messages for this week
            sent_count = db.query(func.count(models.Message.id))\
                .filter(
                    models.Message.status == 'sent',
                    models.Message.created_at > current_date,
                    models.Message.created_at <= week_end
                )\
                .scalar()

            # Get delivered messages for this week
            delivered_count = db.query(func.count(models.Message.id))\
                .filter(
                    models.Message.status == 'delivered',
                    models.Message.created_at > current_date,
                    models.Message.created_at <= week_end
                )\
                .scalar()

            # Get failed messages for this week
            failed_count = db.query(func.count(models.Message.id))\
                .filter(
                    models.Message.status == 'failed',
                    models.Message.created_at > current_date,
                    models.Message.created_at <= week_end
                )\
                .scalar()

            # Format date for labels (e.g., "Mar 12")
            week_label = current_date.strftime("%b %d")

            weeks.append(week_label)
            received.append(received_count)
            read.append(read_count)
            sent.append(sent_count)
            delivered.append(delivered_count)
            failed.append(failed_count)

            current_date = week_end

        return {
            "weeks": weeks,
            "received": received,
            "read": read,
            "sent": sent,
            "delivered": delivered,
            "failed": failed  # Include failed statuses in the response
        }
    except Exception as e:
        logger.error(f"Error fetching status stats: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to fetch status statistics"}
        )

@app.get("/api/v1/analytics/ctr-stats")
@cached(expire_seconds=600, prefix="analytics")  # Cache for 10 minutes since it's an external API call
async def get_ctr_stats(request: Request):
    """Get click-through rate statistics from external API"""
    try:
        # Using httpx for HTTP request
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{settings.SEARCH_BASE_URL}/api/v1/analytics/ctr-stats")
            response.raise_for_status()  # Raise an exception for HTTP errors
            return response.json()
    except Exception as e:
        logger.error(f"Error fetching CTR stats: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to fetch click-through rate statistics"}
        )

@app.get("/api/scheduler/runs")
@cached(expire_seconds=120, prefix="scheduler")  # Cache for 2 minutes
async def get_scheduler_runs(
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.Admin = Depends(auth.get_current_admin)
):
    try:
        # Get the last 100 scheduler runs
        runs = db.query(models.SchedulerRun)\
            .order_by(desc(models.SchedulerRun.start_time))\
            .limit(100)\
            .all()

        return [{
            "id": run.id,
            "task_name": run.task_name,
            "status": run.status,
            "start_time": run.start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": run.end_time.strftime("%Y-%m-%d %H:%M:%S") if run.end_time else None,
            "affected_users": run.affected_users,
            "error_message": run.error_message
        } for run in runs]
    except Exception as e:
        logger.error(f"Error fetching scheduler runs: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to fetch scheduler runs"}
        )

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting server on port 5000...")
    # Ensure host is 0.0.0.0 to be accessible
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
        access_log=True
    )