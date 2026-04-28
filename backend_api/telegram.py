"""Rootfile adapter for Telegram bot endpoints."""

META = {
    "tier": "rootfile",
    "layer": "backend_api",
    "operator_type": "measurement_api",
}

try:
    from apps.telegram.telegram_bot_full import *  # noqa: F401,F403
except Exception:
    # Bot modules may require runtime credentials; import them directly in deployed contexts.
    pass

