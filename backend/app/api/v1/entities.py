"""Routes de lecture des entités : toutes les données du front viennent d'ici."""
from typing import Annotated
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser
from app.db.session import get_db
from app.models.machine import Machine
from app.models.vehicule import Vehicule
from app.models.chauffeur import Chauffeur
from app.models.client import Client
from app.models.mission import Mission
from app.models.tournee import Tournee
from app.models.agence import Agence
from app.schemas.entities import (MachineOut, VehiculeOut, ChauffeurOut, ClientOut,
                                  MissionOut, TourneeOut, AgenceOut)

router = APIRouter(tags=["entities"])
DB = Annotated[AsyncSession, Depends(get_db)]


@router.get("/machines", response_model=list[MachineOut])
async def list_machines(db: DB, user: CurrentUser):
    res = await db.execute(select(Machine).order_by(Machine.modele))
    return res.scalars().all()


@router.get("/vehicules", response_model=list[VehiculeOut])
async def list_vehicules(db: DB, user: CurrentUser, disponible: bool | None = None):
    q = select(Vehicule)
    if disponible is not None:
        q = q.where(Vehicule.disponible == disponible)
    res = await db.execute(q.order_by(Vehicule.immatriculation))
    return res.scalars().all()


@router.get("/chauffeurs", response_model=list[ChauffeurOut])
async def list_chauffeurs(db: DB, user: CurrentUser, disponible: bool | None = None):
    q = select(Chauffeur)
    if disponible is not None:
        q = q.where(Chauffeur.disponible == disponible)
    res = await db.execute(q.order_by(Chauffeur.nom))
    return res.scalars().all()


@router.get("/clients", response_model=list[ClientOut])
async def list_clients(db: DB, user: CurrentUser):
    res = await db.execute(select(Client).order_by(Client.nom))
    return res.scalars().all()


@router.get("/missions", response_model=list[MissionOut])
async def list_missions(
    db: DB, user: CurrentUser,
    statut: str | None = None,
    type_op: str | None = None,
    q: str | None = Query(None, description="Recherche client/adresse/machine"),
):
    query = select(Mission)
    if statut:
        query = query.where(Mission.statut == statut)
    if type_op:
        query = query.where(Mission.type_op == type_op)
    res = await db.execute(query.order_by(Mission.id))
    rows = res.scalars().all()
    if q:
        ql = q.lower()
        rows = [m for m in rows if ql in (m.client_nom or "").lower()
                or ql in (m.adresse or "").lower() or ql in (m.machine_modele or "").lower()]
    return rows


@router.get("/tournees", response_model=list[TourneeOut])
async def list_tournees(db: DB, user: CurrentUser, optimisation_id: int | None = None):
    q = select(Tournee)
    if optimisation_id:
        q = q.where(Tournee.optimisation_id == optimisation_id)
    res = await db.execute(q.order_by(Tournee.id))
    return res.scalars().all()


@router.get("/agences", response_model=list[AgenceOut])
async def list_agences(db: DB, user: CurrentUser):
    res = await db.execute(select(Agence).order_by(Agence.nom))
    return res.scalars().all()
