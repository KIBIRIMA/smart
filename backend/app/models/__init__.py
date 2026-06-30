"""Import central des modèles pour qu'Alembic et la création de schéma les voient tous."""
from app.db.base import Base
from app.models.user import User
from app.models.agence import Agence
from app.models.client import Client
from app.models.machine import Machine
from app.models.vehicule import Vehicule
from app.models.chauffeur import Chauffeur
from app.models.mission import Mission
from app.models.tournee import Tournee
from app.models.optimisation import Optimisation

__all__ = [
    "Base", "User", "Agence", "Client", "Machine",
    "Vehicule", "Chauffeur", "Mission", "Tournee", "Optimisation",
]
