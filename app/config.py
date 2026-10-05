# --- Холст ---
CANVAS_W = 400
CANVAS_H = 400
DEFAULT_COLOR = "#ffffff"

# --- Подключения ---
DATABASE_URL = "postgresql+asyncpg://user:password@localhost:5433/pixelcanvas"
REDIS_URL = "redis://localhost:6379"

# --- Ключи Redis ---
REDIS_CHANNEL = "canvas:events"
REDIS_CANVAS_KEY = "canvas:state"

# --- Интервалы ---
DB_FLUSH_INTERVAL = 2.0