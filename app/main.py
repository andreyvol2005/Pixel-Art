"""Точка сборки приложения.

Здесь и только здесь: создание FastAPI, middleware, подключение роутеров,
жизненный цикл (lifespan) и раздача статики. Бизнес-логики ноль.

Было 163 строки, в которых смешались логирование, админ-CLI, pub/sub, HTTP и
WebSocket. Стало ~60 строк, где видно структуру приложения с одного экрана.
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import admin, api, canvas, realtime, ws
from .config import BASE_DIR, CANVAS_H, CANVAS_W
from .db import create_schema, engine
from .redis_client import close_redis

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

STATIC_DIR = BASE_DIR / "static"


def _watch_task(task: asyncio.Task, name: str) -> None:
    """Фоновая задача упала — это не должно проходить молча."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error("Фоновая задача %s упала: %r", name, exc)


async def _run_task(coro, name: str) -> asyncio.Task:
    task = asyncio.create_task(coro, name=name)
    task.add_done_callback(lambda t: _watch_task(t, name))
    return task


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_schema()
    await canvas.init_canvas()

    tasks = [
        await _run_task(canvas.flush_loop(), "db-flush"),
        await _run_task(realtime.listen_forever(), "redis-pubsub"),
        await _run_task(admin.console_loop(), "admin-console"),
    ]

    logger.info(
        "Pixel-Art запущен: холст %dx%d, статика %s",
        CANVAS_W, CANVAS_H, STATIC_DIR,
    )

    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

        # Последний сброс в БД — иначе потеряем всё, что не успели записать
        await canvas.flush_and_stop()
        await engine.dispose()
        await close_redis()
        logger.info("Pixel-Art остановлен")


app = FastAPI(title="Pixel-Art Online", lifespan=lifespan)

# Статика монтируется последней, чтобы /api и /ws не перехватывались ею
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(api.router)
app.include_router(ws.router)


@app.get("/", include_in_schema=False)
async def index():
    """Отдаём index.html файлом, а не читая его руками в обработчике."""
    return FileResponse(STATIC_DIR / "index.html")