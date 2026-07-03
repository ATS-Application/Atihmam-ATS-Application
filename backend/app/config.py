# backend/app/config.py
"""
Proxy module to avoid duplication between app/config.py and the app/config package.
All configurations are defined in app/config/settings.py.
"""
from app.config.settings import Settings, get_settings

__all__ = ["Settings", "get_settings"]