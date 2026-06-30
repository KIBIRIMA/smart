from sqlalchemy import String, Float
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin


class Agence(Base, TimestampMixin):
    __tablename__ = "agences"

    id: Mapped[int] = mapped_column(primary_key=True)
    nom: Mapped[str] = mapped_column(String(120), nullable=False)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    adresse: Mapped[str] = mapped_column(String(255), default="")
    lat: Mapped[float] = mapped_column(Float, nullable=False)   # dépôt
    lng: Mapped[float] = mapped_column(Float, nullable=False)
