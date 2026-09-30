import asyncio
import json
from typing import Dict, Tuple, List

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .config import (
    CANVAS_W, CANVAS_H, DEFAULT_COLOR,
    REDIS_CANVAS_KEY, REDIS_CHANNEL,
    DB_FLUSH_INTERVAL,
)
from .db import SessionLocal
from .models import Pixel
from .redis_client import redis_client


# Локальный in-memory кэш каждого воркера.
# Ключ: (x, y)  →  значение: "#rrggbb"
_local_canvas: Dict[Tuple[int, int], str] = {}


# ------------------------------------------------------------------ #
#                          Работа с БД                                #
# ------------------------------------------------------------------ #

async def load_canvas_from_db() -> Dict[Tuple[int, int], str]:
    """Читает весь холст из Postgres."""
    async with SessionLocal() as s:
        result = await s.execute(select(Pixel.x, Pixel.y, Pixel.color))
        return {(row.x, row.y): row.color for row in result}


async def save_canvas_to_db(canvas: Dict[Tuple[int, int], str]) -> None:
    """Полная синхронизация с Postgres (upsert всех клеток)."""
    if not canvas:
        return
    values = [{"x": x, "y": y, "color": c} for (x, y), c in canvas.items()]
    async with SessionLocal() as s:
        stmt = pg_insert(Pixel).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["x", "y"],
            set_={"color": stmt.excluded.color},
        )
        await s.execute(stmt)
        await s.commit()


# ------------------------------------------------------------------ #
#                          Работа с Redis                            #
# ------------------------------------------------------------------ #

async def _write_canvas_to_redis(canvas: Dict[Tuple[int, int], str]) -> None:
    """Сохраняет в Redis ТОЛЬКО не-белые пиксели — компактный снапшот."""
    payload = [
        [x, y, c]
        for (x, y), c in canvas.items()
        if c != DEFAULT_COLOR
    ]
    await redis_client.set(REDIS_CANVAS_KEY, json.dumps(payload))


async def publish_pixel(x: int, y: int, color: str) -> None:
    """Публикует изменение пикселя в общий канал."""
    await redis_client.publish(REDIS_CHANNEL, json.dumps([x, y, color]))


# ------------------------------------------------------------------ #
#                      Инициализация и доступ                        #
# ------------------------------------------------------------------ #

async def init_canvas() -> None:
    """Инициализация при старте приложения."""
    # 1) строим полную карту — все клетки белые
    canvas: Dict[Tuple[int, int], str] = {
        (x, y): DEFAULT_COLOR
        for x in range(CANVAS_W)
        for y in range(CANVAS_H)
    }

    cached = await redis_client.get(REDIS_CANVAS_KEY)
    if cached:
        # 2) если Redis не пуст — накладываем не-белые пиксели поверх белого
        try:
            data = json.loads(cached)
            for x, y, c in data:
                canvas[(int(x), int(y))] = c
        except Exception as e:
            print("Redis cache corrupted, falling back to DB:", e)
            cached = None

    if not cached:
        # 3) если Redis пуст — тянем всё из БД
        db_canvas = await load_canvas_from_db()
        canvas.update(db_canvas)
        # гарантируем, что в БД лежат все клетки
        await save_canvas_to_db(canvas)

    # 4) обновляем снапшот в Redis (в нём только не-белые)
    await _write_canvas_to_redis(canvas)

    # 5) заполняем локальный кэш воркера
    _local_canvas.clear()
    _local_canvas.update(canvas)


def get_local_canvas() -> Dict[Tuple[int, int], str]:
    return _local_canvas


def get_non_default_pixels() -> List[List]:
    """Возвращает только клетки, чей цвет отличается от цвета по умолчанию."""
    return [
        [x, y, c]
        for (x, y), c in _local_canvas.items()
        if c != DEFAULT_COLOR
    ]


# ------------------------------------------------------------------ #
#                         Изменение пикселей                         #
# ------------------------------------------------------------------ #

async def set_pixel(x: int, y: int, color: str) -> None:
    """Обновляет пиксель локально и в Redis-снапшоте."""
    _local_canvas[(x, y)] = color
    await _write_canvas_to_redis(_local_canvas)


async def apply_remote_pixel(x: int, y: int, color: str) -> None:
    """Применяет пиксель, пришедший через pub/sub (от другого воркера)."""
    _local_canvas[(x, y)] = color


# ------------------------------------------------------------------ #
#                    Фоновая синхронизация с БД                      #
# ------------------------------------------------------------------ #

async def flush_to_db_periodically(interval: float = DB_FLUSH_INTERVAL) -> None:
    """Раз в N секунд сбрасывает локальный холст в Postgres."""
    while True:
        await asyncio.sleep(interval)
        try:
            await save_canvas_to_db(_local_canvas)
        except Exception as e:
            print("DB flush error:", e)