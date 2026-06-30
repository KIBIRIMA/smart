from datetime import date
from sqlalchemy import String, Float, Integer, Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin


class Mission(Base, TimestampMixin):
    __tablename__ = "missions"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), nullable=True)
    client_nom: Mapped[str] = mapped_column(String(180), default="")
    adresse: Mapped[str] = mapped_column(String(255), default="")
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    type_op: Mapped[str] = mapped_column(String(20), default="livraison")  # livraison | recuperation
    machine_id: Mapped[int | None] = mapped_column(ForeignKey("machines.id"), nullable=True)
    machine_modele: Mapped[str] = mapped_column(String(120), default="")
    quantite: Mapped[int] = mapped_column(Integer, default=1)
    statut: Mapped[str] = mapped_column(String(20), default="A_PLANIFIER")
    date_prevue: Mapped[date | None] = mapped_column(Date, nullable=True)
    tournee_id: Mapped[int | None] = mapped_column(ForeignKey("tournees.id"), nullable=True)
