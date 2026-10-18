import redis.asyncio as redis

from .config import REDIS_URL

redis_client: redis.Redis = redis.from_url(REDIS_URL, decode_responses=True)


async def close_redis() -> None:
    # redis-py 5 переименовал close() в aclose(); поддерживаем обе версии
    closer = getattr(redis_client, "aclose", None) or redis_client.close
    await closer()