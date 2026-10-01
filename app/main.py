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
from sqlalchemy import text


async def clear_canvas():
    """Очищает холст в БД, Redis и локальном кэше"""
    # 1. Очищаем БД
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM pixels"))

    # 2. Очищаем Redis-снапшот
    await canvas_module.clear_redis_snapshot()

    # 3. Очищаем локальный кэш
    canvas_module.clear_cache()

    # 4. Рассылаем команду очистки всем клиентам
    await manager.broadcast({"action": "clear"})

    print("🧹 Холст очищен (БД, Redis, кэш)")


async def admin_listener():
    """Слушает команды админа в терминале"""
    loop = asyncio.get_running_loop()
    while True:
        try:
            command = await loop.run_in_executor(None, input)
            if command.strip().lower() == "wipe":
                await clear_canvas()
        except (EOFError, KeyboardInterrupt):
            break
        except Exception as e:
            print(f"Ошибка: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # создаём таблицы
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # инициализация холста (Postgres + Redis + локальный кэш)
    await canvas_module.init_canvas()

    # запускаем слушатель команд админа
    asyncio.create_task(admin_listener())

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
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode('utf-8', errors='ignore')
                x, y, color = json.loads(data)
            except Exception as e:
                print(f"Redis decode error: {e}")
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


@app.get("/admin/wipe")
async def admin_wipe():
    """Секретная ссылка для очистки холста"""
    await clear_canvas()
    return {"status": "ok", "message": "Холст очищен"}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    count = await manager.connect(ws)
    try:
        # 1) отправляем новому клиенту текущее состояние холста
        pixels = canvas_module.get_non_default_pixels()
        await ws.send_json({"pixels": pixels})

        # 2) сообщаем ВСЕМ новое количество онлайн
        await manager.broadcast({"type": "online", "count": count})

        # 3) основной цикл — принимаем [x, y, color]
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

            await canvas_module.set_pixel(x, y, color)
            await canvas_module.publish_pixel(x, y, color)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print("WS error:", e)
    finally:
        count = await manager.disconnect(ws)
        # сообщаем ВСЕМ новое количество онлайн
        await manager.broadcast({"type": "online", "count": count})