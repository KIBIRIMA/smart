"""Schémas d'entrée/sortie du moteur d'optimisation et de la simulation."""
from datetime import date
from pydantic import BaseModel, Field


class OptimizeRequest(BaseModel):
    date_tournee: date | None = None
    agence_id: int | None = None
    moteur: str = "v12"
    fusion: bool = True
    mission_ids: list[int] | None = None  # None = toutes les missions à planifier


class SimulationConstraints(BaseModel):
    """Contraintes modifiables avant de relancer une optimisation."""
    camions_supplementaires: int = Field(0, ge=0, le=20)
    chauffeurs_indisponibles: list[int] = []
    vehicules_indisponibles: list[int] = []
    nouvelles_missions: list[dict] = []
    contraintes_manuelles: list[dict] = []  # missions épinglées sur une tournée


class SimulateRequest(OptimizeRequest):
    constraints: SimulationConstraints = SimulationConstraints()


class ComparisonMetric(BaseModel):
    label: str
    avant: str
    apres: str
    gain: str
    delta_pct: float | None = None


class OptimizeResult(BaseModel):
    reference: str
    statut: str
    moteur: str
    nb_missions: int
    nb_tournees: int
    nb_tournees_min_theorique: int
    km_total: float
    taux_moyen: float
    cout_estime: float
    co2_kg: float
    duree_calcul_s: float
    comparaison: list[ComparisonMetric]
    tournees: list[dict]
