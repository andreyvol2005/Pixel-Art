"""Рассылка событий между воркерами через Redis pub/sub и учёт онлайна.

Почему отдельный модуль:
  * pub/sub нужен в двух местах (сокет-обработчик слушает, обработчик публикует),
    а раньше это было вшито в main.py;
  * счётчик онлайна обязан быть общим для всех воркеров. Раньше он жил в
    ConnectionManager, то есть считался в пределах одного процесса: при
    `uvicorn --workers 4` каждый воркер показывал свою цифру.
"""
import logging
import time
import uuid

from . import canvas
from .config import (
    PRESENCE_TTL_SECONDS,
    REDIS_CHANNEL,
    REDIS_PRESENCE_KEY,
)
from .connection import manager
from .redis_client import redis_client
from .schemas import OnlineEvent, PixelEvent

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
#                      Рассылка пикселей                             #
# ------------------------------------------------------------------ #

async def publish_pixel(x: int, y: int, color: str) -> None:
    """Отправляет пиксель остальным воркерам."""
    payload = PixelEvent(x=x, y=y, color=color).model_dump_json()
    await redis_client.publish(REDIS_CHANNEL, payload)


async def listen_forever() -> None:
    """Слушает Redis-канал и применяет чужие пиксели к локальному кэшу.

    Свои события Redis тоже присылает обратно. Это дёшево (идемпotentная запись
    в кэш, dirty-сет при этом не трогается) и заодно гарантирует, что все
    воркеры придут к одному состоянию.
    """
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(REDIS_CHANNEL)
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                event = PixelEvent.model_validate_json(message["data"])
            except Exception:
                # Мусор в канале не должен ронять слушателя
                logger.warning("Не удалось разобрать событие Redis: %r", message["data"])
                continue

            await canvas.apply_remote_pixel(event.x, event.y, event.color)
            await manager.broadcast(event.model_dump())
    finally:
        try:
            await pubsub.unsubscribe(REDIS_CHANNEL)
            await pubsub.close()
        except Exception:
            logger.debug("Не удалось закрыть pubsub", exc_info=True)


# ------------------------------------------------------------------ #
#                          Онлайн-счётчик                            #
# ------------------------------------------------------------------ #

async def _prune_dead() -> None:
    """Убирает соединения, которые не подтверждали жизнь дольше TTL.

    Если воркер упал вместе с сокетами, его участники навсегда остались бы в
    ZSET и счётчик завышался бы.
    """
    deadline = time.time() - PRESENCE_TTL_SECONDS
    await redis_client.zremrangebyscore(REDIS_PRESENCE_KEY, "-inf", deadline)


async def register_connection() -> str:
    """Регистрирует соединение, возвращает его токен для последующего снятия."""
    token = uuid.uuid4().hex
    await redis_client.zadd(REDIS_PRESENCE_KEY, {token: time.time()})
    await _prune_dead()
    return token


async def unregister_connection(token: str) -> None:
    """Снимает соединение с учёта."""
    await redis_client.zrem(REDIS_PRESENCE_KEY, token)


async def online_count() -> int:
    """Онлайн без изменений — используется в /api/stats."""
    await _prune_dead()
    return int(await redis_client.zcard(REDIS_PRESENCE_KEY))


# ------------------------------------------------------------------ #
#                          Онлайн-событие                            #
# ------------------------------------------------------------------ #

async def broadcast_online() -> None:
    """Рассылает всем счётчик онлайн (локальным клиентам этого воркера)."""
    try:
        count = await online_count()
    except Exception:
        logger.warning("Redis недоступен — показываем локальный онлайн", exc_info=True)
        count = await manager.count()
    await manager.broadcast(OnlineEvent(count=count).model_dump())


__all__ = [
    "publish_pixel",
    "listen_forever",
    "register_connection",
    "unregister_connection",
    "online_count",
    "broadcast_online",
]