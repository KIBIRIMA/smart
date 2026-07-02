from sqlalchemy import String, Float, Integer, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin


class Tournee(Base, TimestampMixin):
    __tablename__ = "tournees"

    id: Mapped[int] = mapped_column(primary_key=True)
    optimisation_id: Mapped[int | None] = mapped_column(ForeignKey("optimisations.id"), nullable=True)
    chauffeur_id: Mapped[int | None] = mapped_column(ForeignKey("chauffeurs.id"), nullable=True)
    vehicule_id: Mapped[int | None] = mapped_column(ForeignKey("vehicules.id"), nullable=True)
    chauffeur_nom: Mapped[str] = mapped_column(String(120), default="")
    vehicule_immat: Mapped[str] = mapped_column(String(20), default="")
    nb_missions: Mapped[int] = mapped_column(Integer, default=0)
    km: Mapped[float] = mapped_column(Float, default=0.0)
    co2_kg: Mapped[float] = mapped_column(Float, default=0.0)
    taux_remplissage: Mapped[float] = mapped_column(Float, default=0.0)
    depart: Mapped[str] = mapped_column(String(10), default="07:00")
    statut: Mapped[str] = mapped_column(String(20), default="PLANIFIEE")
    couleur: Mapped[str] = mapped_column(String(10), default="#E65100")
    # Trace géographique de l'itinéraire : liste de [lat, lng]
    itineraire: Mapped[list] = mapped_column(JSON, default=list)
    # Explications de l'algorithme (transparence DSI)
    explications: Mapped[list] = mapped_column(JSON, default=list)
    # Machines chargées sur le plateau (pour la vue 2.5D)
    plateau: Mapped[list] = mapped_column(JSON, default=list)
    # Chronologie de la tournée : liste d'étapes {heure, lieu, action, machine, duree}
    chronologie: Mapped[list] = mapped_column(JSON, default=list)
