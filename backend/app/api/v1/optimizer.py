"""Routes du moteur d'optimisation et de la simulation."""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, require_role
from app.core.roles import Role
from app.db.session import get_db
from app.models.agence import Agence
from app.models.machine import Machine
from app.models.mission import Mission
from app.models.vehicule import Vehicule
from app.models.chauffeur import Chauffeur
from app.models.optimisation import Optimisation
from app.schemas.optimizer import OptimizeRequest, SimulateRequest, OptimizeResult
from app.optimizer import adapter

router = APIRouter(prefix="/optimizer", tags=["optimizer"])
DB = Annotated[AsyncSession, Depends(get_db)]


async def _load_context(db: AsyncSession, agence_id: int | None, mission_ids: list[int] | None):
    # dépôt = agence (ou première agence)
    aq = select(Agence)
    if agence_id:
        aq = aq.where(Agence.id == agence_id)
    agence = (await db.execute(aq.limit(1))).scalar_one_or_none()
    depot = {"lat": agence.lat, "lng": agence.lng} if agence else {"lat": 48.632, "lng": 2.47}

    mq = select(Mission)
    if mission_ids:
        mq = mq.where(Mission.id.in_(mission_ids))
    else:
        mq = mq.where(Mission.statut == "A_PLANIFIER")
    missions = (await db.execute(mq)).scalars().all()

    machines = (await db.execute(select(Machine))).scalars().all()
    machines_by_id = {
        m.id: {"longueur_m": m.longueur_m, "largeur_m": m.largeur_m, "poids_kg": m.poids_kg}
        for m in machines
    }
    return depot, missions, machines_by_id, agence


@router.post("/run", response_model=OptimizeResult,
             dependencies=[Depends(require_role(Role.EXPLOITANT))])
async def run(body: OptimizeRequest, db: DB, user: CurrentUser):
    depot, missions, machines_by_id, agence = await _load_context(db, body.agence_id, body.mission_ids)
    if not missions:
        raise HTTPException(400, "Aucune mission à optimiser (statut A_PLANIFIER)")

    # Tente d'abord le VRAI moteur v11 (OR-Tools + Plateau 2.5D).
    # En cas d'échec (lib manquante, géocodage indispo...), repli sur le moteur de référence.
    result = None
    try:
        import anyio
        from app.optimizer import adapter_v11
        result = await anyio.to_thread.run_sync(
            lambda: adapter_v11.run_optimization_v11(missions, {"moteur": body.moteur})
        )
    except Exception as exc:
        import logging
        logging.getLogger("optimizer").warning("Moteur v11 indisponible, repli référence: %s", exc)
        result = None

    if result is None:
        result = adapter.run_optimization(
            missions, machines_by_id, depot,
            {"moteur": body.moteur, "fusion": body.fusion},
        )

    # Archive l'optimisation + ses tournées
    opt = Optimisation(
        reference=result["reference"], date_tournee=body.date_tournee,
        agence_id=agence.id if agence else None, user_id=user.id, user_nom=user.full_name,
        moteur=result["moteur"], statut="TERMINEE",
        nb_missions=result["nb_missions"], nb_tournees=result["nb_tournees"],
        km_total=result["km_total"], taux_moyen=result["taux_moyen"],
        cout_estime=result["cout_estime"], co2_kg=result["co2_kg"],
        duree_calcul_s=result["duree_calcul_s"],
        comparaison={"metrics": result["comparaison"]},
    )
    db.add(opt)
    await db.flush()

    # Remplace les tournées précédentes par celles du nouveau run
    from app.models.tournee import Tournee
    from sqlalchemy import delete as _delete
    await db.execute(_delete(Tournee))
    for t in result["tournees"]:
        db.add(Tournee(
            optimisation_id=opt.id,
            chauffeur_nom=t.get("chauffeur_nom", ""),
            vehicule_immat=t.get("vehicule_immat", ""),
            nb_missions=t["nb_missions"],
            km=t["km"], co2_kg=t["co2_kg"], taux_remplissage=t["taux_remplissage"],
            depart=t.get("depart", "05:00"), statut="PLANIFIEE",
            couleur=t.get("couleur", "#E65100"),
            itineraire=t.get("itineraire", []),
            explications=t.get("explications", []),
            plateau=t.get("plateau", []),
            chronologie=t.get("chronologie", []),
        ))
    await db.commit()
    return result


@router.post("/simulate", response_model=OptimizeResult,
             dependencies=[Depends(require_role(Role.EXPLOITANT))])
async def simulate(body: SimulateRequest, db: DB, user: CurrentUser):
    """Relance l'optimisation avec contraintes modifiées (camion +, chauffeur indispo, missions +)."""
    depot, missions, machines_by_id, agence = await _load_context(db, body.agence_id, body.mission_ids)

    # Intègre les nouvelles missions simulées (non persistées)
    class _Tmp:
        pass
    extra = []
    for i, nm in enumerate(body.constraints.nouvelles_missions):
        t = _Tmp()
        t.id = -(i + 1)
        t.lat = nm.get("lat"); t.lng = nm.get("lng")
        t.type_op = nm.get("type_op", "livraison")
        t.machine_id = nm.get("machine_id")
        t.machine_modele = nm.get("machine_modele", "")
        t.client_nom = nm.get("client", "Mission simulée")
        extra.append(t)

    all_missions = list(missions) + extra
    if not all_missions:
        raise HTTPException(400, "Aucune mission à simuler")

    result = adapter.run_optimization(
        all_missions, machines_by_id, depot,
        {"moteur": body.moteur, "fusion": body.fusion,
         "camions_extra": body.constraints.camions_supplementaires},
    )
    result["reference"] = result["reference"].replace("OPT-", "SIM-")
    result["statut"] = "SIMULATION"
    return result


@router.get("/history")
async def history(db: DB, user: CurrentUser, limit: int = 20):
    res = await db.execute(
        select(Optimisation).order_by(Optimisation.created_at.desc()).limit(limit)
    )
    rows = res.scalars().all()
    return [
        {
            "id": o.id, "reference": o.reference,
            "date": o.created_at.isoformat() if o.created_at else None,
            "user": o.user_nom, "moteur": o.moteur,
            "nb_missions": o.nb_missions, "nb_tournees": o.nb_tournees,
            "km_total": o.km_total, "taux_moyen": o.taux_moyen,
            "cout_estime": o.cout_estime, "co2_kg": o.co2_kg,
            "comparaison": o.comparaison,
        }
        for o in rows
    ]
