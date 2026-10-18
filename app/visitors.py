"""Журнал посещений.

Отдельный модуль, потому что это единственная аналитика в проекте, и она не
должна занимать треть main.py.

Осознанное ограничение: это файл, а не таблица. Как только понадобится считать
визиты по дням, по странам или по user-agent, файла не хватит — тогда см.
`visits(ip, entered_at, left_at, user_agent)` в таблице `visit_events`. Схема
зависит от колонки events в социальных сетях и в сервисах услуг.
"""
import logging
from collections import deque
from datetime import datetime
from pathlib import Path

from .config import VISITORS_LOG, VISITORS_LOG_MAX_LINES

logger = logging.getLogger(__name__)

TEMPLATE = "%Y-%m-%d %H:%M:%S"


def _ensure_dir() -> None:
    VISITORS_LOG.parent.mkdir(parents=True, exist_ok=True)


def _append(line: str) -> None:
    try:
        _ensure_dir()
        with open(VISITORS_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        # Журнал посещений не должен ронять приложение
        logger.warning("Не удалось записать в %s", VISITORS_LOG, exc_info=True)


def _rotate_if_needed() -> None:
    """Оставляет последние VISITORS_LOG_MAX_LINES строк.

    Читаем хвост, а не весь файл: при большом логе readlines() съедал память.
    """
    try:
        if not VISITORS_LOG.exists():
            return
        if sum(1 for _ in open(VISITORS_LOG, "r", encoding="utf-8")) <= VISITORS_LOG_MAX_LINES:
            return

        keep = deque(maxlen=VISITORS_LOG_MAX_LINES)
        with open(VISITORS_LOG, "r", encoding="utf-8") as f:
            for line in f:
                keep.append(line)

        tmp = VISITORS_LOG.with_suffix(".tmp")
        tmp.write_text("".join(keep), encoding="utf-8")
        tmp.replace(VISITORS_LOG)
    except OSError:
        logger.warning("Ротация журнала посещений не удалась", exc_info=True)


def log_visit(ip: str) -> datetime:
    """Записывает время входа. Возвращает это время."""
    entered_at = datetime.now()
    _append(f"{entered_at.strftime(TEMPLATE)} | ВХОД  | {ip}")
    return entered_at


def log_leave(ip: str, entered_at: datetime) -> None:
    """Записывает время выхода и длительность сессии."""
    left_at = datetime.now()
    duration = int((left_at - entered_at).total_seconds())
    _append(f"{left_at.strftime(TEMPLATE)} | ВЫХОД | {ip} | был {duration} сек")
    _rotate_if_needed()