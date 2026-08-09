import logging
import time
from collections import defaultdict, deque
from threading import Lock
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import settings
from app.observability import request_metrics

logger = logging.getLogger('omniai.http')


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get('X-Request-ID') or str(uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            request_metrics.observe(request.method, request.url.path, 500, time.perf_counter() - started)
            raise
        latency = time.perf_counter() - started
        request_metrics.observe(request.method, request.url.path, response.status_code, latency)
        logger.info(
            'request.complete',
            extra={
                'request_id': request_id,
                'method': request.method,
                'path': request_metrics._normalize_path(request.url.path),
                'status_code': response.status_code,
                'latency_ms': round(latency * 1000, 2),
            },
        )
        response.headers['X-Request-ID'] = request_id
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        response.headers['Cross-Origin-Opener-Policy'] = 'same-origin'
        response.headers['Cross-Origin-Resource-Policy'] = 'same-site'
        if settings.environment.lower() == 'production':
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.events: dict[str, deque[float]] = defaultdict(deque)
        self.lock = Lock()

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith('/health'):
            return await call_next(request)
        limit = max(10, settings.rate_limit_per_minute)
        client = request.client.host if request.client else 'unknown'
        now = time.monotonic()
        with self.lock:
            bucket = self.events[client]
            while bucket and bucket[0] < now - 60:
                bucket.popleft()
            if len(bucket) >= limit:
                return JSONResponse({'detail': 'Rate limit exceeded'}, status_code=429, headers={'Retry-After': '60'})
            bucket.append(now)
        return await call_next(request)
