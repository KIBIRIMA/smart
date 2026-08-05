"""Rôles applicatifs et hiérarchie des permissions."""
from enum import Enum


class Role(str, Enum):
    ADMIN = "ADMIN"            # Administrateur — accès total
    DSI = "DSI"               # Direction des systèmes d'information
    EXPLOITANT = "EXPLOITANT"  # Exploitation quotidienne (planifie, optimise)
    CHEF_ATELIER = "CHEF_ATELIER"  # Atelier — maintenance, levée des réserves VGP
    CHEF_AGENCE = "CHEF_AGENCE"  # Pilotage d'une agence
    LECTURE = "LECTURE"        # Lecture seule


# Niveau hiérarchique : un rôle hérite des permissions de niveau inférieur.
#
# CHEF_ATELIER est placé au même niveau qu'EXPLOITANT : ce n'est pas un
# échelon supérieur, c'est une fonction parallèle (l'atelier n'a pas
# vocation à planifier les tournées, ni l'exploitation à intervenir sur
# les machines). Le niveau lui donne l'accès aux écrans d'exploitation ;
# les actions réservées à l'atelier — publication d'un rapport VGP et
# levée d'anomalie — sont contrôlées séparément, par appartenance à un
# ensemble de rôles et non par comparaison de niveau (voir
# app/api/v1/vgp.py, constante _ROLES_ATELIER).
ROLE_LEVEL = {
    Role.LECTURE: 0,
    Role.CHEF_AGENCE: 1,
    Role.EXPLOITANT: 2,
    Role.CHEF_ATELIER: 2,
    Role.DSI: 3,
    Role.ADMIN: 4,
}

# Rôles autorisés à écrire (créer/modifier/lancer des optimisations).
WRITE_ROLES = {Role.ADMIN, Role.DSI, Role.EXPLOITANT, Role.CHEF_ATELIER,
               Role.CHEF_AGENCE}
