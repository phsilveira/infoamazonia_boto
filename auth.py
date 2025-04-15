from datetime import datetime, timedelta
from typing import Optional
import secrets
import string
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
import models
from database import get_db, SessionLocal
from config import settings
from services.email import send_password_reset_email

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES
RESET_TOKEN_EXPIRE_HOURS = 24  # Token valid for 24 hours

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_token_from_cookie(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token.replace("Bearer ", "")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str, db: Session):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
        admin = db.query(models.Admin).filter(models.Admin.username == username).first()
        return admin
    except JWTError:
        return None

async def get_current_admin(request: Request, db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token = get_token_from_cookie(request)
        admin = verify_token(token, db)
        if admin is None:
            raise credentials_exception
        return admin
    except JWTError:
        raise credentials_exception

def generate_reset_token(length=32):
    """Generate a secure random token for password reset"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

async def create_password_reset_token(email: str, db: Session, request: Request = None):
    """Create a password reset token for a user with the given email using Redis"""
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"Attempting to create password reset token for email: {email}")
    
    admin = db.query(models.Admin).filter(models.Admin.email == email).first()
    if not admin:
        logger.info(f"No admin found with email {email}")
        # Don't reveal that the email doesn't exist
        return None
    
    logger.info(f"Admin found with ID: {admin.id}, username: {admin.username}")
    
    # Generate a secure random token
    reset_token = generate_reset_token()
    logger.info(f"Generated reset token: {reset_token[:5]}...{reset_token[-5:]}")
    
    # Set token expiration (24 hours from now)
    expires = RESET_TOKEN_EXPIRE_HOURS * 3600  # Convert hours to seconds for Redis
    
    if request and hasattr(request.app.state, 'redis') and request.app.state.redis:
        # Store token in Redis with expiration
        # Format: reset:{token} = admin_id
        redis_key = f"reset:{reset_token}"
        logger.info(f"Storing token in Redis with key: {redis_key}, admin ID: {admin.id}, expiration: {expires}s")
        
        try:
            await request.app.state.redis.set(redis_key, str(admin.id), ex=expires)
            logger.info("Token successfully stored in Redis")
        except Exception as e:
            logger.error(f"Failed to store token in Redis: {str(e)}")
            return None
    else:
        # Fallback if Redis is not available - we won't store the token
        logger.error("Redis not available for password reset token storage")
        if not request:
            logger.error("Request object is None")
        elif not hasattr(request.app.state, 'redis'):
            logger.error("app.state does not have redis attribute")
        elif not request.app.state.redis:
            logger.error("app.state.redis is None")
        return None
    
    logger.info(f"Returning reset token: {reset_token[:5]}...{reset_token[-5:]}")
    return reset_token

async def verify_reset_token(token: str, db: Session, request: Request = None):
    """Verify if a password reset token is valid and return the associated admin"""
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"Verifying reset token: {token[:5]}...{token[-5:]}")
    
    if not request:
        logger.error("Request object is None during token verification")
        return None
    elif not hasattr(request.app.state, 'redis'):
        logger.error("app.state does not have redis attribute during token verification")
        return None
    elif not request.app.state.redis:
        logger.error("app.state.redis is None during token verification")
        return None
    
    # Format: reset:{token} = admin_id
    redis_key = f"reset:{token}"
    logger.info(f"Looking up Redis key: {redis_key}")
    
    try:
        admin_id = await request.app.state.redis.get(redis_key)
        logger.info(f"Redis lookup result: {admin_id}")
        
        if not admin_id:
            logger.info(f"No admin ID found for token in Redis")
            return None
        
        # Get admin from database
        admin = db.query(models.Admin).filter(models.Admin.id == int(admin_id)).first()
        
        if admin:
            logger.info(f"Admin found with ID: {admin.id}, username: {admin.username}")
        else:
            logger.info(f"No admin found with ID: {admin_id}")
            
        return admin
    except Exception as e:
        logger.error(f"Error verifying reset token: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None

async def reset_password(token: str, new_password: str, db: Session, request: Request = None):
    """Reset a user's password using a valid reset token stored in Redis"""
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"Attempting to reset password with token: {token[:5]}...{token[-5:]}")
    
    admin = await verify_reset_token(token, db, request)
    
    if not admin:
        logger.error("Failed to verify reset token")
        return False
    
    logger.info(f"Token verified successfully for admin: {admin.id}, {admin.username}")
    
    try:    
        # Update password
        admin.hashed_password = get_password_hash(new_password)
        logger.info("Password hashed successfully")
        
        db.commit()
        logger.info("Password updated in database")
        
        # Delete the token from Redis
        if request and hasattr(request.app.state, 'redis') and request.app.state.redis:
            redis_key = f"reset:{token}"
            logger.info(f"Deleting token from Redis: {redis_key}")
            await request.app.state.redis.delete(redis_key)
            logger.info("Token deleted from Redis")
        else:
            logger.warning("Could not delete token from Redis - Redis not available")
        
        return True
    except Exception as e:
        logger.error(f"Error resetting password: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False