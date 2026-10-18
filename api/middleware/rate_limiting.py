import time
from typing import Dict, Tuple
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import asyncio
from collections import defaultdict, deque

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Advanced rate limiting middleware with sliding window algorithm"""
    
    def __init__(self, app, requests_per_minute: int = 60, burst_limit: int = 10):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.burst_limit = burst_limit
        self.clients: Dict[str, deque] = defaultdict(deque)
        self.burst_clients: Dict[str, int] = defaultdict(int)
        self.burst_reset: Dict[str, float] = defaultdict(float)
    
    def get_client_ip(self, request: Request) -> str:
        """Extract client IP with proxy support"""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        return request.client.host if request.client else "unknown"
    
    def is_rate_limited(self, client_ip: str) -> Tuple[bool, Dict[str, any]]:
        """Check if client is rate limited using sliding window"""
        now = time.time()
        window_start = now - 60  # 1 minute window
        
        # Clean old entries
        client_requests = self.clients[client_ip]
        while client_requests and client_requests[0] < window_start:
            client_requests.popleft()
        
        # Check burst protection (reset every 10 seconds)
        if now - self.burst_reset[client_ip] > 10:
            self.burst_clients[client_ip] = 0
            self.burst_reset[client_ip] = now
        
        # Check limits
        requests_in_window = len(client_requests)
        burst_requests = self.burst_clients[client_ip]
        
        rate_limited = (
            requests_in_window >= self.requests_per_minute or 
            burst_requests >= self.burst_limit
        )
        
        if not rate_limited:
            client_requests.append(now)
            self.burst_clients[client_ip] += 1
        
        return rate_limited, {
            "requests_in_window": requests_in_window,
            "burst_requests": burst_requests,
            "window_reset": int(window_start + 60),
            "burst_reset": int(self.burst_reset[client_ip] + 10)
        }
    
    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip rate limiting for health checks and internal endpoints
        if request.url.path in ["/health", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)
        
        client_ip = self.get_client_ip(request)
        is_limited, rate_info = self.is_rate_limited(client_ip)
        
        if is_limited:
            return Response(
                content={
                    "success": False,
                    "error": "RATE_LIMIT_EXCEEDED",
                    "message": "Too many requests. Please try again later.",
                    "retry_after": max(rate_info["window_reset"] - int(time.time()), 1),
                    "limits": {
                        "per_minute": self.requests_per_minute,
                        "burst": self.burst_limit
                    }
                },
                status_code=429,
                headers={
                    "X-RateLimit-Limit": str(self.requests_per_minute),
                    "X-RateLimit-Remaining": str(max(0, self.requests_per_minute - rate_info["requests_in_window"])),
                    "X-RateLimit-Reset": str(rate_info["window_reset"]),
                    "Retry-After": str(max(rate_info["window_reset"] - int(time.time()), 1))
                }
            )
        
        response = await call_next(request)
        
        # Add rate limit headers to successful responses
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(max(0, self.requests_per_minute - rate_info["requests_in_window"]))
        response.headers["X-RateLimit-Reset"] = str(rate_info["window_reset"])
        
        return response

class AdvancedRateLimitMiddleware(BaseHTTPMiddleware):
    """Advanced rate limiting with different limits for different endpoints"""
    
    def __init__(self, app):
        super().__init__(app)
        self.endpoint_limits = {
            "/companies": {"per_minute": 100, "burst": 20},
            "/search": {"per_minute": 30, "burst": 5},
            "/download": {"per_minute": 10, "burst": 2},
            "/bulk": {"per_minute": 20, "burst": 3},
            "default": {"per_minute": 60, "burst": 10}
        }
        self.clients: Dict[str, Dict[str, deque]] = defaultdict(lambda: defaultdict(deque))
    
    def get_endpoint_category(self, path: str) -> str:
        """Categorize endpoint for rate limiting"""
        for pattern, limits in self.endpoint_limits.items():
            if pattern in path:
                return pattern
        return "default"
    
    async def dispatch(self, request: Request, call_next) -> Response:
        # Implementation would be similar to RateLimitMiddleware but with per-endpoint limits
        return await call_next(request)
