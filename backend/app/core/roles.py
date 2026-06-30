"""Rôles applicatifs et hiérarchie des permissions."""
from enum import Enum


class Role(str, Enum):
    ADMIN = "ADMIN"            # Administrateur — accès total
    DSI = "DSI"               # Direction des systèmes d'information
    EXPLOITANT = "EXPLOITANT"  # Exploitation quotidienne (planifie, optimise)
    CHEF_AGENCE = "CHEF_AGENCE"  # Pilotage d'une agence
    LECTURE = "LECTURE"        # Lecture seule


# Niveau hiérarchique : un rôle hérite des permissions de niveau inférieur.
ROLE_LEVEL = {
    Role.LECTURE: 0,
    Role.CHEF_AGENCE: 1,
    Role.EXPLOITANT: 2,
    Role.DSI: 3,
    Role.ADMIN: 4,
}

# Rôles autorisés à écrire (créer/modifier/lancer des optimisations).
WRITE_ROLES = {Role.ADMIN, Role.DSI, Role.EXPLOITANT, Role.CHEF_AGENCE}
