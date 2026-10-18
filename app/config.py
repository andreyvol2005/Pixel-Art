# Единственное место, где живут настройки. Ничего не хардкодим в коде:
# всё читается из переменных окружения, локальные значения — только для отладки.
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# --- Холст ---
CANVAS_W = _env_int("CANVAS_W", 400)
CANVAS_H = _env_int("CANVAS_H", 400)
DEFAULT_COLOR = os.getenv("DEFAULT_COLOR", "#ffffff")

# --- Подключения ---
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://user:password@localhost:5433/pixelcanvas",
)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# --- Ключи Redis ---
# Единственная роль Redis — pub/sub для рассылки пикселей между воркерами.
# Состояние холста в Redis НЕ хранится: его единственный источник истины — Postgres.
# Так невозможно расхождение «кэш протух, база свежая».
REDIS_CHANNEL = os.getenv("REDIS_CHANNEL", "canvas:events")
# ZSET: member = id соединения, score = unix-время последнего касания.
# Нужен, чтобы счётчик онлайн был общим для всех воркеров, а не per-process.
REDIS_PRESENCE_KEY = os.getenv("REDIS_PRESENCE_KEY", "canvas:presence")
# Соединение, которое не подтверждалось дольше этого, считается мёртвым.
PRESENCE_TTL_SECONDS = _env_int("PRESENCE_TTL_SECONDS", 90)

# --- Интервалы ---
# Как часто «грязные» пиксели уезжают в базу. Меньше — меньше потеряем при падении,
# больше — меньше по��ы. 0.5 с — компромисс: одно обновление клетки ≈ 20 строк.
DB_FLUSH_INTERVAL = _env_float("DB_FLUSH_INTERVAL", 0.5)
DB_FLUSH_BATCH_SIZE = _env_int("DB_FLUSH_BATCH_SIZE", 5000)

# --- Админ ---
# Пустое значение = очистка холста по HTTP запрещена (см. app/api.py).
# Задайте ADMIN_TOKEN в окружении, чтобы включить эндпоинт.
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

# --- Логи посещений ---
VISITORS_LOG = Path(os.getenv("VISITORS_LOG", str(BASE_DIR / "data" / "visitors.log")))
VISITORS_LOG_MAX_LINES = _env_int("VISITORS_LOG_MAX_LINES", 2000)