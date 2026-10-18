"""WebSocket: полный путь команды — разбор, применение, рассылка.

Здесь же проверяется, что клиент с устаревшей версией протокола не ломает
сервер: раньше любое непонятное сообщение роняло весь поток.
"""
import json

import pytest
from fastapi.testclient import TestClient

from app import ws
from app.main import app
from app.schemas import PROTOCOL_MIN_SUPPORTED, PROTOCOL_VERSION


@pytest.fixture
def ws_env(monkeypatch, tmp_path):
    published = []
    applied = []
    online_calls = []

    async def register():
        return "token-1"

    async def unregister(token):
        online_calls.append(token)

    async def broadcast_online():
        pass

    async def publish(x, y, color):
        published.append((x, y, color))

    async def set_pixel(x, y, color):
        applied.append((x, y, color))

    monkeypatch.setattr(ws.realtime, "register_connection", register)
    monkeypatch.setattr(ws.realtime, "unregister_connection", unregister)
    monkeypatch.setattr(ws.realtime, "broadcast_online", broadcast_online)
    monkeypatch.setattr(ws.realtime, "publish_pixel", publish)
    monkeypatch.setattr(ws.canvas, "set_pixel", set_pixel)
    monkeypatch.setattr(ws.visitors, "VISITORS_LOG", tmp_path / "visitors.log")
    monkeypatch.setattr(ws.visitors, "VISITORS_LOG_MAX_LINES", 100)

    return {"published": published, "applied": applied, "online": online_calls}


class TestWebSocket:
    def test_sends_snapshot_on_connect(self, ws_env):
        client = TestClient(app)
        with client.websocket_connect("/ws") as socket:
            first = json.loads(socket.receive_text())

            assert first["type"] == "snapshot"
            assert first["v"] == PROTOCOL_VERSION
            assert first["width"] > 0

    def test_announces_online_on_connect(self, ws_env):
        client = TestClient(app)
        with client.websocket_connect("/ws") as socket:
            socket.receive_text()   # snapshot
            event = json.loads(socket.receive_text())

            assert event["type"] == "online"
            assert isinstance(event["count"], int)

    def test_valid_command_reaches_domain(self, ws_env):
        client = TestClient(app)
        with client.websocket_connect("/ws") as socket:
            socket.receive_text()   # snapshot
            socket.receive_text()   # online
            socket.send_text(json.dumps({
                "v": PROTOCOL_VERSION, "type": "set_pixel",
                "x": 12, "y": 34, "color": "#ff8800",
            }))

        assert ws_env["applied"] == [(12, 34, "#ff8800")]
        assert ws_env["published"] == [(12, 34, "#ff8800")]
        assert ws_env["online"] == ["token-1"]

    def test_malformed_command_is_reported_not_fatal(self, ws_env):
        """Клиент послал мусор — соединение должно остаться живым."""
        client = TestClient(app)
        with client.websocket_connect("/ws") as socket:
            socket.receive_text()
            socket.receive_text()
            socket.send_text("не json вовсе")

            error = json.loads(socket.receive_text())
            assert error["type"] == "error"

            # Сокет всё ещё работает: принимаем корректную команду
            socket.send_text(json.dumps({
                "v": PROTOCOL_VERSION, "type": "set_pixel",
                "x": 1, "y": 1, "color": "#000000",
            }))

        assert ws_env["applied"] == [(1, 1, "#000000")]

    def test_oversized_message_is_rejected(self, ws_env):
        client = TestClient(app)
        with client.websocket_connect("/ws") as socket:
            socket.receive_text()
            socket.receive_text()
            socket.send_text(json.dumps({"color": "x" * 10_000}))

            error = json.loads(socket.receive_text())
            assert error["type"] == "error"

        assert ws_env["applied"] == []

    def test_unsupported_protocol_version_is_rejected(self, ws_env):
        client = TestClient(app)
        with client.websocket_connect("/ws") as socket:
            socket.receive_text()
            socket.receive_text()
            socket.send_text(json.dumps({
                "v": PROTOCOL_VERSION + 1, "type": "set_pixel",
                "x": 1, "y": 1, "color": "#000000",
            }))

            error = json.loads(socket.receive_text())
            assert error["type"] == "error"

        assert ws_env["applied"] == []


def test_protocol_version_is_sane():
    assert PROTOCOL_MIN_SUPPORTED <= PROTOCOL_VERSION