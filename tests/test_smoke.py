from backend.core.version import APP_VERSION
from backend.main import app
from fastapi.testclient import TestClient


def test_app_version():
    assert app.version == APP_VERSION
    assert APP_VERSION == "0.8.0"


def test_health_route_exists():
    """Included routers may not flatten into app.routes.path; assert via HTTP."""
    client = TestClient(app)
    res = client.get("/system/health")
    assert res.status_code == 200
    assert res.json().get("status") == "ok"
    # Root health/info JSON still present
    root = client.get("/")
    assert root.status_code == 200
