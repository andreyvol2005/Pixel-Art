"""Контракт между сервером и клиентом.

Раньше по сокету летел «голый массив» [x, y, color], а сервер различал четыре
несовместимых формы сообщения нюхансами (msg.action / msg.type / Array.isArray).
Добавить новое поле означало сломать старого клиента.

Теперь у каждого сообщения есть обязательные поля `v` (версия протокола) и `type`
(тип события), а форма задаётся схемой. Неизвестный тип отбрасывается на входе,
а не ломает разбор всего потока.
"""
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .config import CANVAS_H, CANVAS_W

# Версия протокола. Меняется только при несовместимых изменениях формата.
PROTOCOL_VERSION = 1
PROTOCOL_MIN_SUPPORTED = 1


def _check_version(v: int) -> int:
    if not (PROTOCOL_MIN_SUPPORTED <= v <= PROTOCOL_VERSION):
        raise ValueError(f"unsupported protocol version {v}")
    return v


# ------------------------------------------------------------------ #
#                       Клиент → сервер                              #
# ------------------------------------------------------------------ #

class SetPixelCommand(BaseModel):
    """Клиент поставил пиксель в (x, y)."""

    v: int = PROTOCOL_VERSION
    type: Literal["set_pixel"] = "set_pixel"
    x: int = Field(ge=0, lt=CANVAS_W)
    y: int = Field(ge=0, lt=CANVAS_H)
    color: str

    @field_validator("v")
    @classmethod
    def _check_v(cls, v: int) -> int:
        return _check_version(v)

    @field_validator("color")
    @classmethod
    def _check_color(cls, v: str) -> str:
        v = v.strip().lower()
        if len(v) != 7 or not v.startswith("#"):
            raise ValueError("color must be #rrggbb")
        if any(c not in "0123456789abcdef" for c in v[1:]):
            raise ValueError("color must be hex")
        return v


# ------------------------------------------------------------------ #
#                       Сервер → клиент                              #
# ------------------------------------------------------------------ #

class PixelEvent(BaseModel):
    """Один пиксель изменился."""

    v: int = PROTOCOL_VERSION
    type: Literal["pixel"] = "pixel"
    x: int
    y: int
    color: str


class SnapshotEvent(BaseModel):
    """Полное состояние холста — отправляется сразу при подключении."""

    v: int = PROTOCOL_VERSION
    type: Literal["snapshot"] = "snapshot"
    width: int
    height: int
    pixels: list[list] = Field(default_factory=list)

    @model_validator(mode="after")
    def _cap_size(self):
        # Защита от раздувания: при 400x400 полный холст — это 160 000 элементов.
        if len(self.pixels) > CANVAS_W * CANVAS_H:
            raise ValueError("snapshot is larger than the canvas")
        return self


class OnlineEvent(BaseModel):
    """Счётчик онлайн (общий для всех воркеров)."""

    v: int = PROTOCOL_VERSION
    type: Literal["online"] = "online"
    count: int


class ClearEvent(BaseModel):
    """Холст очищен администратором."""

    v: int = PROTOCOL_VERSION
    type: Literal["clear"] = "clear"


class ErrorEvent(BaseModel):
    """Сервер отклонил команду."""

    v: int = PROTOCOL_VERSION
    type: Literal["error"] = "error"
    detail: str


class PublicConfig(BaseModel):
    """Размеры и цвет по умолчанию — чтобы клиент не держал свою копию констант."""

    width: int
    height: int
    default_color: str
    protocol_version: int = PROTOCOL_VERSION