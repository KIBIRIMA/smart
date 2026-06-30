from sqlalchemy import String, Float
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin


class Machine(Base, TimestampMixin):
    """Catalogue machines — dimensions physiques réelles (clé du bin-packing 2D)."""
    __tablename__ = "machines"

    id: Mapped[int] = mapped_column(primary_key=True)
    modele: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    constructeur: Mapped[str] = mapped_column(String(80), default="")
    famille: Mapped[str] = mapped_column(String(60), default="")  # nacelle, télescopique...
    longueur_m: Mapped[float] = mapped_column(Float, nullable=False)
    largeur_m: Mapped[float] = mapped_column(Float, nullable=False)
    hauteur_m: Mapped[float] = mapped_column(Float, default=0.0)
    poids_kg: Mapped[float] = mapped_column(Float, nullable=False)
