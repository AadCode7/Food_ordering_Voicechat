"""OpenTelemetry tracing + lightweight in-app metrics. Fails soft if OTel is unavailable."""
from __future__ import annotations

import time
from contextlib import contextmanager

from config import settings
from utils.metrics import metrics

from .setup import get_logger

log = get_logger("telemetry")
_tracer = None
_ready = False


def setup_telemetry(app=None) -> None:
    global _tracer, _ready
    if _ready:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

        provider = TracerProvider(resource=Resource.create({"service.name": settings.otel_service_name}))
        if settings.otel_console:
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        if settings.otel_endpoint:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_endpoint)))
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("foodbot")
        if app is not None:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(app)
        _ready = True
        log.info("telemetry ready")
    except Exception as exc:  # never break the app because of monitoring
        log.warning("telemetry disabled: %s", exc)


@contextmanager
def span(name: str, **attrs):
    """Trace span + latency metric in one. Safe to use even if tracing is off."""
    start = time.perf_counter()
    metrics.inc(f"calls.{name}")
    try:
        if _tracer is None:
            yield None
        else:
            with _tracer.start_as_current_span(name) as sp:
                for key, value in attrs.items():
                    if isinstance(value, (str, int, float, bool)):
                        sp.set_attribute(key, value)
                yield sp
    except Exception:
        metrics.inc(f"errors.{name}")
        raise
    finally:
        metrics.observe(name, (time.perf_counter() - start) * 1000)
