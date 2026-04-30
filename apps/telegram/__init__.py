"""Telegram and deployment entrypoints."""

try:
    from ._rootfile_enforcement import install_telegram_authorization

    install_telegram_authorization()
except Exception:
    # Telegram modules must stay importable even when optional bot deps are absent.
    pass
