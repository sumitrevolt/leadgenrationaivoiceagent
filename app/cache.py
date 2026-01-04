"""
Redis Cache Module
Production-ready caching with Redis and in-memory fallback
"""
import json
from typing import Any, Optional, Union
from datetime import timedelta
import asyncio

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# =============================================================================
# REDIS CLIENT
# =============================================================================

_redis_client = None
_use_fallback = False


class InMemoryCache:
    """
    In-memory cache fallback when Redis is not available
    Thread-safe for async operations
    """
    
    def __init__(self, max_size: int = 10000):
        self._cache: dict = {}
        self._expiry: dict = {}
        self._max_size = max_size
        self._lock = asyncio.Lock()
    
    async def get(self, key: str) -> Optional[str]:
        """Get value from cache"""
        async with self._lock:
            if key in self._cache:
                # Check expiry
                import time
                if key in self._expiry and self._expiry[key] < time.time():
                    del self._cache[key]
                    del self._expiry[key]
                    return None
                return self._cache[key]
            return None
    
    async def set(
        self,
        key: str,
        value: str,
        ex: Optional[int] = None,
        px: Optional[int] = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        """Set value in cache with optional expiry"""
        async with self._lock:
            # Check nx (only set if not exists)
            if nx and key in self._cache:
                return False
            
            # Check xx (only set if exists)
            if xx and key not in self._cache:
                return False
            
            # Evict old entries if cache is full
            if len(self._cache) >= self._max_size:
                # Simple LRU: remove oldest entry
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
                if oldest_key in self._expiry:
                    del self._expiry[oldest_key]
            
            self._cache[key] = value
            
            # Set expiry
            if ex or px:
                import time
                expiry_seconds = ex if ex else (px / 1000)
                self._expiry[key] = time.time() + expiry_seconds
            
            return True
    
    async def delete(self, key: str) -> int:
        """Delete key from cache"""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                if key in self._expiry:
                    del self._expiry[key]
                return 1
            return 0
    
    async def exists(self, key: str) -> int:
        """Check if key exists"""
        value = await self.get(key)
        return 1 if value is not None else 0
    
    async def incr(self, key: str) -> int:
        """Increment value"""
        async with self._lock:
            if key not in self._cache:
                self._cache[key] = "0"
            current = int(self._cache[key])
            current += 1
            self._cache[key] = str(current)
            return current
    
    async def decr(self, key: str) -> int:
        """Decrement value"""
        async with self._lock:
            if key not in self._cache:
                self._cache[key] = "0"
            current = int(self._cache[key])
            current -= 1
            self._cache[key] = str(current)
            return current
    
    async def expire(self, key: str, seconds: int) -> bool:
        """Set expiry on key"""
        import time
        async with self._lock:
            if key in self._cache:
                self._expiry[key] = time.time() + seconds
                return True
            return False
    
    async def ttl(self, key: str) -> int:
        """Get time to live for key"""
        import time
        async with self._lock:
            if key not in self._expiry:
                return -1
            remaining = int(self._expiry[key] - time.time())
            return max(remaining, 0)
    
    async def keys(self, pattern: str = "*") -> list:
        """Get keys matching pattern (simplified)"""
        async with self._lock:
            if pattern == "*":
                return list(self._cache.keys())
            # Simple pattern matching
            import fnmatch
            return [k for k in self._cache.keys() if fnmatch.fnmatch(k, pattern)]
    
    async def flushdb(self) -> bool:
        """Clear all keys"""
        async with self._lock:
            self._cache.clear()
            self._expiry.clear()
            return True
    
    async def ping(self) -> bool:
        """Health check"""
        return True
    
    async def close(self):
        """Close connection (no-op for in-memory)"""
        pass


# Fallback cache instance
_fallback_cache = InMemoryCache()


async def get_redis_client():
    """
    Get Redis client instance
    Falls back to in-memory cache if Redis is not available
    """
    global _redis_client, _use_fallback
    
    if _use_fallback:
        return _fallback_cache
    
    if _redis_client is not None:
        return _redis_client
    
    try:
        import redis.asyncio as redis
        
        _redis_client = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30,
        )
        
        # Test connection
        await _redis_client.ping()
        logger.info("? Redis client connected")
        return _redis_client
        
    except ImportError:
        logger.warning("redis package not installed, using in-memory cache")
        _use_fallback = True
        return _fallback_cache
        
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}. Using in-memory cache fallback.")
        _use_fallback = True
        return _fallback_cache


async def close_redis_client():
    """Close Redis connection"""
    global _redis_client, _use_fallback
    
    if _redis_client is not None:
        try:
            await _redis_client.close()
            logger.info("? Redis connection closed")
        except Exception as e:
            logger.warning(f"Error closing Redis: {e}")
        finally:
            _redis_client = None
    
    _use_fallback = False


# =============================================================================
# CACHE UTILITIES
# =============================================================================

class CacheService:
    """
    High-level cache service with JSON serialization
    """
    
    def __init__(self, prefix: str = "leadgen"):
        self.prefix = prefix
    
    def _key(self, key: str) -> str:
        """Generate prefixed key"""
        return f"{self.prefix}:{key}"
    
    async def get(self, key: str) -> Optional[Any]:
        """Get and deserialize value"""
        client = await get_redis_client()
        value = await client.get(self._key(key))
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
        ttl: Optional[Union[int, timedelta]] = None,
    ) -> bool:
        """Serialize and set value"""
        client = await get_redis_client()
        
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        elif not isinstance(value, str):
            value = str(value)
        
        if ttl is None:
            ttl = 3600  # Default 1 hour
        elif isinstance(ttl, timedelta):
            ttl = int(ttl.total_seconds())
        
        return await client.set(self._key(key), value, ex=ttl)
    
    async def delete(self, key: str) -> int:
        """Delete key"""
        client = await get_redis_client()
        return await client.delete(self._key(key))
    
    async def exists(self, key: str) -> bool:
        """Check if key exists"""
        client = await get_redis_client()
        return await client.exists(self._key(key)) > 0
    
    async def increment(self, key: str, amount: int = 1) -> int:
        """Increment counter"""
        client = await get_redis_client()
        return await client.incr(self._key(key))
    
    async def set_with_lock(
        self,
        key: str,
        value: Any,
        ttl: int = 3600,
        lock_ttl: int = 10,
    ) -> bool:
        """Set value with distributed lock"""
        client = await get_redis_client()
        lock_key = f"{self._key(key)}:lock"
        
        # Try to acquire lock
        acquired = await client.set(lock_key, "1", ex=lock_ttl, nx=True)
        if not acquired:
            return False
        
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            await client.set(self._key(key), value, ex=ttl)
            return True
        finally:
            await client.delete(lock_key)
    
    async def get_or_set(
        self,
        key: str,
        factory,
        ttl: int = 3600,
    ) -> Any:
        """Get value or compute and set"""
        value = await self.get(key)
        if value is not None:
            return value
        
        # Compute value
        if asyncio.iscoroutinefunction(factory):
            value = await factory()
        else:
            value = factory()
        
        await self.set(key, value, ttl=ttl)
        return value


# Default cache service instance
cache = CacheService()


# =============================================================================
# RATE LIMITING WITH REDIS
# =============================================================================

class RateLimiter:
    """
    Distributed rate limiter using Redis
    Uses sliding window algorithm
    """
    
    def __init__(
        self,
        prefix: str = "ratelimit",
        max_requests: int = 100,
        window_seconds: int = 60,
    ):
        self.prefix = prefix
        self.max_requests = max_requests
        self.window_seconds = window_seconds
    
    def _key(self, identifier: str) -> str:
        """Generate rate limit key"""
        return f"{self.prefix}:{identifier}"
    
    async def is_allowed(self, identifier: str) -> tuple[bool, int]:
        """
        Check if request is allowed
        Returns (allowed, remaining_requests)
        """
        client = await get_redis_client()
        key = self._key(identifier)
        
        # Increment counter
        current = await client.incr(key)
        
        # Set expiry on first request
        if current == 1:
            await client.expire(key, self.window_seconds)
        
        remaining = max(0, self.max_requests - current)
        allowed = current <= self.max_requests
        
        return allowed, remaining
    
    async def get_remaining(self, identifier: str) -> int:
        """Get remaining requests for identifier"""
        client = await get_redis_client()
        key = self._key(identifier)
        
        current = await client.get(key)
        if current is None:
            return self.max_requests
        
        return max(0, self.max_requests - int(current))
    
    async def reset(self, identifier: str) -> bool:
        """Reset rate limit for identifier"""
        client = await get_redis_client()
        key = self._key(identifier)
        return await client.delete(key) > 0


# =============================================================================
# SESSION CACHE
# =============================================================================

class SessionCache:
    """
    User session cache for storing temporary data
    """
    
    def __init__(self, prefix: str = "session"):
        self.prefix = prefix
        self.default_ttl = 3600  # 1 hour
    
    def _key(self, session_id: str, key: str = "") -> str:
        """Generate session key"""
        if key:
            return f"{self.prefix}:{session_id}:{key}"
        return f"{self.prefix}:{session_id}"
    
    async def get(self, session_id: str, key: str) -> Optional[Any]:
        """Get session value"""
        client = await get_redis_client()
        value = await client.get(self._key(session_id, key))
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return None
    
    async def set(
        self,
        session_id: str,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """Set session value"""
        client = await get_redis_client()
        
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        
        return await client.set(
            self._key(session_id, key),
            value,
            ex=ttl or self.default_ttl,
        )
    
    async def delete(self, session_id: str, key: str = "") -> int:
        """Delete session value or entire session"""
        client = await get_redis_client()
        
        if key:
            return await client.delete(self._key(session_id, key))
        
        # Delete all keys for session
        keys = await client.keys(self._key(session_id, "*"))
        if keys:
            return await client.delete(*keys)
        return 0
    
    async def extend(self, session_id: str, ttl: Optional[int] = None) -> bool:
        """Extend session TTL"""
        client = await get_redis_client()
        keys = await client.keys(self._key(session_id, "*"))
        
        for key in keys:
            await client.expire(key, ttl or self.default_ttl)
        
        return True


# Default instances
session_cache = SessionCache()
rate_limiter = RateLimiter(max_requests=settings.rate_limit_per_minute)
