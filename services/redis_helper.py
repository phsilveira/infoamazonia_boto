import logging
from typing import Optional, Any, List
from fastapi import Request
import json

logger = logging.getLogger(__name__)

class RedisHelper:
    """Redis utility class for URL shortening and CTR tracking"""
    
    @staticmethod
    async def get_redis_client(request: Request):
        """Get Redis client from FastAPI app state"""
        if not hasattr(request.app.state, 'redis') or not request.app.state.redis:
            return None
        return request.app.state.redis
    
    @staticmethod
    async def set_value(key: str, value: Any, request: Request, expire: Optional[int] = None):
        """Set value in Redis with optional expiration"""
        redis_client = await RedisHelper.get_redis_client(request)
        if not redis_client:
            return False
        
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            
            if expire:
                await redis_client.setex(key, expire, value)
            else:
                await redis_client.set(key, value)
            return True
        except Exception as e:
            logger.error(f"Error setting Redis value for key {key}: {e}")
            return False
    
    @staticmethod
    async def get_value(key: str, request: Request) -> Optional[Any]:
        """Get value from Redis"""
        redis_client = await RedisHelper.get_redis_client(request)
        if not redis_client:
            return None
        
        try:
            value = await redis_client.get(key)
            if value:
                # Try to parse as JSON, if it fails return as string
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
            return None
        except Exception as e:
            logger.error(f"Error getting Redis value for key {key}: {e}")
            return None
    
    @staticmethod
    async def increment(key: str, request: Request, expire: Optional[int] = None):
        """Increment value in Redis"""
        redis_client = await RedisHelper.get_redis_client(request)
        if not redis_client:
            return False
        
        try:
            result = await redis_client.incr(key)
            if expire:
                await redis_client.expire(key, expire)
            return result
        except Exception as e:
            logger.error(f"Error incrementing Redis value for key {key}: {e}")
            return False
    
    @staticmethod
    async def exists(key: str, request: Request) -> bool:
        """Check if key exists in Redis"""
        redis_client = await RedisHelper.get_redis_client(request)
        if not redis_client:
            return False
        
        try:
            return await redis_client.exists(key)
        except Exception as e:
            logger.error(f"Error checking Redis key existence {key}: {e}")
            return False
    
    @staticmethod
    async def get_keys_pattern(pattern: str, request: Request) -> List[str]:
        """Get keys matching pattern from Redis"""
        redis_client = await RedisHelper.get_redis_client(request)
        if not redis_client:
            return []
        
        try:
            keys = await redis_client.keys(pattern)
            return [key.decode('utf-8') if isinstance(key, bytes) else key for key in keys]
        except Exception as e:
            logger.error(f"Error getting Redis keys with pattern {pattern}: {e}")
            return []
    
    @staticmethod
    async def delete_key(key: str, request: Request) -> bool:
        """Delete key from Redis"""
        redis_client = await RedisHelper.get_redis_client(request)
        if not redis_client:
            return False
        
        try:
            await redis_client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Error deleting Redis key {key}: {e}")
            return False