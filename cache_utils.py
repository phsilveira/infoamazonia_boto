import logging
import json
from typing import Any, Optional

logger = logging.getLogger(__name__)

async def get_cache(key: str, request):
    """Get data from Redis cache if available"""
    if not hasattr(request.app.state, 'redis') or not request.app.state.redis:
        return None
    
    try:
        cached_value = await request.app.state.redis.get(key)
        if cached_value:
            logger.debug(f"Cache hit for key: {key}")
            return json.loads(cached_value)
        logger.debug(f"Cache miss for key: {key}")
        return None
    except Exception as e:
        logger.error(f"Error retrieving from cache: {e}")
        return None

async def set_cache(key: str, data: Any, request, expire_seconds: int = 300):
    """Set data in Redis cache with expiration time (default 5 minutes)"""
    if not hasattr(request.app.state, 'redis') or not request.app.state.redis:
        return False
    
    try:
        serialized_data = json.dumps(data)
        await request.app.state.redis.setex(key, expire_seconds, serialized_data)
        logger.debug(f"Cache set for key: {key}, expires in {expire_seconds}s")
        return True
    except Exception as e:
        logger.error(f"Error setting cache: {e}")
        return False

async def invalidate_cache(pattern: str, request):
    """Invalidate cache keys matching pattern"""
    if not hasattr(request.app.state, 'redis') or not request.app.state.redis:
        return False
    
    try:
        keys = await request.app.state.redis.keys(pattern)
        if keys:
            await request.app.state.redis.delete(*keys)
            logger.debug(f"Invalidated {len(keys)} cache keys matching pattern: {pattern}")
        return True
    except Exception as e:
        logger.error(f"Error invalidating cache: {e}")
        return False

async def invalidate_dashboard_caches(request):
    """Utility to invalidate all dashboard caches when data is updated"""
    try:
        patterns = [
            "dashboard:*",
            "analytics:*",
            "scheduler:*"
        ]
        count = 0
        for pattern in patterns:
            keys = await request.app.state.redis.keys(pattern)
            if keys:
                await request.app.state.redis.delete(*keys)
                count += len(keys)
        
        if count > 0:
            logger.info(f"Invalidated {count} cache entries after data update")
        return True
    except Exception as e:
        logger.error(f"Error invalidating dashboard caches: {e}")
        return False