"""OpenTelemetry setup and custom metric primitives."""

from __future__ import annotations

from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.metrics import Counter, Histogram
from opentelemetry.trace import Tracer

from config import settings

_tracer: Tracer | None = None


def configure_telemetry() -> None:
    """Initialize the OpenTelemetry SDK if enabled."""
    global _tracer
    if not settings.otel_enabled:
        return
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({"service.name": settings.otel_service_name})

    trace_provider = TracerProvider(resource=resource)
    span_exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
    trace_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(trace_provider)

    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

    metric_exporter = OTLPMetricExporter(endpoint=settings.otel_exporter_otlp_endpoint)
    metric_reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=30_000)
    metric_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(metric_provider)

    _tracer = trace.get_tracer(settings.otel_service_name)


def flush_telemetry() -> None:
    if settings.otel_enabled:
        from opentelemetry import metrics as _metrics

        _metrics.get_meter_provider().force_flush()


def shutdown_telemetry() -> None:
    if settings.otel_enabled:
        from opentelemetry import trace as _trace

        _trace.get_tracer_provider().shutdown()


def get_tracer() -> Tracer:
    return _tracer or trace.get_tracer("agentforge-integrations")


class Metrics:
    """Application-level metrics with creation-on-first-use semantics."""

    def __init__(self) -> None:
        self._meter = metrics.get_meter("agentforge-integrations")
        self._counters: dict[str, Counter] = {}
        self._histograms: dict[str, Histogram] = {}

    def counter(self, name: str, unit: str | None = None, description: str | None = None) -> Counter:
        if name not in self._counters:
            self._counters[name] = self._meter.create_counter(name, unit=unit, description=description)
        return self._counters[name]

    def histogram(self, name: str, unit: str | None = None, description: str | None = None) -> Histogram:
        if name not in self._histograms:
            self._histograms[name] = self._meter.create_histogram(name, unit=unit, description=description)
        return self._histograms[name]

    # -- convenience helpers -------------------------------------------------

    def record_api_latency(self, latency_ms: float, path: str, method: str, status: int) -> None:
        self.histogram("api.latency", "ms").record(latency_ms, {"path": path, "method": method})
        self.counter("api.requests").add(1, {"path": path, "method": method, "status": str(status)})

    def record_provider_call(self, provider: str, success: bool, latency_ms: float) -> None:
        self.histogram("provider.latency", "ms").record(latency_ms, {"provider": provider})
        self.counter("provider.calls").add(
            1, {"provider": provider, "outcome": "success" if success else "error"}
        )

    def inc_webhook_retry(self, provider: str) -> None:
        self.counter("webhook.retries").add(1, {"provider": provider})

    def inc_webhook_delivered(self, provider: str, success: bool) -> None:
        self.counter("webhook.deliveries").add(
            1, {"provider": provider, "outcome": "success" if success else "failed"}
        )

    def inc_oauth_refresh(self, provider: str) -> None:
        self.counter("oauth.refresh").add(1, {"provider": provider})

    def inc_webhook_received(self, provider: str) -> None:
        self.counter("webhook.received").add(1, {"provider": provider})


metrics = Metrics()


def start_span(name: str, attributes: dict[str, Any] | None = None) -> Any:
    """Start a span with an ExitStack-style close. Prefer the context manager form."""
    from utils.context import get_correlation_id

    tracer = get_tracer()
    attrs = dict(attributes or {})
    cid = get_correlation_id()
    if cid:
        attrs.setdefault("correlation_id", cid)
    return tracer.start_span(name, attributes=attrs)


def span(name: str, **attributes: Any) -> Any:
    return get_tracer().start_as_current_span(name, attributes=attributes)
