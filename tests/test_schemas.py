"""Контракт между клиентом и сервером.

Эти тесты ловят то, что нельзя поймать на глаз: смену формата сообщений.
Раньше контракт ничем не был описан, поэтому «просто добавил поле» означало
тихую поломку старого клиента.
"""
import pytest
from pydantic import ValidationError

from app.schemas import (
    PROTOCOL_VERSION,
    OnlineEvent,
    PixelEvent,
    SetPixelCommand,
    SnapshotEvent,
)


class TestSetPixelCommand:
    def test_accepts_minimal_command(self):
        cmd = SetPixelCommand.model_validate({"x": 0, "y": 0, "color": "#ffffff"})
        assert cmd.v == PROTOCOL_VERSION
        assert cmd.type == "set_pixel"

    def test_normalizes_color_to_lowercase(self):
        cmd = SetPixelCommand.model_validate({"x": 1, "y": 2, "color": "#AABBCC"})
        assert cmd.color == "#aabbcc"

    @pytest.mark.parametrize("payload", [
        {"x": -1, "y": 0, "color": "#ffffff"},      # x вне холста
        {"x": 0, "y": 10**6, "color": "#ffffff"},   # y вне холста
        {"x": 0, "y": 0, "color": "white"},         # не hex
        {"x": 0, "y": 0, "color": "#fff"},          # короткий hex
        {"x": 0, "y": 0, "color": "#gggggg"},       # не hex-символы
        {"type": "drop_table", "x": 0, "y": 0, "color": "#ffffff"},
        {"x": 0, "y": 0},                           # нет цвета
    ])
    def test_rejects_garbage(self, payload):
        with pytest.raises(ValidationError):
            SetPixelCommand.model_validate(payload)


class TestEvents:
    def test_every_event_carries_version_and_type(self):
        for event in (PixelEvent(x=0, y=0, color="#ffffff"),
                      OnlineEvent(count=1),
                      SnapshotEvent(width=1, height=1)):
            assert event.v == PROTOCOL_VERSION
            assert event.type

    def test_snapshot_is_capped_by_canvas_size(self):
        huge = [[0, 0, "#ffffff"]] * 10**6
        with pytest.raises(ValidationError):
            SnapshotEvent(width=100, height=100, pixels=huge)

    def test_event_serializes_to_expected_json(self):
        data = PixelEvent(x=3, y=4, color="#ff0000").model_dump()
        assert data == {
            "v": PROTOCOL_VERSION, "type": "pixel",
            "x": 3, "y": 4, "color": "#ff0000",
        }