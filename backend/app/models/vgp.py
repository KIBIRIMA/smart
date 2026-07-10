"""Registre VGP — une ligne par machine physique (n° de parc).

Les VGP arrivent aujourd'hui en PDF envoyés par les inspecteurs à chaque
passage : ce modèle les centralise et permet le QR code par machine.
"""
from datetime import date
from sqlalchemy import String, Date
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin


class Vgp(Base, TimestampMixin):
    __tablename__ = "vgp"

    id: Mapped[int] = mapped_column(primary_key=True)
    parc: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    machine_modele: Mapped[str] = mapped_column(String(120), default="")
    date_vgp: Mapped[date | None] = mapped_column(Date, nullable=True)
    numero_serie: Mapped[str | None] = mapped_column(String(60), nullable=True)
    observations: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # chemins des documents uploadés (PDF)
    fichier_vgp: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fichier_notice: Mapped[str | None] = mapped_column(String(255), nullable=True)
