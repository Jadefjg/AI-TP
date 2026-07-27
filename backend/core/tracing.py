from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")
trace_id_ctx: ContextVar[str] = ContextVar("trace_id", default="")

_otel_configured = False


def get_request_id() -> str:
    return request_id_ctx.get() or ""


def get_trace_id() -> str:
    return trace_id_ctx.get() or get_request_id()


def setup_tracing():
    """可选 OpenTelemetry：设置 OTEL_EXPORTER_OTLP_ENDPOINT 时启用。返回 FastAPIInstrumentor 类或 None。"""
    global _otel_configured
    if _otel_configured:
        return
    from backend.core.config import get_settings

    endpoint = (get_settings().otel_exporter_otlp_endpoint or "").strip()
    if not endpoint:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({"service.name": get_settings().otel_service_name})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        trace.set_tracer_provider(provider)
        _otel_configured = True
        logger.info("OpenTelemetry tracing enabled -> %s", endpoint)
        return FastAPIInstrumentor
    except Exception as exc:  # noqa: BLE001
        logger.warning("OpenTelemetry setup skipped: %s", exc)
        return None


class RequestTracingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        tid = request.headers.get("X-Trace-ID") or rid
        request_id_ctx.set(rid)
        trace_id_ctx.set(tid)
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        response.headers["X-Trace-ID"] = tid
        return response


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path == "/metrics":
            return await call_next(request)
        from time import perf_counter

        from backend.core.metrics import HTTP_LATENCY, HTTP_REQUESTS

        start = perf_counter()
        status_code = 500
        path_template = request.url.path
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            elapsed = perf_counter() - start
            method = request.method
            HTTP_REQUESTS.labels(method=method, path_template=path_template, status=str(status_code)).inc()
            HTTP_LATENCY.labels(method=method, path_template=path_template).observe(elapsed)
