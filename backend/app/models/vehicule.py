from sqlalchemy import String, Float, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin


class Vehicule(Base, TimestampMixin):
    """Camion plateau — capacité du plateau pour le chargement 2D."""
    __tablename__ = "vehicules"

    id: Mapped[int] = mapped_column(primary_key=True)
    immatriculation: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    libelle: Mapped[str] = mapped_column(String(120), default="")
    plateau_longueur_m: Mapped[float] = mapped_column(Float, default=13.6)
    plateau_largeur_m: Mapped[float] = mapped_column(Float, default=2.48)
    charge_utile_kg: Mapped[float] = mapped_column(Float, default=26000)
    conso_l_100km: Mapped[float] = mapped_column(Float, default=32.0)
    disponible: Mapped[bool] = mapped_column(Boolean, default=True)
    agence_id: Mapped[int | None] = mapped_column(ForeignKey("agences.id"), nullable=True)
