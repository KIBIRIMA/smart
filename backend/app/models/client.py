from sqlalchemy import String, Float
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin


class Client(Base, TimestampMixin):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    nom: Mapped[str] = mapped_column(String(180), nullable=False)
    adresse: Mapped[str] = mapped_column(String(255), default="")
    code_postal: Mapped[str] = mapped_column(String(10), default="")
    ville: Mapped[str] = mapped_column(String(120), default="")
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
