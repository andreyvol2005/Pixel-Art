import asyncio
import json
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import CANVAS_W, CANVAS_H, REDIS_CHANNEL
from .db import engine
from .models import Base
from .redis_client import redis_client
from .connection import manager
from . import canvas as canvas_module


# ------------------------------------------------------------------ #
#                          Lifespan                                  #
# ------------------------------------------------------------------ #

@asynccontextmanager
async def lifespan(app: FastAPI):
    # создаём таблицы
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # инициализация холста (Postgres + Redis + локальный кэш)
    await canvas_module.init_canvas()

    # фоновые задачи
    flush_task = asyncio.create_task(canvas_module.flush_to_db_periodically())
    pubsub_task = asyncio.create_task(_listen_redis())

    try:
        yield
    finally:
        flush_task.cancel()
        pubsub_task.cancel()
        # даём задачам корректно завершиться
        for t in (flush_task, pubsub_task):
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        await engine.dispose()
        await redis_client.close()


async def _listen_redis():
    """Слушает Redis-канал и рассылает события своим WebSocket-клиентам."""
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(REDIS_CHANNEL)
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                x, y, color = json.loads(message["data"])
            except Exception:
                continue
            await canvas_module.apply_remote_pixel(x, y, color)
            await manager.broadcast([x, y, color])
    finally:
        try:
            await pubsub.unsubscribe(REDIS_CHANNEL)
            await pubsub.close()
        except Exception:
            pass


# ------------------------------------------------------------------ #
#                          Приложение                                #
# ------------------------------------------------------------------ #

app = FastAPI(lifespan=lifespan)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    with open(os.path.join(STATIC_DIR, "index.html"), encoding="utf-8") as f:
        return f.read()


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        # 1) отправляем ТОЛЬКО не-белые пиксели
        pixels = canvas_module.get_non_default_pixels()
        await ws.send_json({"pixels": pixels})

        # 2) основной цикл — принимаем [x, y, color]
        while True:
            msg = await ws.receive_json()

            if not (isinstance(msg, list) and len(msg) == 3):
                continue

            x, y, color = msg
            try:
                x = int(x)
                y = int(y)
            except (TypeError, ValueError):
                continue
            color = str(color)

            if not (0 <= x < CANVAS_W and 0 <= y < CANVAS_H):
                continue
            if not (len(color) == 7 and color.startswith("#")):
                continue

            # обновляем локальный кэш
            await canvas_module.set_pixel(x, y, color)
            # публикуем в Redis — все воркеры (включая наш) получат событие
            # через _listen_redis и разошлют его своим клиентам
            await canvas_module.publish_pixel(x, y, color)

    except WebSocketDisconnect:
        await manager.disconnect(ws)
    except Exception as e:
        print("WS error:", e)
        await manager.disconnect(ws)