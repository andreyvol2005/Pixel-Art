"""Состояние холста и выгрузка в БД.

Ключевое, что здесь проверяется, — регрессия, из-за которой после перезапуска
сервера воскресало старое изображение: снапшот в Redis читался раньше базы и
никогда не обновлялся. Теперь источник истины один — Postgres.
"""
import pytest
from sqlalchemy.dialects import postgresql

from app import canvas
from app.config import CANVAS_H, CANVAS_W, DEFAULT_COLOR


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeSession:
    """Записывает всё, что приложение отправило в базу."""

    def __init__(self, sink):
        self.sink = sink

    async def execute(self, stmt):
        self.sink.append(stmt)
        return FakeResult([])

    async def commit(self):
        pass


class FakeSessionFactory:
    def __init__(self, sink):
        self.sink = sink

    def __call__(self):
        return self

    async def __aenter__(self):
        return FakeSession(self.sink)

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def db_sink(monkeypatch):
    sink = []
    monkeypatch.setattr(canvas, "SessionLocal", FakeSessionFactory(sink))
    return sink


@pytest.fixture(autouse=True)
def clean_canvas():
    canvas._local_canvas.clear()
    canvas._dirty.clear()
    yield
    canvas._local_canvas.clear()
    canvas._dirty.clear()


def rows_from(sink):
    """Достаёт (x, y, color) из сгенерированных upsert-ов.

    Компилируем под диалект Postgres, иначе параметры мульти-values вставки
    не собираются в читаемый вид.
    """
    result = []
    for stmt in sink:
        params = stmt.compile(dialect=postgresql.dialect()).params
        for i in range(len(params) // 3):
            result.append((
                params[f"x_m{i}"],
                params[f"y_m{i}"],
                params[f"color_m{i}"],
            ))
    return result


class TestDirtyTracking:
    async def test_new_pixel_is_marked_dirty(self):
        await canvas.set_pixel(1, 2, "#ff0000")
        assert canvas._dirty == {(1, 2)}

    async def test_repeated_same_color_is_not_dirty_again(self):
        await canvas.set_pixel(1, 2, "#ff0000")
        await canvas.set_pixel(1, 2, "#ff0000")
        assert canvas._dirty == {(1, 2)}

    async def test_flush_writes_only_changed_pixels(self, db_sink):
        for x in range(50):
            await canvas.set_pixel(x, 0, "#00ff00")

        written = await canvas.flush_dirty_to_db()

        assert written == 50
        assert len(rows_from(db_sink)) == 50

    async def test_second_flush_writes_nothing(self, db_sink):
        await canvas.set_pixel(5, 5, "#00ff00")
        await canvas.flush_dirty_to_db()
        db_sink.clear()

        assert await canvas.flush_dirty_to_db() == 0
        assert db_sink == []

    async def test_remote_pixel_is_not_written_by_receiver(self):
        """Пиксель пришёл по pub/sub — автор уже сохранит его у себя."""
        await canvas.apply_remote_pixel(9, 9, "#123456")
        assert canvas._local_canvas[(9, 9)] == "#123456"
        assert canvas._dirty == set()


class TestInit:
    async def test_loads_state_from_db_not_from_cache(self, monkeypatch):
        async def fake_load():
            return {(3, 4): "#abcdef"}

        monkeypatch.setattr(canvas, "load_canvas_from_db", fake_load)

        await canvas.init_canvas()

        assert canvas._local_canvas[(3, 4)] == "#abcdef"
        assert canvas._dirty == set()

    async def test_db_failure_does_not_prevent_startup(self, monkeypatch):
        async def broken():
            raise RuntimeError("postgres недоступен")

        monkeypatch.setattr(canvas, "load_canvas_from_db", broken)

        await canvas.init_canvas()   # не должно бросить

        assert len(canvas._local_canvas) == CANVAS_W * CANVAS_H
        assert canvas._local_canvas[(0, 0)] == DEFAULT_COLOR


class TestSnapshot:
    async def test_snapshot_contains_only_non_default_cells(self):
        for x in range(5):
            await canvas.set_pixel(x, 0, "#00ff00")

        pixels = canvas.get_non_default_pixels()

        assert len(pixels) == 5
        assert all(c != DEFAULT_COLOR for _, _, c in pixels)
        assert max(len(p) for p in pixels) == 3
        assert CANVAS_W > 0 and CANVAS_H > 0