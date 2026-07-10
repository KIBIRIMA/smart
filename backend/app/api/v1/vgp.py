"""Module VGP — registre des contrôles périodiques par machine (n° de parc).

Gestion (auth EXPLOITANT) : liste, création/mise à jour, upload des PDF
(rapport VGP + notice d'utilisation).
Accès PUBLIC (sans auth) : consultation du statut + documents — c'est la
cible du QR code collé sur la machine, scanné sur chantier.
"""
import os
from datetime import date, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_role
from app.core.roles import Role
from app.db.session import get_db
from app.models.vgp import Vgp

router = APIRouter(prefix="/vgp", tags=["vgp"])

DOCS_DIR = Path(os.environ.get("VGP_DOCS_DIR", "/code/vgp_docs"))
VALIDITE_JOURS = 182  # VGP semestrielle (nacelles/PEMP)


# ─────────────────── ANALYSE DU PDF (meilleure lecture) ───────────────────
# Les rapports varient selon l'organisme (Apave, Dekra, Veritas…) : extraction
# best-effort par mots-clés + regex. Le résultat est RENVOYÉ pour confirmation
# par l'exploitant — jamais appliqué silencieusement.

import re as _re


def _analyser_pdf_vgp(chemin: Path, parc_attendu: str) -> dict:
    try:
        import pdfplumber
        with pdfplumber.open(str(chemin)) as pdf:
            texte = "\n".join((p.extract_text() or "") for p in pdf.pages)
    except Exception as e:
        return {"lecture_ok": False, "erreur": f"PDF illisible : {e}"}

    t = texte or ""
    tl = t.lower()

    # 1. Dates — préférer celles proches d'un mot-clé de vérification
    dates = []
    for m in _re.finditer(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b", t):
        try:
            d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            continue
        if d <= date.today():
            ctx = tl[max(0, m.start() - 60):m.start()]
            score = 2 if _re.search(r"v[ée]rification|effectu|intervention|contr[ôo]le", ctx) else 1
            dates.append((score, d))
    date_detectee = max(dates, key=lambda x: (x[0], x[1]))[1].isoformat() if dates else None

    # 2. N° de parc — le parc attendu apparaît-il dans le document ?
    parc_conforme = bool(parc_attendu) and bool(
        _re.search(rf"\b{_re.escape(parc_attendu)}\b", t))
    m_parc = _re.search(r"(?:n[°o]\s*(?:de\s*)?parc|parc)\s*[:\-]?\s*([A-Z0-9\-]{3,15})", t, _re.I)
    parc_detecte = m_parc.group(1).strip() if m_parc else None

    # 3. N° de série
    m_serie = _re.search(
        r"(?:n[°o]\s*(?:de\s*)?s[ée]rie|serial)\s*[:\-]?\s*([A-Z0-9\-]{4,25})", t, _re.I)
    serie_detectee = m_serie.group(1).strip() if m_serie else None

    # 3bis. Modèle machine (ligne "Machine : …")
    m_mod = _re.search(r"(?:machine|engin|mat[ée]riel)\s*[:\-]\s*([^\n]{3,60})", t, _re.I)
    modele_detecte = m_mod.group(1).strip() if m_mod else None

    # 4. Observations / réserves de l'inspecteur
    observations = None
    m_obs = _re.search(r"(?:observations?|r[ée]serves?|anomalies?)\s*[:\-]?\s*\n?(.{10,600}?)(?:\n\s*\n|$)",
                       t, _re.I | _re.S)
    if m_obs:
        observations = _re.sub(r"\s+", " ", m_obs.group(1)).strip()[:500]

    avertissements = []
    if not date_detectee:
        avertissements.append("Aucune date de vérification détectée — saisir manuellement.")
    if parc_attendu and not parc_conforme:
        avertissements.append(
            f"⚠ Le n° de parc {parc_attendu} n'apparaît PAS dans ce PDF"
            + (f" (parc détecté : {parc_detecte})" if parc_detecte else "")
            + " — vérifier que le document correspond bien à cette machine.")

    return {
        "lecture_ok": True,
        "date_detectee": date_detectee,
        "parc_attendu": parc_attendu,
        "parc_detecte": parc_detecte,
        "parc_conforme": parc_conforme,
        "serie_detectee": serie_detectee,
        "modele_detecte": modele_detecte,
        "observations": observations,
        "avertissements": avertissements,
    }


def _statut(date_vgp: date | None) -> dict:
    """Calcule l'échéance et le statut réglementaire d'une VGP."""
    if not date_vgp:
        return {"echeance": None, "jours_restants": None, "statut": "INCONNUE"}
    echeance = date_vgp + timedelta(days=VALIDITE_JOURS)
    restants = (echeance - date.today()).days
    statut = "EXPIREE" if restants < 0 else ("BIENTOT" if restants <= 30 else "OK")
    return {"echeance": echeance.isoformat(), "jours_restants": restants, "statut": statut}


def _serialize(v: Vgp) -> dict:
    base = {
        "parc": v.parc,
        "machine_modele": v.machine_modele,
        "date_vgp": v.date_vgp.isoformat() if v.date_vgp else None,
        "a_fichier_vgp": bool(v.fichier_vgp),
        "a_fichier_notice": bool(v.fichier_notice),
        "numero_serie": v.numero_serie,
        "observations": v.observations,
    }
    base.update(_statut(v.date_vgp))
    return base


# ─────────────────────────── GESTION (auth) ───────────────────────────

@router.get("/machines", dependencies=[Depends(require_role(Role.EXPLOITANT))])
async def liste_machines(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Vgp).order_by(Vgp.parc))).scalars().all()
    return [_serialize(v) for v in rows]


@router.post("/machines", dependencies=[Depends(require_role(Role.EXPLOITANT))])
async def upsert_machine(
    parc: str = Form(...),
    machine_modele: str = Form(""),
    date_vgp: str = Form(""),
    numero_serie: str = Form(""),
    observations: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    parc = parc.strip()
    if not parc:
        raise HTTPException(422, "n° de parc requis")
    v = (await db.execute(select(Vgp).where(Vgp.parc == parc))).scalar_one_or_none()
    if not v:
        v = Vgp(parc=parc)
        db.add(v)
    if machine_modele:
        v.machine_modele = machine_modele.strip()
    if date_vgp:
        v.date_vgp = date.fromisoformat(date_vgp)
    if numero_serie:
        v.numero_serie = numero_serie.strip()
    if observations:
        v.observations = observations.strip()[:1000]
    await db.commit()
    await db.refresh(v)
    return _serialize(v)


@router.post("/machines/{parc}/document",
             dependencies=[Depends(require_role(Role.EXPLOITANT))])
async def upload_document(
    parc: str,
    type: str = "vgp",  # vgp | notice
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    if type not in ("vgp", "notice"):
        raise HTTPException(422, "type = vgp ou notice")
    v = (await db.execute(select(Vgp).where(Vgp.parc == parc))).scalar_one_or_none()
    if not v:
        raise HTTPException(404, "machine inconnue au registre VGP")
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    dest = DOCS_DIR / f"{parc}_{type}.pdf"
    dest.write_bytes(await file.read())
    analyse = None
    if type == "vgp":
        v.fichier_vgp = str(dest)
        analyse = _analyser_pdf_vgp(dest, v.parc)
    else:
        v.fichier_notice = str(dest)
    await db.commit()
    return {"ok": True, "fichier": dest.name, "analyse": analyse}


@router.post("/import-pdfs", dependencies=[Depends(require_role(Role.EXPLOITANT))])
async def import_pdfs(
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Dépôt EN MASSE des rapports VGP reçus des inspecteurs.

    Pour chaque PDF : lecture automatique → détection du n° de parc →
    création/mise à jour de la machine + date + série + observations,
    SANS saisie manuelle. Les fichiers dont le parc n'est pas détecté
    ressortent "à vérifier" pour affectation manuelle.
    """
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    recap = []
    for f in files:
        tmp = DOCS_DIR / f"_tmp_{f.filename or 'doc.pdf'}"
        tmp.write_bytes(await f.read())
        a = _analyser_pdf_vgp(tmp, "")
        parc = (a.get("parc_detecte") or "").strip()
        if not a.get("lecture_ok"):
            tmp.unlink(missing_ok=True)
            recap.append({"fichier": f.filename, "statut": "ERREUR",
                          "detail": a.get("erreur", "PDF illisible")})
            continue
        if not parc:
            tmp.unlink(missing_ok=True)
            recap.append({"fichier": f.filename, "statut": "A_VERIFIER",
                          "detail": "n° de parc non détecté dans le PDF",
                          "analyse": a})
            continue
        # upsert automatique de la machine
        v = (await db.execute(select(Vgp).where(Vgp.parc == parc))).scalar_one_or_none()
        if not v:
            v = Vgp(parc=parc)
            db.add(v)
        if a.get("modele_detecte") and not v.machine_modele:
            v.machine_modele = a["modele_detecte"][:120]
        if a.get("date_detectee"):
            v.date_vgp = date.fromisoformat(a["date_detectee"])
        if a.get("serie_detectee"):
            v.numero_serie = a["serie_detectee"]
        if a.get("observations"):
            v.observations = a["observations"][:1000]
        dest = DOCS_DIR / f"{parc}_vgp.pdf"
        tmp.replace(dest)
        v.fichier_vgp = str(dest)
        recap.append({"fichier": f.filename, "statut": "INSEREE", "parc": parc,
                      "date": a.get("date_detectee"),
                      "serie": a.get("serie_detectee"),
                      "modele": a.get("modele_detecte"),
                      "observations": bool(a.get("observations"))})
    await db.commit()
    inserees = sum(1 for r in recap if r["statut"] == "INSEREE")
    return {"total": len(recap), "inserees": inserees,
            "a_verifier": len(recap) - inserees, "details": recap}


# ─────────────────────── ACCÈS PUBLIC (QR code) ───────────────────────
# Volontairement SANS auth : le QR est scanné sur chantier par le client
# ou l'inspecteur, sans compte. N'expose que le statut et les documents.

@router.get("/public/{parc}")
async def fiche_publique(parc: str, db: AsyncSession = Depends(get_db)):
    v = (await db.execute(select(Vgp).where(Vgp.parc == parc))).scalar_one_or_none()
    if not v:
        raise HTTPException(404, "machine inconnue")
    return _serialize(v)


@router.get("/public/{parc}/document/{type}")
async def document_public(parc: str, type: str, db: AsyncSession = Depends(get_db)):
    v = (await db.execute(select(Vgp).where(Vgp.parc == parc))).scalar_one_or_none()
    if not v:
        raise HTTPException(404, "machine inconnue")
    chemin = v.fichier_vgp if type == "vgp" else v.fichier_notice
    if not chemin or not Path(chemin).exists():
        raise HTTPException(404, "document non disponible")
    nom = f"{'VGP' if type == 'vgp' else 'Notice'}_{parc}.pdf"
    return FileResponse(chemin, media_type="application/pdf", filename=nom)
