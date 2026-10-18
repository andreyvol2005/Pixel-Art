"""WebSocket-слой: принимает соединение, валидирует команды по схеме, зовёт use-case'ы.

Отдельный модуль от HTTP — потому что у сокета другой протокол, другая обработка
ошибок и своя история жизни соединения. Раньше всё это лежало в main.py рядом с
логированием и админ-командами.
"""
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from . import canvas, realtime, visitors
from .config import CANVAS_H, CANVAS_W
from .connection import manager
from .schemas import ErrorEvent, PROTOCOL_VERSION, SetPixelCommand, SnapshotEvent

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_MESSAGE_BYTES = 4 * 1024


def client_ip(ws: WebSocket) -> str:
    """Реальный IP клиента с учётом обратного прокси (Nginx)."""
    forwarded = ws.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return ws.client.host if ws.client else "unknown"


async def send_snapshot(ws: WebSocket) -> None:
    """Отдаём новичку текущее состояние холста."""
    await ws.send_text(
        SnapshotEvent(
            width=CANVAS_W,
            height=CANVAS_H,
            pixels=canvas.get_non_default_pixels(),
        ).model_dump_json()
    )


async def handle_command(ws: WebSocket, raw: str) -> None:
    """Разбирает и выполняет одну команду клиента."""
    try:
        command = SetPixelCommand.model_validate_json(raw)
    except Exception as exc:
        await ws.send_text(
            ErrorEvent(detail=str(exc)[:200]).model_dump_json()
        )
        return

    await canvas.set_pixel(command.x, command.y, command.color)

    # Публикуем остальным воркерам. Своё событие вернётся из Redis обратно и
    # дойдёт до остальных клиентов этого же воркера через broadcast в
    # realtime.listen_forever — единственный путь рассылки, без дублей.
    await realtime.publish_pixel(command.x, command.y, command.color)


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await manager.connect(ws)

    ip = client_ip(ws)
    entered_at = visitors.log_visit(ip)

    presence_token = None
    try:
        try:
            presence_token = await realtime.register_connection()
        except Exception:
            # Redis недоступен — рисуем работать нельзя, но покажем локальный счётчик
            logger.warning("Redis недоступен: онлайн считаем локально", exc_info=True)

        await send_snapshot(ws)
        await manager.broadcast(
            {"v": PROTOCOL_VERSION, "type": "online", "count": await manager.count()}
        )

        while True:
            raw = await ws.receive_text()
            if len(raw) > MAX_MESSAGE_BYTES:
                await ws.send_text(
                    ErrorEvent(detail="Сообщение слишком большое").model_dump_json()
                )
                continue
            await handle_command(ws, raw)

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Ошибка WebSocket-соединения")
    finally:
        await manager.disconnect(ws)
        if presence_token:
            try:
                await realtime.unregister_connection(presence_token)
            except Exception:
                logger.warning("Не удалось снять присутствие", exc_info=True)
        try:
            await realtime.broadcast_online()
        except Exception:
            logger.warning("Не удалось разослать онлайн", exc_info=True)
        visitors.log_leave(ip, entered_at)