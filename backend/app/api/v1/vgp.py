"""Module VGP — registre + HISTORIQUE des contrôles par machine (n° de parc).

Gestion (auth EXPLOITANT) : liste, upsert, dépôt en masse des PDF (lecture
automatique), upload unitaire.
Accès PUBLIC (sans auth) : fiche machine avec l'historique complet des VGP —
c'est la cible du QR code UNIQUE collé sur la machine.

Chaque PDF déposé AJOUTE un rapport à l'historique (aucun écrasement).
"""
import os
import re as _re
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_role
from app.core.roles import Role
from app.db.session import get_db
from app.models.vgp import Vgp, VgpRapport

router = APIRouter(prefix="/vgp", tags=["vgp"])

DOCS_DIR = Path(os.environ.get("VGP_DOCS_DIR", "/code/vgp_docs"))
VALIDITE_JOURS = 182  # VGP semestrielle (nacelles/PEMP)


# ─────────────────── ANALYSE DU PDF (meilleure lecture) ───────────────────
# Formats variables selon l'organisme (CADET, Apave, Dekra, Veritas…) :
# extraction best-effort par mots-clés + regex, testée sur rapports réels.

def _analyser_pdf_vgp(chemin: Path, parc_attendu: str) -> dict:
    try:
        import pdfplumber
        with pdfplumber.open(str(chemin)) as pdf:
            texte = "\n".join((p.extract_text() or "") for p in pdf.pages)
    except Exception as e:
        return {"lecture_ok": False, "erreur": f"PDF illisible : {e}"}

    t = texte or ""
    tl = t.lower()

    # 1. Date de vérification — privilégier le contexte "vérification/effectuée"
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

    # 2. N° de parc — libellés variables + cas tableau CADET éclaté
    parc_detecte = None
    m_parc = _re.search(
        r"(?:n[°o]\s*(?:de\s*)?parc|code\s*(?:entreprise|parc|interne|client))"
        r"\s*[:\-]?\s*\n?\s*([A-Z0-9\-]{3,15})", t, _re.I)
    if m_parc:
        parc_detecte = m_parc.group(1).strip()
    else:
        # Tableau CADET : "Code\n<parc> Année ...\nentreprise"
        m_parc = _re.search(r"Code\s*\n\s*([A-Z0-9\-]{3,15})\b[^\n]*\n\s*entreprise", t, _re.I)
        if m_parc:
            parc_detecte = m_parc.group(1).strip()
    parc_conforme = bool(parc_attendu) and bool(
        _re.search(rf"\b{_re.escape(parc_attendu)}\b", t))

    # 3. N° de série / fabrication
    m_serie = _re.search(
        r"(?:n[°o]\s*(?:de\s*)?s[ée]rie|serial|fabrication)\s*[:\-]?\s*([A-Z0-9\-]{4,25})",
        t, _re.I)
    serie_detectee = m_serie.group(1).strip() if m_serie else None

    # 4. Modèle — priorité "Type :", liste noire des faux positifs
    modele_detecte = None
    for pattern in (
        r"(?:^|\n)\s*Type\s*[:\-]?\s*([A-Z][A-Z0-9][A-Z0-9 \-/]{1,20})(?=\n|$|\s{2,})",
        r"Marque\s*[:\-]?\s*([A-Za-z][\w \-]{2,25})\s+Type\s*[:\-]?\s*([A-Z0-9][\w \-/]{1,20})(?=\n|$|\s{2,})",
        r"(?:machine|engin|mat[ée]riel|équipement)\s*[:\-]\s*([A-Z][A-Za-z0-9][^\n]{2,50})",
    ):
        m = _re.search(pattern, t, _re.I)
        if m:
            cand = (m.group(2) if m.lastindex and m.lastindex >= 2 else m.group(1)).strip()
            interdits = ("appareil", "location", "utilisatrice", "vérification", "verification",
                         "société", "societe", "accès", "acces", "industrie", "cabinet",
                         "chef", "atelier", "hydraulique", "conservation", "présente", "presente")
            if any(x in cand.lower() for x in interdits):
                continue
            if not _re.search(r"\d|[A-Z]{2,}", cand):
                continue
            modele_detecte = cand[:60]
            break

    # 5. Observations / remarques — itérer sur TOUTES les occurrences
    # (les rapports contiennent souvent un champ "Remarques" vide en page 1
    # et le vrai contenu plus loin) ; garder la 1re non-vide non-structurelle.
    observations = None
    _STRUCT = _re.compile(
        r"^(rapport transmis|contribuons|liste|accr[ée]|l'examen|c'est au chef|avis\s*:)", _re.I)
    for m in _re.finditer(
            r"(?:observations?|remarques?|r[ée]serves?)\s*[:\-]?\s*\n(.{3,300}?)(?:\n|$)",
            t, _re.I):
        cand = _re.sub(r"\s+", " ", m.group(1)).strip()
        if cand and not _STRUCT.match(cand):
            observations = cand[:500]
            break

    # 6. Présence d'anomalie (champ clé de conformité : OUI / NON)
    anomalie = None
    m_ano = _re.search(r"pr[ée]sence\s+d'?anomalies?\s*[:\-]?\s*(OUI|NON|YES|NO)\b", t, _re.I)
    if m_ano:
        anomalie = "OUI" if m_ano.group(1).upper() in ("OUI", "YES") else "NON"

    avertissements = []
    if anomalie == "OUI":
        avertissements.append("🔴 Le rapport signale une PRÉSENCE D'ANOMALIE — vérifier les réserves de l'inspecteur.")
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
        "anomalie": anomalie,
        "avertissements": avertissements,
    }


def _statut(date_vgp: date | None) -> dict:
    if not date_vgp:
        return {"echeance": None, "jours_restants": None, "statut": "INCONNUE"}
    echeance = date_vgp + timedelta(days=VALIDITE_JOURS)
    restants = (echeance - date.today()).days
    statut = "EXPIREE" if restants < 0 else ("BIENTOT" if restants <= 30 else "OK")
    return {"echeance": echeance.isoformat(), "jours_restants": restants, "statut": statut}


def _serialize(v: Vgp, nb_rapports: int = 0) -> dict:
    base = {
        "parc": v.parc,
        "machine_modele": v.machine_modele,
        "date_vgp": v.date_vgp.isoformat() if v.date_vgp else None,
        "a_fichier_vgp": bool(v.fichier_vgp),
        "a_fichier_notice": bool(v.fichier_notice),
        "numero_serie": v.numero_serie,
        "observations": v.observations,
        "anomalie": v.anomalie,
        "nb_rapports": nb_rapports,
    }
    base.update(_statut(v.date_vgp))
    return base


async def _nb_rapports(db: AsyncSession, parc: str) -> int:
    rows = (await db.execute(select(VgpRapport.id).where(VgpRapport.parc == parc))).all()
    return len(rows)


async def _ajouter_rapport(db: AsyncSession, v: Vgp, a: dict, pdf_source: Path) -> VgpRapport:
    """Ajoute un rapport à l'historique (fichier horodaté, jamais d'écrasement)
    et met à jour le cache 'dernier état' de la machine si plus récent."""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = DOCS_DIR / f"{v.parc}_vgp_{stamp}.pdf"
    pdf_source.replace(dest)

    r = VgpRapport(
        parc=v.parc,
        date_vgp=date.fromisoformat(a["date_detectee"]) if a.get("date_detectee") else None,
        numero_serie=a.get("serie_detectee"),
        observations=(a.get("observations") or "")[:1000] or None,
        anomalie=a.get("anomalie"),
        fichier=str(dest),
    )
    db.add(r)

    # mise à jour du cache machine (si rapport plus récent que l'état connu)
    if r.date_vgp and (not v.date_vgp or r.date_vgp >= v.date_vgp):
        v.date_vgp = r.date_vgp
        v.fichier_vgp = str(dest)
        if r.numero_serie:
            v.numero_serie = r.numero_serie
        if r.observations:
            v.observations = r.observations
        v.anomalie = r.anomalie
    if a.get("modele_detecte") and not v.machine_modele:
        v.machine_modele = a["modele_detecte"][:120]
    return r


# ─────────────────────────── GESTION (auth) ───────────────────────────

@router.get("/machines", dependencies=[Depends(require_role(Role.EXPLOITANT))])
async def liste_machines(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Vgp).order_by(Vgp.parc))).scalars().all()
    out = []
    for v in rows:
        out.append(_serialize(v, await _nb_rapports(db, v.parc)))
    return out


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
    return _serialize(v, await _nb_rapports(db, v.parc))


@router.post("/import-pdfs", dependencies=[Depends(require_role(Role.EXPLOITANT))])
async def import_pdfs(
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Dépôt EN MASSE des rapports reçus des inspecteurs.

    Chaque PDF : lecture automatique → détection du parc → création de la
    machine si absente → AJOUT à l'historique + mise à jour du dernier état.
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
        v = (await db.execute(select(Vgp).where(Vgp.parc == parc))).scalar_one_or_none()
        if not v:
            v = Vgp(parc=parc)
            db.add(v)
            await db.flush()
        await _ajouter_rapport(db, v, a, tmp)
        recap.append({"fichier": f.filename, "statut": "INSEREE", "parc": parc,
                      "anomalie": a.get("anomalie"),
                      "date": a.get("date_detectee"),
                      "serie": a.get("serie_detectee"),
                      "modele": a.get("modele_detecte"),
                      "observations": bool(a.get("observations"))})
    await db.commit()
    inserees = sum(1 for r in recap if r["statut"] == "INSEREE")
    return {"total": len(recap), "inserees": inserees,
            "a_verifier": len(recap) - inserees, "details": recap}


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

    if type == "notice":
        dest = DOCS_DIR / f"{parc}_notice.pdf"
        dest.write_bytes(await file.read())
        v.fichier_notice = str(dest)
        await db.commit()
        return {"ok": True, "fichier": dest.name, "analyse": None}

    # rapport VGP unitaire : analyse + ajout à l'historique
    tmp = DOCS_DIR / f"_tmp_{parc}.pdf"
    tmp.write_bytes(await file.read())
    analyse = _analyser_pdf_vgp(tmp, parc)
    await _ajouter_rapport(db, v, analyse, tmp)
    await db.commit()
    return {"ok": True, "analyse": analyse}


# ─────────────────────── ACCÈS PUBLIC (QR code) ───────────────────────
# Sans auth : le QR (UNIQUE par machine, permanent) est scanné sur chantier.

@router.get("/public/{parc}")
async def fiche_publique(parc: str, db: AsyncSession = Depends(get_db)):
    v = (await db.execute(select(Vgp).where(Vgp.parc == parc))).scalar_one_or_none()
    if not v:
        raise HTTPException(404, "machine inconnue")
    rapports = (await db.execute(
        select(VgpRapport).where(VgpRapport.parc == parc)
        .order_by(VgpRapport.date_vgp.desc().nullslast(), VgpRapport.id.desc())
    )).scalars().all()

    hist = [{
        "id": r.id,
        "date_vgp": r.date_vgp.isoformat() if r.date_vgp else None,
        "numero_serie": r.numero_serie,
        "observations": r.observations,
        "anomalie": r.anomalie,
        "a_fichier": bool(r.fichier),
    } for r in rapports]

    # compatibilité : machine renseignée avant l'historique → entrée legacy
    if not hist and v.fichier_vgp:
        hist = [{"id": 0,
                 "date_vgp": v.date_vgp.isoformat() if v.date_vgp else None,
                 "numero_serie": v.numero_serie,
                 "observations": v.observations,
                 "a_fichier": True}]

    out = _serialize(v, len(hist))
    out["rapports"] = hist
    return out


@router.get("/public/{parc}/rapport/{rid}")
async def rapport_public(parc: str, rid: int, db: AsyncSession = Depends(get_db)):
    v = (await db.execute(select(Vgp).where(Vgp.parc == parc))).scalar_one_or_none()
    if not v:
        raise HTTPException(404, "machine inconnue")
    if rid == 0:  # entrée legacy (avant historique)
        chemin = v.fichier_vgp
        nom = f"VGP_{parc}.pdf"
    else:
        r = (await db.execute(select(VgpRapport).where(
            VgpRapport.id == rid, VgpRapport.parc == parc))).scalar_one_or_none()
        if not r:
            raise HTTPException(404, "rapport inconnu")
        chemin = r.fichier
        nom = f"VGP_{parc}_{r.date_vgp.isoformat() if r.date_vgp else rid}.pdf"
    if not chemin or not Path(chemin).exists():
        raise HTTPException(404, "document non disponible")
    return FileResponse(chemin, media_type="application/pdf", filename=nom)


@router.get("/public/{parc}/document/{type}")
async def document_public(parc: str, type: str, db: AsyncSession = Depends(get_db)):
    """Compat : 'vgp' = dernier rapport ; 'notice' = notice d'utilisation."""
    v = (await db.execute(select(Vgp).where(Vgp.parc == parc))).scalar_one_or_none()
    if not v:
        raise HTTPException(404, "machine inconnue")
    chemin = v.fichier_vgp if type == "vgp" else v.fichier_notice
    if not chemin or not Path(chemin).exists():
        raise HTTPException(404, "document non disponible")
    nom = f"{'VGP' if type == 'vgp' else 'Notice'}_{parc}.pdf"
    return FileResponse(chemin, media_type="application/pdf", filename=nom)
