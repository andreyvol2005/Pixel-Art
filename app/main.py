import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime

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


# ------------------------------------------------------------------ #
#                    Логирование посещений                           #
# ------------------------------------------------------------------ #

LOG_FILE = "/root/Pixel-Art/visitors.log"


def log_visit(ip: str) -> datetime:
    """Записывает время входа. Возвращает это время."""
    timestamp = datetime.now()
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{timestamp.strftime('%Y-%m-%d %H:%M:%S')} | ВХОД  | {ip}\n")

    # Ротация: не больше 2000 строк
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > 2000:
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                f.writelines(lines[-2000:])
    except Exception:
        pass

    return timestamp


def log_leave(ip: str, entered_at: datetime):
    """Записывает время выхода и длительность сессии."""
    left_at = datetime.now()
    duration = int((left_at - entered_at).total_seconds())

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(
            f"{left_at.strftime('%Y-%m-%d %H:%M:%S')} | ВЫХОД | {ip} | "
            f"был {duration} сек\n"
        )


# ------------------------------------------------------------------ #
#                    Очистка холста                                  #
# ------------------------------------------------------------------ #

async def clear_canvas():
    """Очищает холст в БД, Redis и локальном кэше"""
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM pixels"))

    await canvas_module.clear_redis_snapshot()
    await canvas_module.clear_cache()
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


# ------------------------------------------------------------------ #
#                    Запуск и остановка                              #
# ------------------------------------------------------------------ #

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await canvas_module.init_canvas()
    asyncio.create_task(admin_listener())

    flush_task = asyncio.create_task(canvas_module.flush_to_db_periodically())
    pubsub_task = asyncio.create_task(_listen_redis())

    try:
        yield
    finally:
        flush_task.cancel()
        pubsub_task.cancel()
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

    # Реальный IP за Nginx
    client_ip = ws.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if not client_ip:
        client_ip = ws.client.host if ws.client else "unknown"

    entered_at = log_visit(client_ip)

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
        await manager.broadcast({"type": "online", "count": count})
        log_leave(client_ip, entered_at)