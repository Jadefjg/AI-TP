"""Shared platform defaults for local/dev execution targets."""

DEFAULT_BASE_URL = "http://127.0.0.1:8002"
DEFAULT_HEALTH_URL = f"{DEFAULT_BASE_URL}/system/health"
# Frontend Vite often binds 5174 in this repo's npm scripts; override via ui_script.base_url.
DEFAULT_UI_BASE_URL = "http://127.0.0.1:5174"
