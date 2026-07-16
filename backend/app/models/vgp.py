"""Registre VGP — machine (dernier état) + historique complet des rapports.

La table `vgp` garde une ligne par machine (n° de parc) avec le DERNIER état
connu (cache d'affichage). La table `vgp_rapports` garde la trace de TOUTES
les vérifications successives : traçabilité réglementaire (registre de
sécurité) et historique consultable au scan du QR code.

Le QR code par machine est UNIQUE et permanent : il pointe vers la fiche
machine, dont le contenu s'enrichit à chaque nouveau rapport déposé.
"""
from datetime import date
from sqlalchemy import String, Date
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin


class Vgp(Base, TimestampMixin):
    __tablename__ = "vgp"

    id: Mapped[int] = mapped_column(primary_key=True)
    parc: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    machine_modele: Mapped[str | None] = mapped_column(String(120), nullable=True, default="")
    date_vgp: Mapped[date | None] = mapped_column(Date, nullable=True)
    numero_serie: Mapped[str | None] = mapped_column(String(60), nullable=True)
    observations: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    anomalie: Mapped[str | None] = mapped_column(String(5), nullable=True)  # OUI / NON
    # chemins des documents (PDF)
    fichier_vgp: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fichier_notice: Mapped[str | None] = mapped_column(String(255), nullable=True)


class VgpRapport(Base, TimestampMixin):
    """Un enregistrement par contrôle VGP — l'historique complet."""
    __tablename__ = "vgp_rapports"

    id: Mapped[int] = mapped_column(primary_key=True)
    parc: Mapped[str] = mapped_column(String(30), index=True)
    date_vgp: Mapped[date | None] = mapped_column(Date, nullable=True)
    numero_serie: Mapped[str | None] = mapped_column(String(60), nullable=True)
    observations: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    anomalie: Mapped[str | None] = mapped_column(String(5), nullable=True)  # OUI / NON
    fichier: Mapped[str | None] = mapped_column(String(255), nullable=True)
