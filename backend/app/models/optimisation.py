from datetime import date
from sqlalchemy import String, Float, Integer, Date, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin


class Optimisation(Base, TimestampMixin):
    """Run d'optimisation — archive + comparaison avant/après."""
    __tablename__ = "optimisations"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    date_tournee: Mapped[date | None] = mapped_column(Date, nullable=True)
    agence_id: Mapped[int | None] = mapped_column(ForeignKey("agences.id"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    user_nom: Mapped[str] = mapped_column(String(120), default="")
    moteur: Mapped[str] = mapped_column(String(10), default="v12")
    statut: Mapped[str] = mapped_column(String(20), default="EN_COURS")  # EN_COURS|TERMINEE|ERREUR

    nb_missions: Mapped[int] = mapped_column(Integer, default=0)
    nb_tournees: Mapped[int] = mapped_column(Integer, default=0)
    km_total: Mapped[float] = mapped_column(Float, default=0.0)
    taux_moyen: Mapped[float] = mapped_column(Float, default=0.0)
    cout_estime: Mapped[float] = mapped_column(Float, default=0.0)
    co2_kg: Mapped[float] = mapped_column(Float, default=0.0)
    duree_calcul_s: Mapped[float] = mapped_column(Float, default=0.0)

    # Bloc comparaison avant/après (planification classique vs optimisée)
    comparaison: Mapped[dict] = mapped_column(JSON, default=dict)
