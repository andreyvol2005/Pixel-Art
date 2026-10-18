"""HTTP-слой: только разбор запроса, коды ответов и вызов use-case'ов.

Здесь нет ни строчки бизнес-логики — ровно та же мысль, что в Messenger,
где роутеры только разбирают HTTP и зовут services.py.
"""
import hmac
import logging

from fastapi import APIRouter, Header, HTTPException, status

from . import realtime
from .admin import clear_canvas
from .config import ADMIN_TOKEN, CANVAS_H, CANVAS_W, DEFAULT_COLOR
from .connection import manager
from .schemas import PublicConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/config", response_model=PublicConfig)
async def public_config():
    """Размеры холста и цвет по умолчанию.

    Клиент раньше держал копию CANVAS_W/CANVAS_H у себя в app.js. Любая правка
    на сервере расходилась с клиентом молча — теперь константа одна.
    """
    return PublicConfig(width=CANVAS_W, height=CANVAS_H, default_color=DEFAULT_COLOR)


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/stats")
async def stats():
    """Диагностика: сколько воркеров видит сокетов и сколько всего онлайн."""
    try:
        online = await realtime.online_count()
    except Exception:
        logger.warning("Redis недоступен", exc_info=True)
        online = -1

    return {
        "online": online,
        "sockets_on_this_worker": await manager.count(),
    }


# ------------------------------------------------------------------ #
#                         Админские операции                          #
# ------------------------------------------------------------------ #

def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    """Проверяет токен администратора.

    Если ADMIN_TOKEN не задан в окружении, эндпоинт остаётся выключенным —
    это осознанно: «случайно включённая» очистка холста стоит дороже, чем
    лишний шаг настройки.
    """
    if not ADMIN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API выключен: задайте ADMIN_TOKEN в окружении",
        )

    # Сравнение постоянного времени — чтобы по задержке нельзя было подбирать токен
    if not x_admin_token or not hmac.compare_digest(x_admin_token, ADMIN_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный X-Admin-Token",
        )


@router.post("/admin/wipe", status_code=status.HTTP_200_OK)
async def wipe(x_admin_token: str | None = Header(default=None)):
    """Очищает холст. Требует заголовок X-Admin-Token.

    Раньше это было GET /admin/wipe без проверок — ссылку мог повторить кто угодно.
    """
    require_admin(x_admin_token)
    deleted = await clear_canvas()
    return {"status": "ok", "deleted": deleted}