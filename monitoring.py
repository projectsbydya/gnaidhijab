"""
monitoring.py — Application monitoring and error tracking.

Initialises Sentry SDK when SENTRY_DSN is present in the environment.
No-op when the DSN is absent so local/CI environments are unaffected.

Environment variables:
    SENTRY_DSN                  Required to enable Sentry. Leave unset to disable.
    SENTRY_ENVIRONMENT          e.g. "production", "staging"  (default: "production")
    SENTRY_RELEASE              Optional release identifier (e.g. git SHA or tag).
    SENTRY_TRACES_SAMPLE_RATE   Float 0.0–1.0 for performance tracing  (default: 0.1)
    SENTRY_PROFILES_SAMPLE_RATE Float 0.0–1.0 for profiling             (default: 0.0)
    SENTRY_SEND_DEFAULT_PII     "true" to include user IP / email in events (default: false)
"""

import logging
import os

logger = logging.getLogger(__name__)


def init_monitoring(app) -> None:
    """
    Attach Sentry to the Flask application.
    Call this inside create_app() after all extensions and blueprints are registered.
    """
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        app.logger.info("[monitoring] SENTRY_DSN not set — error tracking disabled.")
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
    except ImportError:
        app.logger.warning(
            "[monitoring] sentry-sdk is not installed. "
            "Run: pip install sentry-sdk[flask]"
        )
        return

    environment = os.environ.get("SENTRY_ENVIRONMENT", "production").strip()
    release = os.environ.get("SENTRY_RELEASE", "").strip() or None

    traces_sample_rate = _parse_float(
        os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1"), default=0.1
    )
    profiles_sample_rate = _parse_float(
        os.environ.get("SENTRY_PROFILES_SAMPLE_RATE", "0.0"), default=0.0
    )
    send_default_pii = os.environ.get("SENTRY_SEND_DEFAULT_PII", "false").lower() == "true"

    # Forward Python logging WARNING+ to Sentry as breadcrumbs, ERROR+ as events.
    sentry_logging = LoggingIntegration(
        level=logging.WARNING,   # breadcrumbs
        event_level=logging.ERROR,  # captured as Sentry events
    )

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release,
        integrations=[
            FlaskIntegration(
                transaction_style="url",   # group by route pattern, not raw path
            ),
            SqlalchemyIntegration(),
            sentry_logging,
        ],
        traces_sample_rate=traces_sample_rate,
        profiles_sample_rate=profiles_sample_rate,
        send_default_pii=send_default_pii,
        # Silence noisy low-signal loggers from reaching Sentry
        ignore_errors=[
            KeyboardInterrupt,
        ],
    )

    app.logger.info(
        "[monitoring] Sentry initialised — env=%s traces=%.2f profiles=%.2f pii=%s",
        environment,
        traces_sample_rate,
        profiles_sample_rate,
        send_default_pii,
    )


def _parse_float(value: str, default: float) -> float:
    try:
        result = float(value)
        return max(0.0, min(1.0, result))  # clamp to [0.0, 1.0]
    except (ValueError, TypeError):
        return default
