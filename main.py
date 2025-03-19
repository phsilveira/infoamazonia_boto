from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status, Request
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
from datetime import datetime, timedelta
from sqlalchemy import func, desc

# Configure logging with more detail
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create all database tables
models.Base.metadata.create_all(bind=engine)

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
async def get_dashboard_stats(db: Session = Depends(get_db)):
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
async def get_recent_users(db: Session = Depends(get_db)):
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
async def get_news_sources(db: Session = Depends(get_db)):
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
async def get_user_stats(db: Session = Depends(get_db)):
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
                    models.User.updated_at > current_date,
                    models.User.updated_at <= week_end
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

@app.get("/api/scheduler/runs")
async def get_scheduler_runs(
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