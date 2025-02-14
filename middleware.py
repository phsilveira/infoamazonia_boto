from fastapi import Request, HTTPException, status
from fastapi.responses import RedirectResponse
from auth import get_current_admin, get_token_from_cookie
from typing import Callable
import re

async def auth_middleware(request: Request, call_next: Callable):
    # Paths that don't require authentication
    public_paths = ['/login', '/token', '/static']
    
    # Check if the current path is public
    is_public = any(request.url.path.startswith(path) for path in public_paths)
    
    if not is_public:
        try:
            # Try to get token from cookie
            token = request.cookies.get("access_token")
            if not token:
                return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
            
            # Verify token and get admin user
            await get_current_admin(request)
        except HTTPException:
            return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    response = await call_next(request)
    return response
