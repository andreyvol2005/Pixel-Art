from sqlalchemy import CheckConstraint, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Pixel(Base):
    """Одна клетка холста.

    Первичный ключ составной (x, y): клетка адресуется координатами, поэтому
    отдельного id нет — он бы только раздувал таблицу на 160 000 строк.

    Клетки цвета по умолчанию в таблицу НЕ пишутся: их не с чем сравнивать,
    холст сам понимает, что отсутствующая строка означает DEFAULT_COLOR.
    """

    __tablename__ = "pixels"
    __table_args__ = (
        CheckConstraint("color ~ '^#[0-9a-f]{6}$'", name="pixels_color_hex"),
    )

    x: Mapped[int] = mapped_column(Integer, primary_key=True)
    y: Mapped[int] = mapped_column(Integer, primary_key=True)
    color: Mapped[str] = mapped_column(String(7), default="#ffffff")