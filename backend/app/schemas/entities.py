"""Schémas de lecture des entités du domaine."""
from datetime import date
from pydantic import BaseModel


class MachineOut(BaseModel):
    id: int
    modele: str
    constructeur: str
    famille: str
    longueur_m: float
    largeur_m: float
    hauteur_m: float
    poids_kg: float
    class Config: from_attributes = True


class VehiculeOut(BaseModel):
    id: int
    immatriculation: str
    libelle: str
    plateau_longueur_m: float
    plateau_largeur_m: float
    charge_utile_kg: float
    conso_l_100km: float
    disponible: bool
    class Config: from_attributes = True


class ChauffeurOut(BaseModel):
    id: int
    nom: str
    telephone: str
    permis: str
    disponible: bool
    class Config: from_attributes = True


class ClientOut(BaseModel):
    id: int
    nom: str
    adresse: str
    code_postal: str
    ville: str
    lat: float | None
    lng: float | None
    class Config: from_attributes = True


class MissionOut(BaseModel):
    id: int
    client_nom: str
    adresse: str
    lat: float | None
    lng: float | None
    type_op: str
    machine_modele: str
    quantite: int
    statut: str
    date_prevue: date | None
    tournee_id: int | None
    class Config: from_attributes = True


class TourneeOut(BaseModel):
    id: int
    chauffeur_nom: str
    vehicule_immat: str
    nb_missions: int
    km: float
    co2_kg: float
    taux_remplissage: float
    depart: str
    statut: str
    couleur: str
    itineraire: list
    explications: list
    plateau: list = []
    chronologie: list = []
    class Config: from_attributes = True


class OptimisationOut(BaseModel):
    id: int
    reference: str
    date_tournee: date | None
    user_nom: str
    moteur: str
    statut: str
    nb_missions: int
    nb_tournees: int
    km_total: float
    taux_moyen: float
    cout_estime: float
    co2_kg: float
    duree_calcul_s: float
    comparaison: dict
    class Config: from_attributes = True


class AgenceOut(BaseModel):
    id: int
    nom: str
    code: str
    adresse: str
    lat: float
    lng: float
    class Config: from_attributes = True
