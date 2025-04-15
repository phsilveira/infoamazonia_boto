from fastapi import Request, HTTPException, status
from fastapi.responses import RedirectResponse
from auth import verify_token
from typing import Callable
from database import SessionLocal
import re

async def auth_middleware(request: Request, call_next: Callable):
    # Paths that don't require authentication
    public_paths = ['/login', '/token', '/static', '/webhook', '/forgot-password', '/reset-password']

    # Check if the current path is public
    is_public = any(request.url.path.startswith(path) for path in public_paths)

    if not is_public:
        try:
            # Try to get token from cookie
            token = request.cookies.get("access_token")
            if not token:
                return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

            # Remove 'Bearer ' prefix if present
            token = token.replace("Bearer ", "")

            # Create a new database session
            db = SessionLocal()
            try:
                # Verify token and get admin user
                admin = verify_token(token, db)
                if not admin:
                    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
            finally:
                db.close()

        except Exception:
            return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    response = await call_next(request)
    return response