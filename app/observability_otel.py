"""OpenTelemetry distributed tracing — import-safe, OFF by default.

Sentry already errors capture karta; yeh module **end-to-end traces** deta
(FastAPI request -> SQLAlchemy query -> Redis -> outbound httpx) taaki "slow/fail
kahan aur kyun" dikhe. Grafana Tempo/LGTM stack me feed hota.

ZERO behaviour change by default:
  - `ENABLE_OTEL` env "1"/"true" na ho to seedha return (no-op).
  - opentelemetry packages installed na ho to graceful skip (sirf log).

Enable karne ke liye:
  pip install opentelemetry-distro opentelemetry-exporter-otlp \
              opentelemetry-instrumentation-fastapi \
              opentelemetry-instrumentation-sqlalchemy \
              opentelemetry-instrumentation-redis \
              opentelemetry-instrumentation-httpx
  ENABLE_OTEL=1
  OTEL_EXPORTER_OTLP_ENDPOINT=http://tempo:4317   # deploy/compose/docker-compose.observability.yml

Reference stack: github.com/blueswen/fastapi-observability (Tempo+Loki+Prometheus+Grafana).
"""

from __future__ import annotations

import os

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _enabled() -> bool:
    return os.environ.get("ENABLE_OTEL", "0").strip().lower() in ("1", "true", "yes")


def setup_otel(app) -> bool:
    """FastAPI app pe OTel auto-instrumentation lagao. True = laga, False = skip.

    Kabhi raise nahi karta — observability wiring app boot ko block na kare.
    """
    if not _enabled():
        logger.info("⏭️ OTel disabled (ENABLE_OTEL unset) — Sentry/Prometheus active")
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        try:
            from app.config import settings

            svc = getattr(settings, "app_name", "leadgen-app")
        except Exception:
            svc = "leadgen-app"

        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://tempo:4317")
        provider = TracerProvider(resource=Resource.create({SERVICE_NAME: svc}))
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
        )
        trace.set_tracer_provider(provider)

        # FastAPI request spans (health endpoints excluded from noise).
        FastAPIInstrumentor.instrument_app(
            app, excluded_urls="/health,/health/ready,/health/live,/metrics"
        )

        # Best-effort downstream instrumentation — har ek alag try (ek missing baaki na rok de).
        for mod, fn in (
            ("opentelemetry.instrumentation.sqlalchemy", "SQLAlchemyInstrumentor"),
            ("opentelemetry.instrumentation.redis", "RedisInstrumentor"),
            ("opentelemetry.instrumentation.httpx", "HTTPXClientInstrumentor"),
        ):
            try:
                m = __import__(mod, fromlist=[fn])
                getattr(m, fn)().instrument()
            except Exception as e:  # noqa: BLE001
                logger.debug(f"OTel {fn} skip: {e}")

        logger.info(f"✅ OpenTelemetry tracing ON -> {endpoint} (service={svc})")
        return True
    except ImportError:
        logger.warning(
            "ENABLE_OTEL=1 par opentelemetry packages missing — `pip install` karo. Skipping."
        )
        return False
    except Exception as e:  # noqa: BLE001
        logger.warning(f"OTel setup failed (non-fatal): {e}")
        return False
