from backend.core.version import APP_VERSION
from backend.main import app


def test_app_version():
    assert app.version == APP_VERSION
    assert APP_VERSION == "0.8.0"


def test_health_route_exists():
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/" in paths
    assert "/system/health" in paths
