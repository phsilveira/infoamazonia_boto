from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Query
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
import models, schemas, auth
from database import engine, get_db, init_db
from admin import router as admin_router
from webhook import router as webhook_router
from routers.location import router as location_router
from api_endpoints import router as api_router
from datetime import timedelta
from typing import Optional
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from middleware import auth_middleware
from scheduler import start_scheduler
from config import settings, get_redis
import redis.asyncio as redis
import logging
import asyncio
import sys
import os
import traceback
import httpx
import json
from datetime import datetime, timedelta
from sqlalchemy import func, desc
from functools import wraps
from cache_utils import get_cache, set_cache, invalidate_cache, invalidate_dashboard_caches
from services.email import send_password_reset_email

# Configure logging with more detail
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Log deployment environment information at startup
logger.info("=== Application Startup Information ===")
logger.info(f"Python version: {sys.version}")
logger.info(f"FastAPI app starting with debug mode: {settings.DEBUG}")
logger.info(f"Log level: {settings.LOG_LEVEL}")
logger.info(f"Database URL configured: {'Yes' if hasattr(settings, 'DATABASE_URL') and settings.DATABASE_URL else 'No'}")
logger.info(f"Redis configured: {'Yes' if settings.REDIS_HOST and settings.REDIS_PORT else 'No'}")
logger.info(f"OpenAI configured: {'Yes' if hasattr(settings, 'OPENAI_API_KEY') and settings.OPENAI_API_KEY else 'No'}")
logger.info("=====================================")

# Create all database tables
init_db()
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
    logger.info("=== Starting Application Lifespan Management ===")
    startup_errors = []
    
    try:
        logger.info("Initializing database connection...")
        # Test database connection at startup
        try:
            from sqlalchemy import text
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            logger.info("✓ Database connection verified successfully")
        except Exception as e:
            error_msg = f"✗ Database connection failed: {e}"
            logger.error(error_msg)
            startup_errors.append(error_msg)
            # Don't fail completely, but log the error
        
        # Initialize Redis connection
        logger.info("Initializing Redis connection...")
        app.state.redis = None
        try:
            redis_client = await get_redis()
            if redis_client:
                await redis_client.ping()
                logger.info("✓ Redis connection established successfully")
                app.state.redis = redis_client
            else:
                logger.warning("✗ Redis client creation returned None")
                startup_errors.append("Redis client creation failed")
        except Exception as e:
            error_msg = f"✗ Redis connection failed: {e}"
            logger.error(error_msg)
            logger.error(f"Redis error traceback: {traceback.format_exc()}")
            startup_errors.append(error_msg)

        # Initialize scheduler
        logger.info("Initializing background scheduler...")
        try:
            # Create a task to run the scheduler
            await asyncio.sleep(1)  # Brief delay to ensure app is ready
            asyncio.create_task(start_scheduler())
            logger.info("✓ Scheduler initialization scheduled in background")
        except Exception as e:
            error_msg = f"✗ Scheduler initialization failed: {e}"
            logger.error(error_msg)
            logger.error(f"Scheduler error traceback: {traceback.format_exc()}")
            startup_errors.append(error_msg)

        # Log startup summary
        if startup_errors:
            logger.warning(f"Application started with {len(startup_errors)} warnings/errors:")
            for error in startup_errors:
                logger.warning(f"  - {error}")
            logger.warning("Application may have reduced functionality but will continue running")
        else:
            logger.info("✓ All components initialized successfully")
            
        logger.info("=== Application startup completed ===")
        
    except Exception as e:
        logger.critical(f"✗ Critical startup failure: {e}")
        logger.critical(f"Critical error traceback: {traceback.format_exc()}")
        # Allow the app to continue even with critical errors for debugging
        
    yield

    # Cleanup
    logger.info("=== Starting Application Shutdown ===")
    try:
        if hasattr(app.state, 'redis') and app.state.redis:
            await app.state.redis.close()
            logger.info("✓ Redis connection closed")
    except Exception as e:
        logger.error(f"Error during Redis cleanup: {e}")
    
    logger.info("=== Application shutdown completed ===")

app = FastAPI(
    title="InfoAmazonia Admin Dashboard",
    debug=settings.DEBUG,
    lifespan=lifespan
)

# Health check endpoint with comprehensive status
@app.get("/health")
async def health_check(request: Request):
    logger.info(f"Health check endpoint called at {datetime.utcnow().isoformat()}")
    
    # Check database
    try:
        from sqlalchemy import text
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        db_status = "ok"
        db_error = None
    except Exception as e:
        logger.error(f"Database health check failed: {str(e)}")
        db_status = "error"
        db_error = str(e)
    
    # Check Redis
    redis_status = "not_configured"
    redis_error = None
    if hasattr(request.app.state, 'redis') and request.app.state.redis:
        try:
            await request.app.state.redis.ping()
            redis_status = "ok"
        except Exception as e:
            logger.error(f"Redis health check failed: {str(e)}")
            redis_status = "error"
            redis_error = str(e)
    else:
        redis_status = "not_connected"

    response = {
        "status": "ok" if db_status == "ok" else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "components": {
            "database": {
                "status": db_status,
                "error": db_error
            },
            "redis": {
                "status": redis_status,
                "error": redis_error
            }
        },
        "environment": {
            "debug": settings.DEBUG,
            "log_level": settings.LOG_LEVEL,
            "host": request.url.hostname,
            "port": request.url.port
        }
    }
    
    status_code = 200 if response["status"] == "ok" else 503
    logger.info(f"Health check response (status {status_code}): {response}")
    
    return JSONResponse(content=response, status_code=status_code)

# Startup verification endpoint for deployment debugging
@app.get("/startup-status")
async def startup_status():
    """Detailed startup status for deployment debugging"""
    return {
        "app_title": app.title,
        "startup_time": datetime.utcnow().isoformat(),
        "environment": {
            "python_version": sys.version,
            "debug_mode": settings.DEBUG,
            "log_level": settings.LOG_LEVEL,
        },
        "configuration": {
            "database_configured": hasattr(settings, 'DATABASE_URL') and bool(settings.DATABASE_URL),
            "redis_configured": bool(settings.REDIS_HOST and settings.REDIS_PORT),
            "openai_configured": hasattr(settings, 'OPENAI_API_KEY') and bool(settings.OPENAI_API_KEY),
        },
        "message": "Application startup verification endpoint"
    }

# Shortened URL redirect endpoint
@app.get("/r/{short_id}")
async def redirect_to_url(short_id: str, request: Request):
    """
    Redirect to the original URL and track click metrics.
    """
    # Get Redis client from app state
    redis_client = getattr(request.app.state, 'redis', None)
    
    # Try to get original URL from Redis first
    original_url = None
    if redis_client:
        try:
            original_url = await redis_client.get(f"url:{short_id}")
            # Decode bytes if necessary
            if isinstance(original_url, bytes):
                original_url = original_url.decode()
            # Increment click count
            await redis_client.incr(f"clicks:{short_id}")
            await redis_client.expire(f"clicks:{short_id}", 86400 * 30)  # Refresh expiration
        except Exception as e:
            logger.error(f"Redis error in redirect_to_url: {e}")
    
    # Fallback to in-memory cache
    if not original_url:
        from services.search import url_cache, url_clicks_cache
        original_url = url_cache.get(short_id)
        if original_url:
            url_clicks_cache[short_id] = url_clicks_cache.get(short_id, 0) + 1
    
    if original_url:
        # Ensure original_url is a string
        if isinstance(original_url, bytes):
            original_url = original_url.decode()
        
        # Add UTM parameters to the redirect URL
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
        parsed_url = urlparse(original_url)
        query_params = parse_qs(parsed_url.query)
        
        # Add UTM parameters
        query_params.update({
            "utmSource": ["whatsapp"],
            "utmMedium": ["news"]
        })
        
        # Reconstruct the URL with UTM parameters
        new_query = urlencode(query_params, doseq=True)
        redirect_url = urlunparse((
            parsed_url.scheme,
            parsed_url.netloc,
            parsed_url.path,
            parsed_url.params,
            new_query,
            parsed_url.fragment
        ))
        
        return RedirectResponse(url=redirect_url, status_code=302)
    else:
        raise HTTPException(status_code=404, detail="URL not found")

# Mount static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Add middleware
app.middleware("http")(auth_middleware)

# Include routers
app.include_router(admin_router)
app.include_router(webhook_router)
app.include_router(location_router)
app.include_router(api_router)

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: Optional[str] = None):
    return templates.TemplateResponse(
        "admin/login.html",
        {"request": request, "error": error}
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
    # Log the request
    logger.info(f"Password reset requested for email: {email}")
    
    # Check if email exists in database
    logger.info("Attempting to create password reset token...")
    reset_token = await auth.create_password_reset_token(email, db, request)
    
    # Log token status
    if reset_token:
        logger.info(f"Token generated successfully for {email}: {reset_token[:5]}...{reset_token[-5:]}")
    else:
        logger.info(f"No token generated for {email} - email not found or Redis error")
    
    # Always show success message, even if email not found (security measure)
    message = f"Se uma conta com esse email exists, o link será enviado para o email cadastrado."
    
    if reset_token:
        # Generate the reset link with the token
        # Use URL for directly to avoid duplicating the base URL
        reset_url = request.url_for('reset_password_page')
        reset_link = f"{reset_url}?token={reset_token}"
        
        # Log the reset link details (be careful in production environments)
        logger.info(f"Generated reset link: {reset_link}")
        
        logger.info(f"Attempting to send password reset email to {email}...")
        # Send the password reset email
        email_sent = send_password_reset_email(email, reset_link)
        
        if email_sent:
            logger.info(f"Password reset email successfully sent to {email}")
        else:
            logger.error(f"Failed to send password reset email to {email}")
            # Still show success message to prevent user enumeration
    
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
        {"request": request, "message": "Senha foi redefinida com sucesso. Você pode agora entrar."}
    )

@app.post("/token")
async def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    # Check if input is a username or email
    from sqlalchemy import or_
    admin = db.query(models.Admin).filter(
        or_(
            models.Admin.username == form_data.username,
            models.Admin.email == form_data.username
        )
    ).first()
    
    if not admin or not auth.verify_password(form_data.password, admin.hashed_password):
        # Instead of raising an exception, return to login page with error
        return templates.TemplateResponse(
            "admin/login.html",
            {
                "request": request, 
                "error": "Usuário ou senha incorretos"
            },
            status_code=status.HTTP_401_UNAUTHORIZED
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
@cached(expire_seconds=300, prefix="dashboard")  # Cache for 1 minute
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

        # Calculate click rate using CTR stats function logic
        # Get Redis client from app state
        redis_client = getattr(request.app.state, 'redis', None)
        
        # Import caches from search service
        from services.search import url_impressions_cache, url_clicks_cache, url_cache
        
        # Get short IDs from both Redis and in-memory cache
        short_ids = set()
        
        # Get short IDs from Redis if available
        if redis_client:
            try:
                # Get all impression keys from Redis
                impression_keys = await redis_client.keys("impressions:*")
                for key in impression_keys:
                    if isinstance(key, bytes):
                        key = key.decode('utf-8')
                    short_id = key.split(":")[-1]
                    short_ids.add(short_id)
            except Exception as e:
                logger.error(f"Error getting impression keys from Redis: {e}")

        # Also check in-memory cache for fallback
        short_ids.update(url_impressions_cache.keys())
        
        # Calculate overall CTR
        total_impressions = 0
        total_clicks = 0
        
        for short_id in short_ids:
            impressions = 0
            clicks = 0

            # Try to get data from Redis first
            if redis_client:
                try:
                    imp_val = await redis_client.get(f"impressions:{short_id}")
                    click_val = await redis_client.get(f"clicks:{short_id}")
                    impressions = int(imp_val) if imp_val else 0
                    clicks = int(click_val) if click_val else 0
                except Exception as e:
                    logger.error(f"Error getting data from Redis for {short_id}: {e}")

            # Fallback to in-memory cache if Redis failed or returned no data
            if impressions == 0 and clicks == 0:
                impressions = url_impressions_cache.get(short_id, 0)
                clicks = url_clicks_cache.get(short_id, 0)
            
            total_impressions += impressions
            total_clicks += clicks
        
        # Calculate overall CTR
        click_rate = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0

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
@cached(expire_seconds=300, prefix="dashboard")  # Cache for 1 minute
async def get_recent_users(request: Request, db: Session = Depends(get_db)):
    try:
        recent_users = db.query(models.User)\
            .order_by(desc(models.User.created_at))\
            .limit(5)\
            .all()

        return [{
            "phone_number": user.phone_number,
            "joined": user.created_at.strftime("%d/%m/%Y %H:%M"),
            "status": "Active" if bool(user.is_active) else "Inactive"
        } for user in recent_users]
    except Exception as e:
        logger.error(f"Error fetching recent users: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to fetch recent users"}
        )

@app.get("/api/dashboard/news-sources")
@cached(expire_seconds=300, prefix="dashboard")  # Cache for 1 minute
async def get_news_sources(request: Request, db: Session = Depends(get_db)):
    try:
        sources = db.query(models.NewsSource)\
            .order_by(desc(models.NewsSource.created_at))\
            .limit(5)\
            .all()

        return [{
            "name": source.name,
            "status": "Active" if bool(source.is_active) else "Inactive",
            "last_update": source.created_at.strftime("%d/%m/%Y %H:%M")
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
                    models.Message.status == 'sent',
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
            "start_time": run.start_time.strftime("%d/%m/%Y %H:%M:%S"),
            "end_time": run.end_time.strftime("%d/%m/%Y %H:%M:%S") if run.end_time is not None else None,
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
    # Use PORT environment variable for deployment compatibility
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting server on port {port}...")
    # Ensure host is 0.0.0.0 to be accessible
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=settings.DEBUG,  # Only reload in debug mode
        log_level="info",
        # access_log=True
    )