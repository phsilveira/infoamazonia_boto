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

def create_password_reset_token(email: str, db: Session):
    """Create a password reset token for a user with the given email"""
    admin = db.query(models.Admin).filter(models.Admin.email == email).first()
    if not admin:
        # Don't reveal that the email doesn't exist
        return None
    
    # Generate a secure random token
    reset_token = generate_reset_token()
    
    # Set token expiration (24 hours from now)
    expires = datetime.utcnow() + timedelta(hours=RESET_TOKEN_EXPIRE_HOURS)
    
    # Save the token and expiration in the database
    admin.reset_token = reset_token
    admin.reset_token_expires = expires
    db.commit()
    
    return reset_token

def verify_reset_token(token: str, db: Session):
    """Verify if a password reset token is valid and return the associated admin"""
    admin = db.query(models.Admin).filter(models.Admin.reset_token == token).first()
    
    if not admin:
        return None
        
    # Check if token is expired
    if admin.reset_token_expires and admin.reset_token_expires < datetime.utcnow():
        return None
        
    return admin

def reset_password(token: str, new_password: str, db: Session):
    """Reset a user's password using a valid reset token"""
    admin = verify_reset_token(token, db)
    
    if not admin:
        return False
        
    # Update password
    admin.hashed_password = get_password_hash(new_password)
    
    # Clear the reset token
    admin.reset_token = None
    admin.reset_token_expires = None
    
    db.commit()
    return True