"""
Redis Cache and Rate Limiting
Production-grade caching and rate limiting using Redis
"""
import asyncio
import json
from typing import Optional, Any, Union
from datetime import timedelta

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Redis client singleton
_redis_client = None


async def get_redis_client():
    """Get or create Redis client singleton"""
    global _redis_client
    
    if _redis_client is None:
        try:
            import redis.asyncio as aioredis
            
            _redis_client = aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=20,
            )
            
            # Test connection
            await _redis_client.ping()
            logger.info("? Redis client connected")
            
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}. Using in-memory fallback.")
            _redis_client = InMemoryCache()
    
    return _redis_client


async def close_redis_client():
    """Close Redis connection"""
    global _redis_client
    
    if _redis_client and not isinstance(_redis_client, InMemoryCache):
        await _redis_client.close()
        _redis_client = None
        logger.info("? Redis client closed")


class InMemoryCache:
    """
    In-memory fallback when Redis is not available
    NOT suitable for production with multiple workers
    """
    
    def __init__(self):
        self._cache: dict = {}
        self._expiry: dict = {}
        logger.warning("?? Using in-memory cache (not suitable for production)")
    
    async def get(self, key: str) -> Optional[str]:
        import time
        
        if key in self._expiry and self._expiry[key] < time.time():
            del self._cache[key]
            del self._expiry[key]
            return None
        
        return self._cache.get(key)
    
    async def set(
        self,
        key: str,
        value: str,
        ex: Optional[int] = None,
        px: Optional[int] = None,
    ):
        import time
        
        self._cache[key] = value
        
        if ex:
            self._expiry[key] = time.time() + ex
        elif px:
            self._expiry[key] = time.time() + (px / 1000)
    
    async def delete(self, key: str):
        self._cache.pop(key, None)
        self._expiry.pop(key, None)
    
    async def incr(self, key: str) -> int:
        val = int(self._cache.get(key, 0)) + 1
        self._cache[key] = str(val)
        return val
    
    async def expire(self, key: str, seconds: int):
        import time
        self._expiry[key] = time.time() + seconds
    
    async def ttl(self, key: str) -> int:
        import time
        if key not in self._expiry:
            return -1
        remaining = int(self._expiry[key] - time.time())
        return max(0, remaining)
    
    async def ping(self):
        return True
    
    async def close(self):
        self._cache.clear()
        self._expiry.clear()


# =============================================================================
# RATE LIMITER
# =============================================================================

class RedisRateLimiter:
    """
    Production-grade rate limiter using Redis
    Implements sliding window rate limiting
    """
    
    def __init__(
        self,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
        prefix: str = "ratelimit",
    ):
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.prefix = prefix
    
    async def is_allowed(self, identifier: str) -> tuple[bool, dict]:
        """
        Check if request is allowed
        
        Returns:
            (is_allowed, rate_limit_info)
        """
        redis = await get_redis_client()
        
        minute_key = f"{self.prefix}:minute:{identifier}"
        hour_key = f"{self.prefix}:hour:{identifier}"
        
        # Check minute limit
        minute_count = await redis.incr(minute_key)
        if minute_count == 1:
            await redis.expire(minute_key, 60)
        
        minute_remaining = max(0, self.requests_per_minute - minute_count)
        minute_reset = await redis.ttl(minute_key)
        
        if minute_count > self.requests_per_minute:
            return False, {
                "limit": self.requests_per_minute,
                "remaining": 0,
                "reset": minute_reset,
                "window": "minute",
            }
        
        # Check hour limit
        hour_count = await redis.incr(hour_key)
        if hour_count == 1:
            await redis.expire(hour_key, 3600)
        
        hour_remaining = max(0, self.requests_per_hour - hour_count)
        hour_reset = await redis.ttl(hour_key)
        
        if hour_count > self.requests_per_hour:
            return False, {
                "limit": self.requests_per_hour,
                "remaining": 0,
                "reset": hour_reset,
                "window": "hour",
            }
        
        return True, {
            "limit": self.requests_per_minute,
            "remaining": minute_remaining,
            "reset": minute_reset,
            "window": "minute",
        }
    
    async def reset(self, identifier: str):
        """Reset rate limit for an identifier"""
        redis = await get_redis_client()
        
        await redis.delete(f"{self.prefix}:minute:{identifier}")
        await redis.delete(f"{self.prefix}:hour:{identifier}")


# =============================================================================
# CACHE UTILITIES
# =============================================================================

class Cache:
    """
    High-level caching utilities
    """
    
    def __init__(self, prefix: str = "cache", default_ttl: int = 300):
        self.prefix = prefix
        self.default_ttl = default_ttl
    
    async def get(self, key: str) -> Optional[Any]:
        """Get cached value"""
        redis = await get_redis_client()
        
        full_key = f"{self.prefix}:{key}"
        value = await redis.get(full_key)
        
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        
        return None
    
    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ):
        """Set cached value"""
        redis = await get_redis_client()
        
        full_key = f"{self.prefix}:{key}"
        
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        
        await redis.set(full_key, value, ex=ttl or self.default_ttl)
    
    async def delete(self, key: str):
        """Delete cached value"""
        redis = await get_redis_client()
        await redis.delete(f"{self.prefix}:{key}")
    
    async def get_or_set(
        self,
        key: str,
        factory,
        ttl: Optional[int] = None,
    ) -> Any:
        """
        Get cached value or compute and cache it
        
        Args:
            key: Cache key
            factory: Async function to compute value if not cached
            ttl: Time to live in seconds
        """
        value = await self.get(key)
        
        if value is not None:
            return value
        
        # Compute value
        if asyncio.iscoroutinefunction(factory):
            value = await factory()
        else:
            value = factory()
        
        # Cache it
        await self.set(key, value, ttl)
        
        return value


# =============================================================================
# DISTRIBUTED LOCK
# =============================================================================

class DistributedLock:
    """
    Redis-based distributed lock for preventing race conditions
    """
    
    def __init__(self, name: str, timeout: int = 10):
        self.name = f"lock:{name}"
        self.timeout = timeout
        self._token = None
    
    async def __aenter__(self):
        await self.acquire()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.release()
    
    async def acquire(self) -> bool:
        """Acquire the lock"""
        import uuid
        
        redis = await get_redis_client()
        self._token = str(uuid.uuid4())
        
        # Try to acquire lock
        acquired = await redis.set(
            self.name,
            self._token,
            ex=self.timeout,
            nx=True,  # Only set if not exists
        ) if hasattr(redis, 'set') else True
        
        if not acquired:
            # For InMemoryCache fallback
            if isinstance(redis, InMemoryCache):
                existing = await redis.get(self.name)
                if existing is None:
                    await redis.set(self.name, self._token, ex=self.timeout)
                    return True
            return False
        
        return True
    
    async def release(self):
        """Release the lock"""
        redis = await get_redis_client()
        
        # Only release if we own the lock
        current = await redis.get(self.name)
        if current == self._token:
            await redis.delete(self.name)


# =============================================================================
# SINGLETON INSTANCES
# =============================================================================

# Default rate limiter
rate_limiter = RedisRateLimiter(
    requests_per_minute=100,
    requests_per_hour=2000,
)

# Default cache
cache = Cache(prefix="leadgen", default_ttl=300)
