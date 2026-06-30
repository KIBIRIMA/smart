from sqlalchemy import String, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin


class Chauffeur(Base, TimestampMixin):
    __tablename__ = "chauffeurs"

    id: Mapped[int] = mapped_column(primary_key=True)
    nom: Mapped[str] = mapped_column(String(120), nullable=False)
    telephone: Mapped[str] = mapped_column(String(30), default="")
    permis: Mapped[str] = mapped_column(String(40), default="CE")
    disponible: Mapped[bool] = mapped_column(Boolean, default=True)
    agence_id: Mapped[int | None] = mapped_column(ForeignKey("agences.id"), nullable=True)
