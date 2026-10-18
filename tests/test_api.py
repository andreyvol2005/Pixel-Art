"""HTTP-слой: в первую очередь проверка прав на очистку холста.

Раньше это было GET /admin/wipe без единой проверки — ссылку мог повторить
любой посетитель и стереть весь рисунок.
"""
import pytest
from fastapi.testclient import TestClient

from app import api
from app.main import app

TOKEN = "test-secret-token"


@pytest.fixture
def client():
    # Lifespan не запускаем: он ходит в Postgres и Redis, которых в тестах нет.
    return TestClient(app)


@pytest.fixture
def wiped(monkeypatch):
    calls = []

    async def fake_clear():
        calls.append(1)
        return 42

    monkeypatch.setattr(api, "clear_canvas", fake_clear)
    return calls


class TestAdminWipe:
    def test_disabled_when_no_token_configured(self, client, wiped, monkeypatch):
        monkeypatch.setattr(api, "ADMIN_TOKEN", "")
        response = client.post("/api/admin/wipe")

        assert response.status_code == 503
        assert wiped == []

    def test_rejects_missing_token(self, client, wiped, monkeypatch):
        monkeypatch.setattr(api, "ADMIN_TOKEN", TOKEN)

        assert client.post("/api/admin/wipe").status_code == 401
        assert client.post("/api/admin/wipe", headers={"X-Admin-Token": ""}).status_code == 401
        assert client.post("/api/admin/wipe", headers={"X-Admin-Token": "wrong"}).status_code == 401
        assert wiped == []

    def test_allows_valid_token(self, client, wiped, monkeypatch):
        monkeypatch.setattr(api, "ADMIN_TOKEN", TOKEN)

        response = client.post("/api/admin/wipe", headers={"X-Admin-Token": TOKEN})

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "deleted": 42}
        assert wiped == [1]

    def test_old_public_get_endpoint_is_gone(self, client):
        """Старая ссылка /admin/wipe больше не чистит холст."""
        assert client.get("/admin/wipe").status_code == 404


class TestPublicApi:
    def test_config_is_served_for_the_client(self, client):
        """Клиент берёт размеры холста отсюда, а не держит свою копию."""
        data = client.get("/api/config").json()

        assert data["width"] > 0
        assert data["height"] > 0
        assert data["default_color"].startswith("#")
        assert data["protocol_version"] == 1

    def test_health(self, client):
        assert client.get("/api/health").json() == {"status": "ok"}