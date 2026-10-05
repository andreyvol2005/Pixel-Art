import redis.asyncio as redis
from .config import REDIS_URL

redis_client: redis.Redis = redis.from_url(REDIS_URL, decode_responses=True)