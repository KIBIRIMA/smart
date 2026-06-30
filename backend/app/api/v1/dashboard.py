"""KPI agrégés du tableau de bord — calculés en base, jamais en dur côté front."""
from typing import Annotated
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser
from app.db.session import get_db
from app.models.mission import Mission
from app.models.tournee import Tournee
from app.models.optimisation import Optimisation

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/kpi")
async def kpi(db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser):
    nb_missions = (await db.execute(select(func.count(Mission.id)))).scalar() or 0
    nb_tournees = (await db.execute(select(func.count(Tournee.id)))).scalar() or 0
    km_total = (await db.execute(select(func.coalesce(func.sum(Tournee.km), 0)))).scalar() or 0
    co2 = (await db.execute(select(func.coalesce(func.sum(Tournee.co2_kg), 0)))).scalar() or 0
    taux = (await db.execute(select(func.coalesce(func.avg(Tournee.taux_remplissage), 0)))).scalar() or 0

    # dernier run pour économies & coût
    last = (await db.execute(
        select(Optimisation).where(Optimisation.statut == "TERMINEE")
        .order_by(Optimisation.created_at.desc()).limit(1)
    )).scalar_one_or_none()

    cout = last.cout_estime if last else 0.0
    litres = float(km_total) * 32.0 / 100
    carburant = round(litres, 0)

    economies = 0.0
    if last and last.comparaison:
        for m in last.comparaison.get("metrics", []):
            if m.get("label") == "Coût carburant":
                try:
                    economies = abs(float(m["avant"].split()[0].replace(" ", "")) -
                                    float(m["apres"].split()[0].replace(" ", "")))
                except Exception:
                    pass

    return {
        "missions": nb_missions,
        "tournees": nb_tournees,
        "km": round(float(km_total), 0),
        "cout_estime": round(float(cout), 0),
        "carburant_l": carburant,
        "co2_kg": round(float(co2), 0),
        "taux_remplissage": round(float(taux), 1),
        "economies": round(economies, 0),
    }
