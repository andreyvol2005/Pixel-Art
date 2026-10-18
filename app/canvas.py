"""Application-слой: состояние холста и его сохранение.

Инфраструктура (Postgres, Redis) вызывается отсюда напрямую намеренно: на этом
размере проекта репозитории были бы лишней обвязкой. Но логика хранения —
целиком здесь, и она единственная в проекте.

Источник истины — Postgres. Локальный кэш — это «горячий» буфер чтения для
отрисовки, а не база. Раньше третьим источником был снапшот в Redis, и он
никогда не обновлялся после старта: `init_canvas` читал его первым, поэтому после
перезапуска приложение воскрешало состояние, отставшее на всё время работы.
Снапшота в Redis больше нет — Redis занимается только pub/sub.
"""
import asyncio
import logging
from typing import Dict, List, Set, Tuple

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .config import (
    DB_FLUSH_BATCH_SIZE,
    DB_FLUSH_INTERVAL,
    CANVAS_H,
    CANVAS_W,
    DEFAULT_COLOR,
)
from .db import SessionLocal
from .models import Pixel

logger = logging.getLogger(__name__)

# Локальный in-memory кэш каждого воркера.
# Ключ: (x, y) → значение: "#rrggbb"
_local_canvas: Dict[Tuple[int, int], str] = {}

# Пиксели, изменённые с прошлого сброса в базу. Именно дельта, а не весь холст:
# раньше каждый воркер раз в 2 секунды делал upsert ВСЕХ небелых клеток, и при
# двух воркерах они затирали друг друга по кругу (last-write-wins на всю таблицу).
_dirty: Set[Tuple[int, int]] = set()

# Асинхронный лок нужен, потому что set_pixel вызывается из обработчика сокета.
_dirty_lock = asyncio.Lock()


# ------------------------------------------------------------------ #
#                          Работа с БД                                #
# ------------------------------------------------------------------ #

async def load_canvas_from_db() -> Dict[Tuple[int, int], str]:
    """Читает все не-белые клетки из Postgres."""
    async with SessionLocal() as s:
        result = await s.execute(select(Pixel.x, Pixel.y, Pixel.color))
        return {(row.x, row.y): row.color for row in result}


async def save_pixels_to_db(pixels: List[Tuple[int, int, str]]) -> int:
    """Пишет переданные пиксели пачками. Возвращает количество записей."""
    if not pixels:
        return 0

    written = 0
    async with SessionLocal() as s:
        for i in range(0, len(pixels), DB_FLUSH_BATCH_SIZE):
            batch = pixels[i:i + DB_FLUSH_BATCH_SIZE]
            stmt = pg_insert(Pixel).values(
                [{"x": x, "y": y, "color": c} for x, y, c in batch]
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["x", "y"],
                set_={"color": stmt.excluded.color},
            )
            await s.execute(stmt)
            written += len(batch)
        await s.commit()
    return written


async def delete_all_from_db() -> int:
    async with SessionLocal() as s:
        result = await s.execute(Pixel.__table__.delete())
        await s.commit()
        return result.rowcount or 0


# ------------------------------------------------------------------ #
#                       Инициализация и доступ                        #
# ------------------------------------------------------------------ #

def _empty_canvas() -> Dict[Tuple[int, int], str]:
    return {(x, y): DEFAULT_COLOR for x in range(CANVAS_W) for y in range(CANVAS_H)}


async def init_canvas() -> None:
    """Инициализация холста при старте приложения. База — единственный источник."""
    canvas = _empty_canvas()
    try:
        db_canvas = await load_canvas_from_db()
    except Exception:
        # Не падаем: без базы приложение всё равно должно подняться и показать
        # пустой холст, а не упасть на старте.
        logger.exception("Не удалось загрузить холст из БД — стартуем пустым")
        db_canvas = {}

    canvas.update(db_canvas)

    _local_canvas.clear()
    _local_canvas.update(canvas)
    async with _dirty_lock:
        _dirty.clear()

    logger.info(
        "[init] canvas ready %dx%d, небелых клеток из БД: %d",
        CANVAS_W, CANVAS_H, len(db_canvas),
    )


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
    """Пиксель поставлен локальным клиентом: обновляем кэш и помечаем в базу."""
    coord = (x, y)
    if _local_canvas.get(coord) == color:
        return
    _local_canvas[coord] = color
    async with _dirty_lock:
        _dirty.add(coord)


async def apply_remote_pixel(x: int, y: int, color: str) -> None:
    """Пиксель пришёл через pub/sub от другого воркера.

    В базу его писать не нужно: автор изменения уже пометил его у себя в _dirty.
    """
    _local_canvas[(x, y)] = color


# ------------------------------------------------------------------ #
#                    Фоновая синхронизация                           #
# ------------------------------------------------------------------ #

async def flush_dirty_to_db() -> int:
    """Выгружает в базу только те клетки, что изменились с прошлого раза."""
    # Список и значения снимаем ПОД локом. Иначе set_pixel успевает дописать в
    # _local_canvas после того, как _dirty очищен, — и это изменение потеряется
    # до следующего события по этой клетке.
    async with _dirty_lock:
        if not _dirty:
            return 0
        pixels = [(x, y, _local_canvas[(x, y)]) for x, y in _dirty]
        _dirty.clear()

    return await save_pixels_to_db(pixels)


async def flush_loop(interval: float = DB_FLUSH_INTERVAL) -> None:
    """Фоновая задача: периодически сбрасывает дельту в базу."""
    while True:
        await asyncio.sleep(interval)
        try:
            await flush_dirty_to_db()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Ошибка выгрузки пикселей в БД")


async def flush_and_stop() -> None:
    """Последний сброс перед остановкой, чтобы не потерять хвост изменений."""
    try:
        written = await flush_dirty_to_db()
        if written:
            logger.info("Финальный сброс: %d пикселей", written)
    except Exception:
        logger.exception("Финальный сброс не удался")