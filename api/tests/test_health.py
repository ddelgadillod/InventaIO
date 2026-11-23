"""INV-34 (B17, CA 6) — /api/health dice qué versión y qué commit corren."""
import pytest
from fastapi.testclient import TestClient

from core.config import get_settings
from main import app


@pytest.fixture
def salud(monkeypatch):
    def pedir(commit: str) -> dict:
        monkeypatch.setattr(get_settings(), "INVENTAIO_COMMIT", commit)
        r = TestClient(app).get("/api/health")
        assert r.status_code == 200
        return r.json()
    return pedir


def test_sin_commit_queda_vacio(salud):
    cuerpo = salud("")
    assert cuerpo["version"] == app.version
    assert cuerpo["commit"] == ""


def test_con_commit_devuelve_7_caracteres(salud):
    assert salud("a1b2c3d4e5f60718293a4b5c6d7e8f9012345678")["commit"] == "a1b2c3d"
