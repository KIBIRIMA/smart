"""Route d'import : upload d'un fichier CSV de missions → géocodage → insertion en base."""
import csv
import io
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, require_role
from app.core.roles import Role
from app.db.session import get_db
from app.models.mission import Mission
from app.services.geocode import geocode

router = APIRouter(prefix="/import", tags=["import"])
logger = logging.getLogger("import")


def _detect_delimiter(sample: str) -> str:
    return ";" if sample.count(";") >= sample.count(",") else ","


def _get(row: dict, *names: str, default: str = "") -> str:
    for n in names:
        if n in row and row[n] is not None and str(row[n]).strip():
            return str(row[n]).strip()
    return default


@router.post("/missions", dependencies=[Depends(require_role(Role.EXPLOITANT))])
async def import_missions(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    file: UploadFile = File(...),
    remplacer: bool = True,
):
    """
    Importe des missions depuis un CSV.
    Colonnes reconnues (souples) : client, ville, code_postal, adresse,
    type_mission/type_op, machine.
    Chaque ligne est géocodée (API adresse.gouv + repli ville IDF).
    Si remplacer=True, les missions A_PLANIFIER existantes sont effacées d'abord.
    """
    raw = await file.read()
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = raw.decode("latin-1")

    delimiter = _detect_delimiter(content[:2048])
    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)

    if remplacer:
        await db.execute(delete(Mission).where(Mission.statut == "A_PLANIFIER"))

    inserees = 0
    sources = {"api": 0, "ville": 0, "defaut": 0}
    erreurs: list[str] = []

    for i, row in enumerate(reader, start=2):
        client = _get(row, "client", "client_nom")
        ville = _get(row, "ville")
        if not client and not ville:
            continue
        adresse = _get(row, "adresse")
        code_postal = _get(row, "code_postal", "cp")
        type_op = _get(row, "type_op", "type_mission", default="livraison").lower()
        if type_op not in ("livraison", "recuperation"):
            type_op = "livraison"
        machine = _get(row, "machine", "machine_modele")

        try:
            lat, lng, source = geocode(adresse, ville, code_postal)
            sources[source] = sources.get(source, 0) + 1
        except Exception as exc:
            erreurs.append(f"Ligne {i}: géocodage échoué ({exc})")
            continue

        adresse_complete = ", ".join(p for p in [adresse, code_postal, ville] if p)
        db.add(Mission(
            client_nom=client or ville,
            adresse=adresse_complete,
            lat=lat, lng=lng,
            type_op=type_op,
            machine_modele=machine,
            quantite=1,
            statut="A_PLANIFIER",
        ))
        inserees += 1

    await db.flush()
    logger.info("Import: %d missions (%s) par %s", inserees, sources, user.email)

    return {
        "importees": inserees,
        "geocodage": sources,
        "remplacement": remplacer,
        "erreurs": erreurs,
        "message": f"{inserees} mission(s) importée(s) et géolocalisée(s).",
    }
