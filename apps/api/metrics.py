"""Prometheus metrics + middleware (design Section 13.5). Owner: Tarun."""
from __future__ import annotations

import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUESTS = Counter("processiq_http_requests_total", "HTTP requests",
                   ["method", "path", "status"])
LATENCY = Histogram("processiq_http_request_seconds", "HTTP request latency", ["method", "path"])
JOBS = Counter("processiq_jobs_total", "Jobs processed", ["status"])


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        path = request.scope.get("route").path if request.scope.get("route") else request.url.path
        REQUESTS.labels(request.method, path, response.status_code).inc()
        LATENCY.labels(request.method, path).observe(time.perf_counter() - start)
        return response


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
