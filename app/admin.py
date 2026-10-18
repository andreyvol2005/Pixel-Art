"""Очистка холста — use-case, который трогает сразу три слоя.

Раньше он жил прямо в main.py и был доступен по ссылке /admin/wipe без всякой
проверки прав: любой посетитель мог стереть весь холст. Теперь:
  * по HTTP — только POST и только с заголовком X-Admin-Token;
  * из терминала — команда `wipe` в консоли приложения;
  * обе точки входа вызывают один и тот же use-case.
"""
import asyncio
import logging

from . import canvas
from .connection import manager
from .schemas import ClearEvent

logger = logging.getLogger(__name__)


async def clear_canvas() -> int:
    """Очищает холст в БД и в локальном кэше, затем уведомляет клиентов.

    Возвращает количество удалённых строк.
    """
    deleted = await canvas.delete_all_from_db()

    await canvas.init_canvas()          # перечитывает (уже пустую) базу
    await manager.broadcast(ClearEvent().model_dump())

    logger.info("Холст очищен, удалено строк: %d", deleted)
    return deleted


async def console_loop() -> None:
    """Слушает команды администратора в терминале.

    В проде это заменяется на админ-API с ролями, но для локальной разработки
    удобно иметь управление прямо в консоли.
    """
    loop = asyncio.get_running_loop()
    print("Админ-консоль: введите 'wipe' для очистки холста, 'quit' для выхода.")
    while True:
        try:
            command = (await loop.run_in_executor(None, input)).strip().lower()
        except (EOFError, KeyboardInterrupt):
            break

        if command == "quit":
            break
        if command == "wipe":
            try:
                await clear_canvas()
            except Exception:
                logger.exception("Не удалось очистить холст")
        elif command:
            print(f"Неизвестная команда: {command}")