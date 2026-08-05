"""Module VGP — registre, historique des contrôles, levées d'anomalie et
contrats de location.

ACCÈS — DEUX NATURES D'INFORMATION, DEUX RÉGIMES
  Le QR code COMPLÈTE les documents papier présents dans la machine ; il ne
  s'y substitue pas. Le loueur reste tenu de fournir le dernier rapport de
  VGP, la notice d'instruction, le certificat de conformité et le carnet de
  maintenance (code du travail, art. L4741-1).

  L'information de SÉCURITÉ — VGP à jour ou non, échéance — doit rester
  accessible à quiconque monte sur la machine : c'est l'objet même du
  dispositif. L'information COMMERCIALE — contrat, client, chantier,
  historique détaillé — n'a pas à être exposée à un tiers.

  • scan sans code                 : statut VGP, échéance, conformité
  • scan + code du contrat         : + contrat, historique, documents
  • scan + code de service AGENCE  : + historique et documents, toutes machines
  • scan + code de service ATELIER : + rapports en attente de traitement
  • interne (compte authentifié)   : tout

  Le QR contient un JETON OPAQUE et non le n° de parc : celui-ci étant
  séquentiel, l'exposer permettrait de parcourir tout le parc en incrémentant
  l'URL. Le jeton est tiré au hasard, il n'existe pas de « suivant ».

PUBLICATION
  Un rapport déposé entre dans l'historique interne mais n'est pas visible
  au scan tant qu'un agent d'atelier ne l'a pas publié. Objectif métier :
  le client ne doit pas découvrir une anomalie avant que l'atelier et le
  service commercial aient statué sur le rapatriement de la machine.
  Un rapport SANS anomalie est publié automatiquement (voir la constante
  PUBLICATION_AUTO_SI_CONFORME) ; un rapport AVEC anomalie ne l'est jamais,
  quelle que soit sa gravité.

LEVÉE D'ANOMALIE
  Acte nominatif par lequel l'atelier déclare la réserve corrigée après
  réparation. Elle ne supprime rien : le rapport en anomalie reste dans
  l'historique, la levée s'y ajoute. C'est ce qui donne au registre sa
  valeur en cas de contrôle.
"""
import hashlib
import logging
import os
import re as _re
import secrets
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Request,
                     UploadFile)
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, require_role
from app.core.roles import Role
from app.db.session import get_db
from app.models.vgp import (Vgp, VgpAccesLog, VgpCodeAgent, VgpContrat,
                            VgpDemande, VgpDemandeLigne, VgpLevee,
                            VgpPrestataire, VgpRapport)

logger = logging.getLogger("vgp")

router = APIRouter(prefix="/vgp", tags=["vgp"])

DOCS_DIR = Path(os.environ.get("VGP_DOCS_DIR", "/code/vgp_docs"))
VALIDITE_JOURS = 182  # VGP semestrielle (nacelles/PEMP)

# Rôles habilités à PUBLIER un rapport et à LEVER une anomalie.
#
# Volontairement un ENSEMBLE et non un niveau hiérarchique : « chef
# d'atelier » n'est pas un échelon au-dessus d'« exploitant », c'est une
# fonction différente. La levée d'une réserve engage l'entreprise en cas de
# contrôle ou d'accident ; elle ne doit pas être ouverte à tous ceux qui
# planifient des tournées.
#
# ⚠ Tant qu'aucun rôle CHEF_ATELIER n'existe, EXPLOITANT est conservé pour
#   que la fonction reste utilisable. Dès que le rôle est créé (voir le
#   roles.py fourni), retirer Role.EXPLOITANT de cet ensemble.
_ROLES_ATELIER = {
    getattr(Role, "CHEF_ATELIER", None),
    Role.ADMIN,
    Role.EXPLOITANT,   # ← à retirer une fois CHEF_ATELIER en place
}
_ROLES_ATELIER = {r for r in _ROLES_ATELIER if r is not None}
_VALEURS_ATELIER = {getattr(r, "value", str(r)) for r in _ROLES_ATELIER}

# Publication automatique des rapports SANS anomalie.
# Sur un parc de plusieurs centaines de machines, exiger une validation
# manuelle pour chaque contrôle conforme reviendrait à ne plus rien publier.
# Mettre à False pour exiger une validation de TOUS les rapports.
PUBLICATION_AUTO_SI_CONFORME = True

# Code d'accès locataire : alphabet sans caractères ambigus (ni 0/O, ni 1/I/L)
# car le code est destiné à être lu sur un contrat papier.
_ALPHABET_CODE = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LONGUEUR = 8

# Limitation du tâtonnement sur les codes de contrat
MAX_TENTATIVES = 10
FENETRE_TENTATIVES_MIN = 15

# Pièces du dossier machine. Le carnet de maintenance figure parmi les
# documents exigibles par le locataire à la mise à disposition ; la
# photographie permet de confirmer qu'on consulte la bonne machine.
TYPES_DOCUMENT = ("vgp", "notice", "fiche_technique", "carnet", "photo")
EXTENSIONS_PHOTO = (".jpg", ".jpeg", ".png", ".webp")

# Jeton figurant dans le QR code (identifiant opaque de la machine)
JETON_LONGUEUR = 12

# Anticipation des VGP arrivant à échéance
PREAVIS_JOURS = 30


# ═══════════════════ ANALYSE DU PDF (multi-organismes) ═══════════════════
# Formats variables selon l'organisme (CADET, AVGP, Apave, Dekra, Veritas…) :
# extraction best-effort par mots-clés + regex, validée sur rapports réels.

def _detecter_organisme(t: str) -> str | None:
    for org in ("CADET", "AVGP", "APAVE", "DEKRA", "VERITAS", "SOCOTEC", "QUALICONSULT"):
        if org in t.upper():
            return org
    return None


_MOTS_LABEL = {"marque", "type", "n°", "no", "n", "de", "fabrication", "code", "entreprise",
               "année", "annee", "marquage", "ce", "oui", "non", "série", "serie"}


def _candidats_serie(tokens: list[str], parc: str) -> list[str]:
    """Tokens ressemblant à un n° de série/fabrication (≥6 chars, ≥1 chiffre,
    pas une année, pas le n° de parc, pas un libellé)."""
    out = []
    for tok in tokens:
        tk = tok.strip(":").strip()
        if tk.lower() in _MOTS_LABEL:
            continue
        if not _re.fullmatch(r"[A-Z0-9\-]{6,25}", tk, _re.I):
            continue
        if not _re.search(r"\d", tk):
            continue
        if _re.fullmatch(r"(19|20)\d{2}", tk):
            continue
        if parc and tk == parc:
            continue
        out.append(tk)
    return out


def _analyser_pdf_vgp(chemin: Path, parc_attendu: str) -> dict:
    try:
        import pdfplumber
        with pdfplumber.open(str(chemin)) as pdf:
            texte = "\n".join((p.extract_text() or "") for p in pdf.pages)
    except Exception as e:
        return {"lecture_ok": False, "erreur": f"PDF illisible : {e}"}

    t = texte or ""
    tl = t.lower()
    lignes = t.splitlines()
    organisme = _detecter_organisme(t)

    # 1. Date de vérification — privilégier le contexte "vérification/visite",
    # exclure les dates futures (prochaine vérification).
    dates = []
    for m in _re.finditer(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b", t):
        try:
            d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            continue
        if d > date.today():
            continue
        ctx = tl[max(0, m.start() - 60):m.start()]
        if _re.search(r"prochaine", ctx):
            continue
        score = 2 if _re.search(r"v[ée]rification|visite|effectu|intervention|contr[ôo]le", ctx) else 1
        dates.append((score, d))
    date_detectee = max(dates, key=lambda x: (x[0], x[1]))[1].isoformat() if dates else None

    # 2. N° de parc — libellés variables + tableau CADET éclaté
    parc_detecte = None
    m_parc = _re.search(
        r"(?:n[°o]\s*(?:de\s*)?parc|code\s*(?:entreprise|parc|interne|client))"
        r"\s*[:\-]?\s*\n?\s*([A-Z0-9\-]{3,15})\b", t, _re.I)
    if m_parc:
        parc_detecte = m_parc.group(1).strip()
    else:
        m_parc = _re.search(r"Code\s*\n\s*([A-Z0-9\-]{3,15})\b[^\n]*\n\s*entreprise", t, _re.I)
        if m_parc:
            parc_detecte = m_parc.group(1).strip()
    parc_conforme = bool(parc_attendu) and bool(
        _re.search(rf"\b{_re.escape(parc_attendu)}\b", t))
    parc_ref = parc_attendu or parc_detecte or ""

    # 3. N° de série / fabrication / châssis
    serie_detectee = None
    m_serie = _re.search(
        r"(?:n[°o]\s*(?:de\s*)?s[ée]rie|serial|n[°o]\s*ch[âa]ssis|n[°o]\s*(?:de\s*)?fabrication)"
        r"\s*[:\-]\s*([A-Z0-9\-]{4,25})", t, _re.I)
    if m_serie:
        serie_detectee = m_serie.group(1).strip()
    else:
        # Tableau CADET éclaté : "N° de" et "fabrication" sur des lignes
        # voisines, valeur coupée en 1 ou 2 fragments.
        for idx, ln in enumerate(lignes):
            if not _re.search(r"\bfabrication\b", ln, _re.I):
                continue
            fenetre = lignes[max(0, idx - 2):idx + 1]
            if not any(_re.search(r"n[°o]\s*de\b", l, _re.I) for l in fenetre):
                continue
            frag_apres = None
            m_ap = _re.search(r"\bfabrication\b\s+([A-Z0-9\-]{1,15})\b", ln, _re.I)
            if m_ap and m_ap.group(1).lower() not in _MOTS_LABEL:
                frag_apres = m_ap.group(1)
            cands = [c for c in _candidats_serie(" ".join(fenetre).split(), parc_ref)
                     if c != frag_apres]
            if cands:
                serie_detectee = max(cands, key=len) + (frag_apres or "")
            elif frag_apres:
                serie_detectee = frag_apres
            if serie_detectee:
                break

    # 4. Modèle
    modele_detecte = None
    _FIN_CHAMP = r"(?=\s+(?:Heures?|N[°o]|S[ée]rie|[ÉE]nergie|Marque|Ann[ée]e|Fabriqu)\b|\n|$)"
    for idx, ln in enumerate(lignes):
        m_mq = _re.search(r"\bMarque\s+(.+?)\s+Type\b(.*)$", ln)
        if not m_mq:
            continue
        marque = m_mq.group(1).strip()
        if marque.lower() in _MOTS_LABEL or len(marque) > 25:
            continue
        serset = {c for c in _candidats_serie(ln.split(), parc_ref) if len(c) >= 7}
        apres_type = [w for w in m_mq.group(2).split()
                      if w not in serset and w.lower() not in _MOTS_LABEL]
        part1, part2 = [], []
        if idx > 0 and _re.search(r"n[°o]\s*de\b", lignes[idx - 1], _re.I):
            av = _re.split(r"n[°o]\s*de\b", lignes[idx - 1], flags=_re.I)[0].split()
            sp = set(_candidats_serie(av, parc_ref))
            part1 = [w for w in av if w not in sp]
        if idx + 1 < len(lignes) and _re.search(r"\bfabrication\b", lignes[idx + 1], _re.I):
            av = _re.split(r"\bfabrication\b", lignes[idx + 1], flags=_re.I)[0].split()
            sp = set(_candidats_serie(av, parc_ref))
            part2 = [w for w in av if w not in sp]
        cand = " ".join([marque] + part1 + apres_type + part2).strip()
        if 2 <= len(cand) <= 60:
            modele_detecte = cand
            break
    if not modele_detecte:
        constructeur = None
        m_c = _re.search(r"Constructeur\s*[:\-]\s*([A-Z][A-Za-z0-9 \-]{1,25}?)" + _FIN_CHAMP, t)
        if m_c:
            constructeur = m_c.group(1).strip()
        for pattern in (
            r"(?:^|\n)[^\n]*?\bType\s*[:\-]\s*([A-Z0-9][A-Z0-9 \-/\.]{1,25}?)" + _FIN_CHAMP,
            r"(?:machine|engin|mat[ée]riel|équipement)\s*[:\-]\s*([A-Z][A-Za-z0-9][^\n]{2,50})",
        ):
            m = _re.search(pattern, t, _re.I)
            if m:
                cand = m.group(1).strip()
                interdits = ("appareil", "location", "utilisatrice", "vérification", "verification",
                             "société", "societe", "accès", "acces", "industrie", "cabinet",
                             "chef", "atelier", "hydraulique", "conservation", "présente", "presente")
                if any(x in cand.lower() for x in interdits):
                    continue
                if not _re.search(r"\d|[A-Z]{2,}", cand):
                    continue
                modele_detecte = cand[:60]
                break
        if modele_detecte and constructeur and constructeur.lower() not in modele_detecte.lower():
            modele_detecte = f"{constructeur} {modele_detecte}"[:60]

    # 5+6. Anomalie + observations — détection en 3 niveaux.
    anomalie = None
    observations = None

    # Niveau 1 — champ explicite "Présence d'anomalie : OUI/NON" (CADET…)
    m_ano = _re.search(r"pr[ée]sence\s+d'?anomalies?\s*[:\-]?\s*(OUI|NON|YES|NO)\b", t, _re.I)
    if m_ano:
        anomalie = "OUI" if m_ano.group(1).upper() in ("OUI", "YES") else "NON"

    # Niveau 2 — verdict de l'avis général (AVGP, Apave, Dekra, Veritas…)
    if anomalie is None:
        if _re.search(
            r"ne\s+permett(?:ant|ent)\s+pas\s+(?:au\s+chef\s+d'établissement\s+de\s+)?"
            r"(?:la\s+(?:re)?mise|de\s+mettre)\s+(?:à\s+(?:la\s+)?disposition|l'appareil)"
            r"|rapport\s+d[ée]favorable|mise\s+à\s+disposition\s+interdite", tl):
            anomalie = "OUI"
        elif _re.search(
            r"n'ont\s+pas\s+fait\s+appara[îi]tre\s+d'anomalie"
            r"|aucune\s+anomalie\s+(?:n'a\s+été\s+)?constat[ée]"
            r"|peut\s+être\s+(?:maintenu|remis)\s+en\s+service"
            r"|sans\s+observation", tl):
            anomalie = "NON"

    # Section "Récapitulatif des anomalies constatées" → items NN.NN = réserves
    m_recap = _re.search(
        r"r[ée]capitulatif\s+des\s+anomalies\s+constat[ée]es\s*\n(.*?)"
        r"(?=\n\s*(?:les\s+anomalies\s+constat[ée]es|avis\s+g[ée]n[ée]ral|l'inspecteur)|\Z)",
        t, _re.I | _re.S)
    if m_recap:
        bloc = m_recap.group(1)
        items = [_re.sub(r"\s+", " ", l).strip()
                 for l in bloc.splitlines()
                 if _re.match(r"\s*\d{2}\.\d{2}\s+\S", l)]
        if items:
            if anomalie is None:  # Niveau 3 — items présents = anomalies
                anomalie = "OUI"
            observations = " ; ".join(items)[:1000]
        elif anomalie is None and _re.search(r"n[ée]ant|aucune|sans\s+objet", bloc, _re.I):
            anomalie = "NON"

    # Fallback observations : champs "Observations/Remarques/Réserves"
    if observations is None:
        _STRUCT = _re.compile(
            r"^(rapport transmis|contribuons|liste|accr[ée]|l'examen|c'est au chef|avis\s*:|rappel)",
            _re.I)
        for m in _re.finditer(
                r"(?:observations?|remarques?|r[ée]serves?)\s*[:\-]?\s*\n(.{3,300}?)(?:\n|$)",
                t, _re.I):
            cand = _re.sub(r"\s+", " ", m.group(1)).strip()
            if cand and cand != "/" and not _STRUCT.match(cand):
                observations = cand[:500]
                break

    avertissements = []
    interdiction = bool(anomalie == "OUI" and _re.search(
        r"ne\s+permett(?:ant|ent)\s+pas\s+la\s+mise\s+à\s+disposition"
        r"|ne\s+permettant\s+pas\s+au\s+chef", tl))
    if interdiction:
        avertissements.append(
            "⛔ L'inspecteur INTERDIT la mise à disposition de la machine aux travailleurs.")
    if anomalie == "OUI":
        avertissements.append(
            "🔴 Le rapport signale une PRÉSENCE D'ANOMALIE — vérifier les réserves de l'inspecteur.")
    if not date_detectee:
        avertissements.append("Aucune date de vérification détectée — saisir manuellement.")
    if parc_attendu and not parc_conforme:
        avertissements.append(
            f"⚠ Le n° de parc {parc_attendu} n'apparaît PAS dans ce PDF"
            + (f" (parc détecté : {parc_detecte})" if parc_detecte else "")
            + " — vérifier que le document correspond bien à cette machine.")

    resultat = {
        "lecture_ok": True,
        "organisme": organisme,
        "date_detectee": date_detectee,
        "parc_attendu": parc_attendu,
        "parc_detecte": parc_detecte,
        "parc_conforme": parc_conforme,
        "serie_detectee": serie_detectee,
        "modele_detecte": modele_detecte,
        "observations": observations,
        "anomalie": anomalie,
        "interdiction_exploitation": interdiction,
        "avertissements": avertissements,
    }
    logger.info("Analyse VGP %s [%s] → parc=%s date=%s serie=%s modele=%r anomalie=%s",
                chemin.name, organisme or "?", parc_detecte or parc_attendu, date_detectee,
                serie_detectee, modele_detecte, anomalie)
    return resultat


# ═══════════════════════════ OUTILS INTERNES ═══════════════════════════

def _empreinte_fichier(data: bytes) -> str:
    """SHA-256 du fichier — identité exacte du rapport pour la déduplication."""
    return hashlib.sha256(data).hexdigest()


def _meme_rapport(r: VgpRapport, empreinte: str, d: date | None, obs: str | None) -> bool:
    """Doublon si même fichier, ou — pour les rapports antérieurs à
    l'empreinte — même date ET mêmes observations."""
    if r.empreinte and r.empreinte == empreinte:
        return True
    return bool(r.date_vgp and d and r.date_vgp == d
                and (r.observations or "") == (obs or ""))


def _exiger_atelier(user) -> str:
    """Vérifie l'habilitation atelier et renvoie le nom de l'agent.

    Le contrôle porte sur l'appartenance à un ensemble de rôles, et non sur
    un niveau hiérarchique : c'est ce qui permet de réserver la levée à
    l'atelier sans l'ouvrir à toute la chaîne d'exploitation.
    """
    role = getattr(user, "role", None)
    valeur = getattr(role, "value", None) or str(role or "")
    if valeur not in _VALEURS_ATELIER:
        raise HTTPException(
            403, "Seul un agent d'atelier habilité peut publier un rapport "
                 "ou lever une anomalie.")
    return _nom_agent(user)


def _nom_agent(user) -> str:
    """Libellé nominatif de l'agent, quel que soit le modèle User."""
    for attr in ("nom_complet", "full_name", "nom", "name", "username"):
        v = getattr(user, attr, None)
        if v:
            return str(v)[:120]
    return str(getattr(user, "email", "inconnu"))[:120]


def _statut(date_vgp: date | None) -> dict:
    if not date_vgp:
        return {"echeance": None, "jours_restants": None, "statut": "INCONNUE"}
    echeance = date_vgp + timedelta(days=VALIDITE_JOURS)
    restants = (echeance - date.today()).days
    statut = "EXPIREE" if restants < 0 else ("BIENTOT" if restants <= 30 else "OK")
    return {"echeance": echeance.isoformat(), "jours_restants": restants, "statut": statut}


async def _generer_code_acces(db: AsyncSession) -> str:
    """Code aléatoire unique. `secrets` et non `random` : la valeur ne doit
    pas être prédictible à partir des codes déjà émis."""
    for _ in range(20):
        code = "".join(secrets.choice(_ALPHABET_CODE) for _ in range(CODE_LONGUEUR))
        existe = (await db.execute(
            select(VgpContrat.id).where(VgpContrat.code_acces == code))).first()
        if not existe:
            return code
    raise HTTPException(500, "génération du code d'accès impossible")


async def _levees_par_rapport(db: AsyncSession, parc: str) -> dict[int, list[dict]]:
    rows = (await db.execute(
        select(VgpLevee).where(VgpLevee.parc == parc)
        .order_by(VgpLevee.date_levee.desc(), VgpLevee.id.desc()))).scalars().all()
    out: dict[int, list[dict]] = {}
    for lv in rows:
        out.setdefault(lv.rapport_id, []).append({
            "id": lv.id,
            "date_levee": lv.date_levee.isoformat() if lv.date_levee else None,
            "auteur": lv.auteur,
            "description": lv.description,
            "a_fichier": bool(lv.fichier),
        })
    return out


def _etat_machine(rapports: list[VgpRapport], levees: dict[int, list[dict]]) -> dict:
    """État courant à partir d'une liste de rapports (déjà filtrée selon le
    niveau de visibilité) triée du plus récent au plus ancien.

    Une anomalie est ACTIVE si le rapport le plus récent la signale et
    qu'aucune levée n'a été enregistrée pour ce rapport.
    """
    if not rapports:
        return {"anomalie": None, "anomalie_active": False, "levee": None,
                **_statut(None)}
    dernier = rapports[0]
    lv = levees.get(dernier.id) or []
    anomalie_active = (dernier.anomalie == "OUI") and not lv
    return {
        "anomalie": dernier.anomalie,
        "anomalie_active": anomalie_active,
        "levee": lv[0] if lv else None,
        **_statut(dernier.date_vgp),
    }


async def _rapports(db: AsyncSession, parc: str, publies_seulement: bool) -> list[VgpRapport]:
    q = select(VgpRapport).where(VgpRapport.parc == parc)
    if publies_seulement:
        q = q.where(VgpRapport.publie.is_(True))
    q = q.order_by(VgpRapport.date_vgp.desc().nullslast(), VgpRapport.id.desc())
    return list((await db.execute(q)).scalars().all())


async def _compteurs(db: AsyncSession, parc: str) -> dict:
    total = (await db.execute(select(func.count(VgpRapport.id))
                              .where(VgpRapport.parc == parc))).scalar() or 0
    attente = (await db.execute(select(func.count(VgpRapport.id))
                                .where(VgpRapport.parc == parc,
                                       VgpRapport.publie.is_(False)))).scalar() or 0
    return {"nb_rapports": total, "nb_en_attente": attente}


async def _ajouter_rapport(db: AsyncSession, v: Vgp, a: dict, pdf_source: Path,
                           empreinte: str | None = None) -> VgpRapport:
    """Ajoute un rapport à l'historique (fichier horodaté, jamais d'écrasement)
    et met à jour le cache 'dernier état' de la machine si plus récent."""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = DOCS_DIR / f"{v.parc}_vgp_{stamp}.pdf"
    pdf_source.replace(dest)

    anomalie = a.get("anomalie")
    publie_auto = PUBLICATION_AUTO_SI_CONFORME and anomalie == "NON"

    r = VgpRapport(
        parc=v.parc,
        date_vgp=date.fromisoformat(a["date_detectee"]) if a.get("date_detectee") else None,
        numero_serie=a.get("serie_detectee"),
        observations=(a.get("observations") or "")[:1000] or None,
        anomalie=anomalie,
        organisme=a.get("organisme"),
        fichier=str(dest),
        empreinte=empreinte,
        publie=publie_auto,
        publie_par="publication automatique (rapport conforme)" if publie_auto else None,
        publie_le=datetime.now(timezone.utc) if publie_auto else None,
    )
    db.add(r)

    # Cache machine (affichage interne) — mis à jour si rapport plus récent
    if r.date_vgp and (not v.date_vgp or r.date_vgp >= v.date_vgp):
        v.date_vgp = r.date_vgp
        v.fichier_vgp = str(dest)
        if r.numero_serie:
            v.numero_serie = r.numero_serie
        if r.observations:
            v.observations = r.observations
        v.anomalie = r.anomalie
    if a.get("modele_detecte") and (
            not v.machine_modele
            or (r.date_vgp and (not v.date_vgp or r.date_vgp >= v.date_vgp))):
        v.machine_modele = a["modele_detecte"][:120]
    return r


async def _doublon_existant(db: AsyncSession, parc: str, empreinte: str,
                            d: date | None, obs: str | None) -> bool:
    rapports = (await db.execute(
        select(VgpRapport).where(VgpRapport.parc == parc))).scalars().all()
    return any(_meme_rapport(r, empreinte, d, obs) for r in rapports)


def _serialize(v: Vgp, compteurs: dict, etat: dict) -> dict:
    return {
        "parc": v.parc,
        # Sert à générer le QR côté interface ; jamais exposé publiquement.
        "jeton_public": v.jeton_public,
        "machine_modele": v.machine_modele,
        "date_vgp": v.date_vgp.isoformat() if v.date_vgp else None,
        "numero_serie": v.numero_serie,
        "observations": v.observations,
        "a_fichier_vgp": bool(v.fichier_vgp),
        "a_fichier_notice": bool(v.fichier_notice),
        "a_fichier_fiche_technique": bool(v.fichier_fiche_technique),
        "a_fichier_carnet": bool(v.fichier_carnet),
        "a_photo": bool(v.fichier_photo),
        **compteurs,
        **etat,
    }


# ═══════════════════════ GESTION (authentifiée) ═══════════════════════

@router.get("/machines", dependencies=[Depends(require_role(Role.LECTURE))])
async def liste_machines(db: AsyncSession = Depends(get_db)):
    """Registre interne — tous les rapports, publiés ou non."""
    rows = (await db.execute(select(Vgp).order_by(Vgp.parc))).scalars().all()
    out = []
    for v in rows:
        raps = await _rapports(db, v.parc, publies_seulement=False)
        levees = await _levees_par_rapport(db, v.parc)
        out.append(_serialize(v, await _compteurs(db, v.parc), _etat_machine(raps, levees)))
    return out


@router.get("/machines/{parc}/detail", dependencies=[Depends(require_role(Role.LECTURE))])
async def detail_machine(parc: str, db: AsyncSession = Depends(get_db)):
    """Vue interne complète : rapports (publiés ou non), levées, contrats."""
    v = (await db.execute(select(Vgp).where(Vgp.parc == parc))).scalar_one_or_none()
    if not v:
        raise HTTPException(404, "machine inconnue au registre VGP")
    raps = await _rapports(db, parc, publies_seulement=False)
    levees = await _levees_par_rapport(db, parc)
    contrats = (await db.execute(
        select(VgpContrat).where(VgpContrat.parc == parc)
        .order_by(VgpContrat.date_debut.desc()))).scalars().all()

    out = _serialize(v, await _compteurs(db, parc), _etat_machine(raps, levees))
    out["rapports"] = [{
        "id": r.id,
        "date_vgp": r.date_vgp.isoformat() if r.date_vgp else None,
        "organisme": r.organisme,
        "numero_serie": r.numero_serie,
        "observations": r.observations,
        "anomalie": r.anomalie,
        "publie": r.publie,
        "publie_par": r.publie_par,
        "publie_le": r.publie_le.isoformat() if r.publie_le else None,
        "a_fichier": bool(r.fichier),
        "levees": levees.get(r.id, []),
    } for r in raps]
    out["contrats"] = [{
        "id": c.id,
        "numero_contrat": c.numero_contrat,
        "client_nom": c.client_nom,
        "chantier": c.chantier,
        "ville": c.ville,
        "date_debut": c.date_debut.isoformat() if c.date_debut else None,
        "date_fin": c.date_fin.isoformat() if c.date_fin else None,
        "code_acces": c.code_acces,
        "revoque": c.revoque,
        "actif": _contrat_actif(c),
    } for c in contrats]
    return out


@router.get("/rapports/en-attente", dependencies=[Depends(require_role(Role.LECTURE))])
async def rapports_en_attente(db: AsyncSession = Depends(get_db)):
    """File de traitement de l'atelier.

    Sert de garde-fou : un rapport oublié se voit à son ancienneté.
    """
    raps = (await db.execute(
        select(VgpRapport).where(VgpRapport.publie.is_(False))
        .order_by(VgpRapport.date_vgp.asc().nullsfirst(), VgpRapport.id.asc())
    )).scalars().all()

    aujourdhui = date.today()
    out = []
    for r in raps:
        v = (await db.execute(select(Vgp).where(Vgp.parc == r.parc))).scalar_one_or_none()
        anciennete = (aujourdhui - r.date_vgp).days if r.date_vgp else None
        out.append({
            "id": r.id,
            "parc": r.parc,
            "machine_modele": v.machine_modele if v else None,
            "date_vgp": r.date_vgp.isoformat() if r.date_vgp else None,
            "anciennete_jours": anciennete,
            "organisme": r.organisme,
            "anomalie": r.anomalie,
            "observations": r.observations,
            "levees": len((await _levees_par_rapport(db, r.parc)).get(r.id, [])),
        })
    return {"total": len(out), "rapports": out}


@router.post("/rapports/{rid}/publier")
async def publier_rapport(
    rid: int,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Rend un rapport visible au scan du QR code.

    Aucune règle automatique : la décision appartient à l'atelier, qui
    statue avec le service commercial sur le rapatriement éventuel de la
    machine avant que le client ne voie l'information.
    """
    agent = _exiger_atelier(user)
    r = (await db.execute(select(VgpRapport).where(VgpRapport.id == rid))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "rapport inconnu")
    if r.publie:
        return {"ok": True, "deja_publie": True, "publie_par": r.publie_par}

    r.publie = True
    r.publie_par = agent
    r.publie_le = datetime.now(timezone.utc)
    await db.commit()
    logger.info("Rapport %s (parc %s) publié par %s", rid, r.parc, r.publie_par)
    return {"ok": True, "deja_publie": False, "publie_par": r.publie_par,
            "publie_le": r.publie_le.isoformat()}


@router.post("/rapports/{rid}/levee")
async def lever_anomalie(
    rid: int,
    user: CurrentUser,
    description: str = Form(...),
    date_levee: str = Form(""),
    publier: bool = Form(True),
    justificatif: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
):
    """Levée d'anomalie — déclaration de correction après réparation.

    Ne supprime rien : le rapport en anomalie reste dans l'historique, la
    levée s'y ajoute. C'est cette double trace qui donne au registre sa
    valeur en cas de contrôle.

    `publier=True` (défaut) publie le rapport dans la foulée : une fois la
    réparation faite, il n'y a plus de raison de masquer l'information.
    """
    agent = _exiger_atelier(user)
    r = (await db.execute(select(VgpRapport).where(VgpRapport.id == rid))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "rapport inconnu")
    if r.anomalie != "OUI":
        raise HTTPException(422, "ce rapport ne signale aucune anomalie à lever")
    if not description.strip():
        raise HTTPException(422, "la description de l'intervention est obligatoire")

    try:
        d_levee = date.fromisoformat(date_levee) if date_levee else date.today()
    except ValueError:
        raise HTTPException(422, "date de levée invalide (format attendu AAAA-MM-JJ)")
    if r.date_vgp and d_levee < r.date_vgp:
        raise HTTPException(422, "la levée ne peut pas précéder le contrôle")
    if d_levee > date.today():
        raise HTTPException(422, "la levée ne peut pas être postérieure à aujourd'hui")

    chemin = None
    if justificatif is not None and justificatif.filename:
        DOCS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = Path(justificatif.filename).suffix.lower() or ".pdf"
        if ext not in (".pdf", ".jpg", ".jpeg", ".png"):
            raise HTTPException(422, "justificatif : PDF ou image uniquement")
        dest = DOCS_DIR / f"{r.parc}_levee_{stamp}{ext}"
        dest.write_bytes(await justificatif.read())
        chemin = str(dest)

    lv = VgpLevee(
        rapport_id=r.id,
        parc=r.parc,
        date_levee=d_levee,
        auteur=agent,
        auteur_id=getattr(user, "id", None),
        description=description.strip(),
        fichier=chemin,
    )
    db.add(lv)

    if publier and not r.publie:
        r.publie = True
        r.publie_par = agent
        r.publie_le = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(lv)
    logger.info("Levée %s sur rapport %s (parc %s) par %s", lv.id, r.id, r.parc, lv.auteur)
    return {"ok": True, "levee": {
        "id": lv.id, "date_levee": lv.date_levee.isoformat(),
        "auteur": lv.auteur, "description": lv.description,
        "a_fichier": bool(lv.fichier)},
        "rapport_publie": r.publie}


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
        v = Vgp(parc=parc, jeton_public=await _generer_jeton(db))
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
    raps = await _rapports(db, v.parc, publies_seulement=False)
    levees = await _levees_par_rapport(db, v.parc)
    return _serialize(v, await _compteurs(db, v.parc), _etat_machine(raps, levees))


@router.post("/import-pdfs", dependencies=[Depends(require_role(Role.EXPLOITANT))])
async def import_pdfs(
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Dépôt EN MASSE des rapports reçus des organismes de contrôle.

    Chaque PDF : lecture automatique → détection du parc → création de la
    machine si absente → ajout à l'historique. Un rapport conforme est
    publié automatiquement ; un rapport en anomalie reste en attente de
    décision de l'atelier.
    """
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    recap = []
    for f in files:
        contenu = await f.read()
        empreinte = _empreinte_fichier(contenu)
        tmp = DOCS_DIR / f"_tmp_{f.filename or 'doc.pdf'}"
        tmp.write_bytes(contenu)
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

        d_vgp = date.fromisoformat(a["date_detectee"]) if a.get("date_detectee") else None
        if await _doublon_existant(db, parc, empreinte, d_vgp, a.get("observations")):
            tmp.unlink(missing_ok=True)
            logger.info("Doublon ignoré : %s (parc %s)", f.filename, parc)
            recap.append({"fichier": f.filename, "statut": "DOUBLON", "parc": parc,
                          "date": a.get("date_detectee"),
                          "detail": "rapport identique déjà dans l'historique"})
            continue

        v = (await db.execute(select(Vgp).where(Vgp.parc == parc))).scalar_one_or_none()
        if not v:
            v = Vgp(parc=parc, jeton_public=await _generer_jeton(db))
            db.add(v)
            await db.flush()
        r = await _ajouter_rapport(db, v, a, tmp, empreinte)
        recap.append({"fichier": f.filename, "statut": "INSEREE", "parc": parc,
                      "organisme": a.get("organisme"),
                      "anomalie": a.get("anomalie"),
                      "date": a.get("date_detectee"),
                      "serie": a.get("serie_detectee"),
                      "modele": a.get("modele_detecte"),
                      "publie": r.publie,
                      "observations": bool(a.get("observations"))})
    await db.commit()

    inserees = sum(1 for r in recap if r["statut"] == "INSEREE")
    doublons = sum(1 for r in recap if r["statut"] == "DOUBLON")
    en_attente = sum(1 for r in recap if r["statut"] == "INSEREE" and not r.get("publie"))
    return {"total": len(recap), "inserees": inserees, "doublons": doublons,
            "en_attente": en_attente,
            "a_verifier": len(recap) - inserees - doublons, "details": recap}


@router.post("/machines/{parc}/document",
             dependencies=[Depends(require_role(Role.EXPLOITANT))])
async def upload_document(
    parc: str,
    type: str = "vgp",  # vgp | notice | fiche_technique
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    if type not in TYPES_DOCUMENT:
        raise HTTPException(422, f"type attendu : {', '.join(TYPES_DOCUMENT)}")
    v = (await db.execute(select(Vgp).where(Vgp.parc == parc))).scalar_one_or_none()
    if not v:
        raise HTTPException(404, "machine inconnue au registre VGP")
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    if type == "photo":
        ext = Path(file.filename or "").suffix.lower()
        if ext not in EXTENSIONS_PHOTO:
            raise HTTPException(
                422, f"photo : formats acceptés {', '.join(EXTENSIONS_PHOTO)}")
        dest = DOCS_DIR / f"{parc}_photo{ext}"
        dest.write_bytes(await file.read())
        v.fichier_photo = str(dest)
        await db.commit()
        return {"ok": True, "fichier": dest.name, "analyse": None}

    if type in ("notice", "fiche_technique", "carnet"):
        dest = DOCS_DIR / f"{parc}_{type}.pdf"
        dest.write_bytes(await file.read())
        if type == "notice":
            v.fichier_notice = str(dest)
        elif type == "carnet":
            v.fichier_carnet = str(dest)
        else:
            v.fichier_fiche_technique = str(dest)
        await db.commit()
        return {"ok": True, "fichier": dest.name, "analyse": None}

    # rapport VGP unitaire : analyse + ajout à l'historique (sauf doublon)
    contenu = await file.read()
    empreinte = _empreinte_fichier(contenu)
    tmp = DOCS_DIR / f"_tmp_{parc}.pdf"
    tmp.write_bytes(contenu)
    analyse = _analyser_pdf_vgp(tmp, parc)

    d_vgp = None
    if analyse.get("lecture_ok") and analyse.get("date_detectee"):
        d_vgp = date.fromisoformat(analyse["date_detectee"])
    if analyse.get("lecture_ok") and await _doublon_existant(
            db, parc, empreinte, d_vgp, analyse.get("observations")):
        tmp.unlink(missing_ok=True)
        logger.info("Doublon ignoré (upload unitaire) : parc %s", parc)
        return {"ok": True, "doublon": True, "analyse": analyse}

    r = await _ajouter_rapport(db, v, analyse, tmp, empreinte)
    await db.commit()
    return {"ok": True, "doublon": False, "analyse": analyse, "publie": r.publie}


# ═════════════════════ CONTRATS DE LOCATION ═════════════════════
# Données fournies par le service commercial. Chaque contrat porte un code
# d'accès aléatoire, valable pour CE contrat uniquement : à son terme, le
# locataire perd l'accès aux informations de la machine.

def _contrat_actif(c: VgpContrat, jour: date | None = None) -> bool:
    j = jour or date.today()
    if c.revoque:
        return False
    if c.date_debut and j < c.date_debut:
        return False
    if c.date_fin and j > c.date_fin:
        return False
    return True


@router.post("/contrats", dependencies=[Depends(require_role(Role.EXPLOITANT))])
async def creer_contrat(
    parc: str = Form(...),
    numero_contrat: str = Form(...),
    client_nom: str = Form(...),
    date_debut: str = Form(...),
    date_fin: str = Form(""),
    chantier: str = Form(""),
    ville: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    """Enregistre un contrat de location et génère son code d'accès."""
    parc = parc.strip()
    v = (await db.execute(select(Vgp).where(Vgp.parc == parc))).scalar_one_or_none()
    if not v:
        raise HTTPException(404, "machine inconnue au registre VGP")
    try:
        d_deb = date.fromisoformat(date_debut)
        d_fin = date.fromisoformat(date_fin) if date_fin else None
    except ValueError:
        raise HTTPException(422, "dates invalides (format attendu AAAA-MM-JJ)")
    if d_fin and d_fin < d_deb:
        raise HTTPException(422, "la date de fin précède la date de début")

    c = VgpContrat(
        parc=parc,
        numero_contrat=numero_contrat.strip(),
        client_nom=client_nom.strip(),
        chantier=chantier.strip() or None,
        ville=ville.strip() or None,
        date_debut=d_deb,
        date_fin=d_fin,
        code_acces=await _generer_code_acces(db),
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    logger.info("Contrat %s créé pour parc %s (client %s)", c.numero_contrat, parc, c.client_nom)
    return {"ok": True, "id": c.id, "code_acces": c.code_acces,
            "parc": c.parc, "numero_contrat": c.numero_contrat,
            "client_nom": c.client_nom,
            "date_debut": c.date_debut.isoformat(),
            "date_fin": c.date_fin.isoformat() if c.date_fin else None,
            "actif": _contrat_actif(c)}


@router.get("/contrats", dependencies=[Depends(require_role(Role.LECTURE))])
async def liste_contrats(parc: str = "", db: AsyncSession = Depends(get_db)):
    q = select(VgpContrat)
    if parc:
        q = q.where(VgpContrat.parc == parc.strip())
    rows = (await db.execute(q.order_by(VgpContrat.date_debut.desc()))).scalars().all()
    return [{
        "id": c.id, "parc": c.parc, "numero_contrat": c.numero_contrat,
        "client_nom": c.client_nom, "chantier": c.chantier, "ville": c.ville,
        "date_debut": c.date_debut.isoformat() if c.date_debut else None,
        "date_fin": c.date_fin.isoformat() if c.date_fin else None,
        "code_acces": c.code_acces, "revoque": c.revoque,
        "actif": _contrat_actif(c),
    } for c in rows]


@router.post("/contrats/{cid}/revoquer", dependencies=[Depends(require_role(Role.EXPLOITANT))])
async def revoquer_contrat(cid: int, db: AsyncSession = Depends(get_db)):
    """Coupe l'accès du locataire avant le terme du contrat, sans supprimer
    l'enregistrement (traçabilité)."""
    c = (await db.execute(select(VgpContrat).where(VgpContrat.id == cid))).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "contrat inconnu")
    c.revoque = True
    await db.commit()
    return {"ok": True, "id": c.id, "actif": False}


# ═════════════ CODES DE SERVICE (agents Accès Industrie) ═════════════
# Réservés à l'administration : ce sont des secrets partagés, valables sur
# l'ensemble du parc. Leur création et leur révocation sont donc plus
# sensibles que celles d'un code de contrat.

CODE_AGENT_LONGUEUR = 12


@router.post("/codes-agent", dependencies=[Depends(require_role(Role.ADMIN))])
async def creer_code_agent(
    libelle: str = Form(...),
    portee: str = Form("AGENCE"),
    db: AsyncSession = Depends(get_db),
):
    portee = portee.strip().upper()
    if portee not in ("AGENCE", "ATELIER"):
        raise HTTPException(422, "portée attendue : AGENCE ou ATELIER")
    if not libelle.strip():
        raise HTTPException(422, "libellé requis (ex. « Atelier Lieusaint »)")

    for _ in range(20):
        code = "".join(secrets.choice(_ALPHABET_CODE) for _ in range(CODE_AGENT_LONGUEUR))
        if not (await db.execute(select(VgpCodeAgent.id)
                                 .where(VgpCodeAgent.code == code))).first():
            break
    else:
        raise HTTPException(500, "génération du code impossible")

    ca = VgpCodeAgent(libelle=libelle.strip(), code=code, portee=portee, actif=True)
    db.add(ca)
    await db.commit()
    await db.refresh(ca)
    logger.info("Code de service créé : %s (%s)", ca.libelle, ca.portee)
    return {"ok": True, "id": ca.id, "libelle": ca.libelle,
            "code": ca.code, "portee": ca.portee, "actif": ca.actif}


@router.get("/codes-agent", dependencies=[Depends(require_role(Role.ADMIN))])
async def liste_codes_agent(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(VgpCodeAgent).order_by(VgpCodeAgent.id))).scalars().all()
    return [{"id": c.id, "libelle": c.libelle, "code": c.code,
             "portee": c.portee, "actif": c.actif} for c in rows]


@router.post("/codes-agent/{cid}/revoquer",
             dependencies=[Depends(require_role(Role.ADMIN))])
async def revoquer_code_agent(cid: int, db: AsyncSession = Depends(get_db)):
    ca = (await db.execute(select(VgpCodeAgent)
                           .where(VgpCodeAgent.id == cid))).scalar_one_or_none()
    if not ca:
        raise HTTPException(404, "code inconnu")
    ca.actif = False
    await db.commit()
    logger.info("Code de service révoqué : %s", ca.libelle)
    return {"ok": True, "id": ca.id, "actif": False}


# ═════════ BON DE COMMANDE : GÉNÉRATION PDF ET ENVOI ═════════
# Le PDF est produit avec reportlab (déjà utilisé pour les feuilles de
# route). L'envoi passe par SMTP, paramétré par variables d'environnement :
#   VGP_SMTP_HOTE, VGP_SMTP_PORT, VGP_SMTP_UTILISATEUR, VGP_SMTP_MDP,
#   VGP_SMTP_EXPEDITEUR, VGP_SMTP_COPIE (facultatif), VGP_SMTP_TLS
# Sans configuration SMTP, la validation aboutit quand même : le PDF est
# généré et reste téléchargeable pour un envoi manuel.


def _generer_pdf_demande(d, pr, lignes) -> str:
    """Bon de commande d'intervention VGP, au format A4."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer,
                                    Table, TableStyle)

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    chemin = DOCS_DIR / f"demande_{d.reference}.pdf"

    navy = colors.HexColor("#071730")
    orange = colors.HexColor("#E65100")
    gris = colors.HexColor("#5A6472")
    bord = colors.HexColor("#C9D2DE")

    st_titre = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=17,
                              textColor=navy, leading=21, spaceAfter=2)
    st_sous = ParagraphStyle("s", fontName="Helvetica", fontSize=10,
                             textColor=gris, leading=13, spaceAfter=10)
    st_h = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=11,
                          textColor=orange, leading=14, spaceBefore=12, spaceAfter=5)
    st_p = ParagraphStyle("p", fontName="Helvetica", fontSize=9.3,
                          textColor=colors.HexColor("#1B2430"), leading=13, spaceAfter=4)
    st_c = ParagraphStyle("c", fontName="Helvetica", fontSize=8.4,
                          textColor=colors.HexColor("#1B2430"), leading=11)
    st_cb = ParagraphStyle("cb", fontName="Helvetica-Bold", fontSize=8.4,
                           textColor=navy, leading=11)
    st_note = ParagraphStyle("n", fontName="Helvetica-Oblique", fontSize=8.2,
                             textColor=gris, leading=11)

    doc = SimpleDocTemplate(str(chemin), pagesize=A4,
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm,
                            title=f"Demande d'intervention VGP {d.reference}")
    F = []
    F.append(Paragraph("Demande d'intervention — Vérification Générale Périodique", st_titre))
    F.append(Paragraph(
        f"Référence <b>{d.reference}</b> · émise le "
        f"{date.today().strftime('%d/%m/%Y')} · Accès Industrie", st_sous))

    F.append(Paragraph("Destinataire", st_h))
    F.append(Paragraph(
        f"<b>{pr.nom if pr else '—'}</b><br/>{pr.email if pr else ''}"
        + (f"<br/>Réf. client : {pr.reference_client}"
           if pr and pr.reference_client else ""), st_p))

    F.append(Paragraph("Objet", st_h))
    sur_chantier = sum(1 for l in lignes if l.sur_chantier)
    F.append(Paragraph(
        f"Vérification générale périodique de <b>{len(lignes)} machine(s)</b> "
        f"dont <b>{sur_chantier}</b> sur chantier."
        + (f"<br/>Intervention souhaitée à partir du "
           f"<b>{d.date_souhaitee.strftime('%d/%m/%Y')}</b>."
           if d.date_souhaitee else ""), st_p))

    F.append(Paragraph("Machines concernées", st_h))
    donnees = [[Paragraph(x, st_cb) for x in
                ("N° de parc", "Modèle", "Échéance VGP", "Lieu d'intervention", "Situation")]]
    for l in lignes:
        donnees.append([
            Paragraph(f"<b>{l.parc}</b>", st_c),
            Paragraph(l.machine_modele or "—", st_c),
            Paragraph(l.date_echeance.strftime("%d/%m/%Y") if l.date_echeance else "—", st_c),
            Paragraph(f"{l.lieu or '—'}" + (f"<br/>{l.ville}" if l.ville else ""), st_c),
            Paragraph("Sur chantier" if l.sur_chantier else "Dépôt agence", st_c),
        ])
    t = Table(donnees, colWidths=[24 * mm, 40 * mm, 24 * mm, 56 * mm, 30 * mm], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, bord),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F4F8")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    F.append(t)

    if d.commentaire:
        F.append(Paragraph("Précisions", st_h))
        F.append(Paragraph(d.commentaire.replace("\n", "<br/>"), st_p))

    F.append(Paragraph("Conditions", st_h))
    F.append(Paragraph(
        "Vérification réalisée conformément à l'arrêté du 1er mars 2004 relatif "
        "aux vérifications des appareils et accessoires de levage. Le rapport "
        "est attendu au format PDF, mentionnant le n° de parc de chaque machine.", st_p))
    F.append(Paragraph(
        "Pour les machines situées sur chantier, la prise de rendez-vous est à "
        "convenir avec l'agence : l'accès au site et la disponibilité de "
        "l'appareil doivent être organisés avec l'entreprise utilisatrice.", st_p))

    F.append(Spacer(1, 10))
    F.append(Paragraph(
        f"Demande établie par {d.cree_par or '—'}"
        + (f", validée par {d.valide_par}" if d.valide_par else "")
        + f" · Accès Industrie — Agence Paris Sud.", st_note))
    doc.build(F)
    return str(chemin)


def _envoyer_demande(d, pr, chemin_pdf: str, nb_machines: int) -> None:
    """Envoi du bon de commande par courriel, pièce jointe incluse.

    Lève une exception en cas d'échec : l'appelant consigne l'erreur sans
    perdre la validation.
    """
    import smtplib
    from email.message import EmailMessage

    hote = os.environ.get("VGP_SMTP_HOTE", "").strip()
    if not hote:
        raise RuntimeError(
            "SMTP non configuré (VGP_SMTP_HOTE) — bon de commande généré, "
            "à envoyer manuellement")

    port = int(os.environ.get("VGP_SMTP_PORT", "587"))
    utilisateur = os.environ.get("VGP_SMTP_UTILISATEUR", "").strip()
    mdp = os.environ.get("VGP_SMTP_MDP", "")
    expediteur = os.environ.get("VGP_SMTP_EXPEDITEUR", utilisateur).strip()
    copie = os.environ.get("VGP_SMTP_COPIE", "").strip()
    tls = os.environ.get("VGP_SMTP_TLS", "1") != "0"

    msg = EmailMessage()
    msg["Subject"] = f"Demande d'intervention VGP — {d.reference} — {nb_machines} machine(s)"
    msg["From"] = expediteur
    msg["To"] = pr.email
    if copie:
        msg["Cc"] = copie
    msg.set_content(
        f"Bonjour,\n\n"
        f"Veuillez trouver ci-joint notre demande d'intervention {d.reference} "
        f"portant sur {nb_machines} machine(s).\n"
        + (f"Intervention souhaitée à partir du "
           f"{d.date_souhaitee.strftime('%d/%m/%Y')}.\n" if d.date_souhaitee else "")
        + "\nCertaines machines peuvent se trouver sur chantier : le détail des "
          "lieux d'intervention figure dans le document joint.\n\n"
          "Nous restons à votre disposition pour convenir des modalités.\n\n"
          "Cordialement,\n"
          "Accès Industrie — Agence Paris Sud\n")

    with open(chemin_pdf, "rb") as f:
        msg.add_attachment(f.read(), maintype="application", subtype="pdf",
                           filename=f"{d.reference}.pdf")

    with smtplib.SMTP(hote, port, timeout=20) as smtp:
        if tls:
            smtp.starttls()
        if utilisateur:
            smtp.login(utilisateur, mdp)
        smtp.send_message(msg)
    logger.info("Demande %s envoyée à %s", d.reference, pr.email)


# ═══════════ ÉCHÉANCES VGP ET DEMANDES D'INTERVENTION ═══════════
# Une machine partie en location peut arriver à échéance sans que personne
# ne s'en aperçoive : elle n'est plus sous les yeux de l'atelier. Le système
# repère les échéances à 30 jours et prépare la demande ; le chef d'atelier
# choisit le prestataire et valide. Aucune émission automatique : un bon de
# commande engage financièrement l'entreprise.


@router.get("/echeances", dependencies=[Depends(require_role(Role.LECTURE))])
async def echeances(jours: int = PREAVIS_JOURS, db: AsyncSession = Depends(get_db)):
    """Machines dont la VGP arrive à échéance dans les `jours` prochains,
    ou déjà expirée.

    Indique pour chacune si elle se trouve sur chantier : le contrôle devra
    alors être organisé sur place, ce qui change le délai et le prestataire
    à solliciter.
    """
    machines = (await db.execute(select(Vgp).order_by(Vgp.parc))).scalars().all()
    deja_demande = {
        l.parc for l in (await db.execute(
            select(VgpDemandeLigne).join(
                VgpDemande, VgpDemande.id == VgpDemandeLigne.demande_id)
            .where(VgpDemande.statut.in_(("BROUILLON", "VALIDEE", "ENVOYEE")))
        )).scalars().all()
    }

    out = []
    for v in machines:
        raps = await _rapports(db, v.parc, publies_seulement=False)
        if not raps or not raps[0].date_vgp:
            continue
        st = _statut(raps[0].date_vgp)
        if st["jours_restants"] is None or st["jours_restants"] > jours:
            continue
        contrat = await _contrat_en_cours(db, v.parc)
        out.append({
            "parc": v.parc,
            "machine_modele": v.machine_modele,
            "date_vgp": raps[0].date_vgp.isoformat(),
            "echeance": st["echeance"],
            "jours_restants": st["jours_restants"],
            "statut": st["statut"],
            "sur_chantier": bool(contrat),
            "lieu": (contrat.chantier if contrat else "Dépôt agence"),
            "ville": (contrat.ville if contrat else None),
            "client": (contrat.client_nom if contrat else None),
            "numero_contrat": (contrat.numero_contrat if contrat else None),
            "fin_location": (contrat.date_fin.isoformat()
                             if contrat and contrat.date_fin else None),
            "demande_en_cours": v.parc in deja_demande,
        })
    out.sort(key=lambda x: x["jours_restants"])
    return {"preavis_jours": jours, "total": len(out),
            "expirees": sum(1 for x in out if x["jours_restants"] < 0),
            "sur_chantier": sum(1 for x in out if x["sur_chantier"]),
            "machines": out}


@router.get("/prestataires", dependencies=[Depends(require_role(Role.LECTURE))])
async def liste_prestataires(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(VgpPrestataire).order_by(VgpPrestataire.nom))).scalars().all()
    return [{"id": p.id, "nom": p.nom, "email": p.email,
             "telephone": p.telephone, "reference_client": p.reference_client,
             "actif": p.actif} for p in rows]


@router.post("/prestataires", dependencies=[Depends(require_role(Role.EXPLOITANT))])
async def creer_prestataire(
    nom: str = Form(...),
    email: str = Form(...),
    telephone: str = Form(""),
    reference_client: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    if "@" not in email:
        raise HTTPException(422, "adresse de courriel invalide")
    pr = VgpPrestataire(nom=nom.strip(), email=email.strip().lower(),
                        telephone=telephone.strip() or None,
                        reference_client=reference_client.strip() or None)
    db.add(pr)
    await db.commit()
    await db.refresh(pr)
    return {"ok": True, "id": pr.id, "nom": pr.nom, "email": pr.email}


@router.post("/demandes")
async def creer_demande(
    user: CurrentUser,
    prestataire_id: int = Form(...),
    parcs: str = Form(...),            # n° de parc séparés par des virgules
    date_souhaitee: str = Form(""),
    commentaire: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    """Prépare une demande d'intervention (brouillon).

    Le chef d'atelier choisit les machines et le prestataire : le
    rattachement n'est pas automatique, car il dépend de la localisation du
    chantier et des disponibilités.
    """
    agent = _exiger_atelier(user)
    pr = (await db.execute(select(VgpPrestataire).where(
        VgpPrestataire.id == prestataire_id))).scalar_one_or_none()
    if not pr or not pr.actif:
        raise HTTPException(404, "prestataire inconnu ou inactif")

    liste = [p.strip() for p in parcs.split(",") if p.strip()]
    if not liste:
        raise HTTPException(422, "aucune machine sélectionnée")
    try:
        d_souhaitee = date.fromisoformat(date_souhaitee) if date_souhaitee else None
    except ValueError:
        raise HTTPException(422, "date souhaitée invalide (AAAA-MM-JJ)")

    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    dem = VgpDemande(
        reference=f"VGP-{stamp}",
        prestataire_id=pr.id,
        statut="BROUILLON",
        cree_par=agent,
        date_souhaitee=d_souhaitee,
        commentaire=commentaire.strip() or None,
    )
    db.add(dem)
    await db.flush()

    lignes = []
    for parc in liste:
        v = (await db.execute(select(Vgp).where(Vgp.parc == parc))).scalar_one_or_none()
        if not v:
            continue
        raps = await _rapports(db, parc, publies_seulement=False)
        ech = _statut(raps[0].date_vgp)["echeance"] if raps and raps[0].date_vgp else None
        contrat = await _contrat_en_cours(db, parc)
        lg = VgpDemandeLigne(
            demande_id=dem.id, parc=parc, machine_modele=v.machine_modele,
            date_echeance=date.fromisoformat(ech) if ech else None,
            lieu=(contrat.chantier if contrat else "Dépôt agence"),
            ville=(contrat.ville if contrat else None),
            sur_chantier=bool(contrat),
            numero_contrat=(contrat.numero_contrat if contrat else None),
        )
        db.add(lg)
        lignes.append(lg)

    if not lignes:
        raise HTTPException(422, "aucune machine valide dans la sélection")
    await db.commit()
    await db.refresh(dem)
    logger.info("Demande VGP %s créée par %s (%s machines, prestataire %s)",
                dem.reference, agent, len(lignes), pr.nom)
    return {"ok": True, "id": dem.id, "reference": dem.reference,
            "statut": dem.statut, "nb_machines": len(lignes),
            "prestataire": pr.nom}


@router.get("/demandes", dependencies=[Depends(require_role(Role.LECTURE))])
async def liste_demandes(statut: str = "", db: AsyncSession = Depends(get_db)):
    q = select(VgpDemande)
    if statut:
        q = q.where(VgpDemande.statut == statut.strip().upper())
    rows = (await db.execute(q.order_by(VgpDemande.id.desc()))).scalars().all()
    out = []
    for d in rows:
        pr = (await db.execute(select(VgpPrestataire).where(
            VgpPrestataire.id == d.prestataire_id))).scalar_one_or_none()
        lignes = (await db.execute(select(VgpDemandeLigne).where(
            VgpDemandeLigne.demande_id == d.id))).scalars().all()
        out.append({
            "id": d.id, "reference": d.reference, "statut": d.statut,
            "prestataire": pr.nom if pr else None,
            "prestataire_email": pr.email if pr else None,
            "cree_par": d.cree_par, "valide_par": d.valide_par,
            "valide_le": d.valide_le.isoformat() if d.valide_le else None,
            "envoye_le": d.envoye_le.isoformat() if d.envoye_le else None,
            "erreur_envoi": d.erreur_envoi,
            "date_souhaitee": d.date_souhaitee.isoformat() if d.date_souhaitee else None,
            "commentaire": d.commentaire,
            "a_pdf": bool(d.fichier_pdf),
            "machines": [{
                "parc": l.parc, "machine_modele": l.machine_modele,
                "date_echeance": l.date_echeance.isoformat() if l.date_echeance else None,
                "lieu": l.lieu, "ville": l.ville,
                "sur_chantier": l.sur_chantier,
                "numero_contrat": l.numero_contrat,
            } for l in lignes],
        })
    return out


@router.post("/demandes/{did}/valider")
async def valider_demande(
    did: int,
    user: CurrentUser,
    envoyer: bool = Form(True),
    db: AsyncSession = Depends(get_db),
):
    """Validation par le chef d'atelier, génération du PDF et envoi.

    L'envoi du courriel peut échouer sans que la validation soit perdue :
    la demande reste VALIDEE avec l'erreur consignée, et le PDF reste
    téléchargeable pour un envoi manuel.
    """
    agent = _exiger_atelier(user)
    d = (await db.execute(select(VgpDemande).where(
        VgpDemande.id == did))).scalar_one_or_none()
    if not d:
        raise HTTPException(404, "demande inconnue")
    if d.statut == "ENVOYEE":
        return {"ok": True, "deja_envoyee": True, "reference": d.reference}
    if d.statut == "ANNULEE":
        raise HTTPException(422, "demande annulée")

    pr = (await db.execute(select(VgpPrestataire).where(
        VgpPrestataire.id == d.prestataire_id))).scalar_one_or_none()
    lignes = (await db.execute(select(VgpDemandeLigne).where(
        VgpDemandeLigne.demande_id == d.id))).scalars().all()

    d.statut = "VALIDEE"
    d.valide_par = agent
    d.valide_le = datetime.now(timezone.utc)

    chemin = _generer_pdf_demande(d, pr, lignes)
    d.fichier_pdf = chemin

    if envoyer and pr:
        try:
            _envoyer_demande(d, pr, chemin, len(lignes))
            d.statut = "ENVOYEE"
            d.envoye_le = datetime.now(timezone.utc)
            d.erreur_envoi = None
        except Exception as e:
            d.erreur_envoi = str(e)[:300]
            logger.warning("Envoi de la demande %s impossible : %s", d.reference, e)

    await db.commit()
    return {"ok": True, "reference": d.reference, "statut": d.statut,
            "valide_par": d.valide_par,
            "erreur_envoi": d.erreur_envoi,
            "a_pdf": bool(d.fichier_pdf)}


@router.post("/demandes/{did}/annuler")
async def annuler_demande(did: int, user: CurrentUser,
                          db: AsyncSession = Depends(get_db)):
    _exiger_atelier(user)
    d = (await db.execute(select(VgpDemande).where(
        VgpDemande.id == did))).scalar_one_or_none()
    if not d:
        raise HTTPException(404, "demande inconnue")
    if d.statut == "ENVOYEE":
        raise HTTPException(422, "demande déjà envoyée au prestataire")
    d.statut = "ANNULEE"
    await db.commit()
    return {"ok": True, "id": d.id, "statut": d.statut}


@router.get("/demandes/{did}/pdf", dependencies=[Depends(require_role(Role.LECTURE))])
async def pdf_demande(did: int, db: AsyncSession = Depends(get_db)):
    d = (await db.execute(select(VgpDemande).where(
        VgpDemande.id == did))).scalar_one_or_none()
    if not d or not d.fichier_pdf or not Path(d.fichier_pdf).exists():
        raise HTTPException(404, "document non disponible")
    return FileResponse(d.fichier_pdf, media_type="application/pdf",
                        filename=f"{d.reference}.pdf")


# ═════════════════════ ACCÈS PUBLIC (QR code) ═════════════════════
# Le QR est UNIQUE et permanent par machine. C'est le CONTENU affiché qui
# varie : sans code, seules les informations de sécurité sont visibles.

async def _resoudre_acces(db: AsyncSession, parc: str, code: str,
                          ip: str | None) -> dict:
    """Détermine le niveau d'accès associé à un code, avec limitation du
    tâtonnement.

    Chaque tentative est journalisée. Au-delà de MAX_TENTATIVES échecs en
    FENETRE_TENTATIVES_MIN minutes sur une même machine, l'accès est refusé :
    sans cela, un code de 8 caractères finirait par céder à l'énumération.

    Renvoie {"niveau", "contrat", "libelle"} où niveau vaut
    AUCUN | LOCATAIRE | AGENCE | ATELIER.
    """
    depuis = datetime.now(timezone.utc) - timedelta(minutes=FENETRE_TENTATIVES_MIN)
    echecs = (await db.execute(
        select(func.count(VgpAccesLog.id)).where(
            VgpAccesLog.parc == parc,
            VgpAccesLog.succes.is_(False),
            VgpAccesLog.created_at >= depuis))).scalar() or 0
    if echecs >= MAX_TENTATIVES:
        logger.warning("Trop de tentatives de code sur le parc %s (ip %s)", parc, ip)
        raise HTTPException(429, "trop de tentatives — réessayer dans quelques minutes")

    code = (code or "").strip().upper().replace(" ", "").replace("-", "")
    resultat = {"niveau": "AUCUN", "contrat": None, "libelle": None}

    # 1. Code de service (agents Accès Industrie) — vaut pour toute machine
    ca = (await db.execute(select(VgpCodeAgent).where(
        VgpCodeAgent.code == code, VgpCodeAgent.actif.is_(True)))).scalar_one_or_none()
    if ca:
        portee = ca.portee if ca.portee in ("AGENCE", "ATELIER") else "AGENCE"
        # Un agent voit aussi le contrat en cours sur la machine : c'est
        # l'information qu'il cherche en priorité sur le terrain.
        contrat = await _contrat_en_cours(db, parc)
        resultat = {"niveau": portee, "contrat": contrat, "libelle": ca.libelle}

    # 2. Code de contrat — propre à cette machine et à cette location
    if resultat["niveau"] == "AUCUN":
        c = (await db.execute(select(VgpContrat).where(
            VgpContrat.parc == parc,
            VgpContrat.code_acces == code))).scalar_one_or_none()
        if c and _contrat_actif(c):
            resultat = {"niveau": "LOCATAIRE", "contrat": c, "libelle": c.client_nom}

    succes = resultat["niveau"] != "AUCUN"
    contrat = resultat["contrat"]
    db.add(VgpAccesLog(parc=parc, code_tente=code[:16] or None,
                       ip=(ip or "")[:45] or None, succes=succes,
                       contrat_id=contrat.id if contrat else None,
                       niveau=resultat["niveau"]))
    await db.commit()
    return resultat


async def _machine_par_reference(db: AsyncSession, ref: str) -> Vgp | None:
    """Résout une machine depuis le QR (jeton opaque) ou depuis le n° de parc.

    Le n° de parc reste accepté pour les usages internes et les QR déjà
    imprimés ; les nouveaux QR portent le jeton.
    """
    ref = (ref or "").strip()
    if not ref:
        return None
    v = (await db.execute(select(Vgp).where(Vgp.jeton_public == ref))).scalar_one_or_none()
    if v:
        return v
    return (await db.execute(select(Vgp).where(Vgp.parc == ref))).scalar_one_or_none()


async def _generer_jeton(db: AsyncSession) -> str:
    for _ in range(20):
        j = "".join(secrets.choice(_ALPHABET_CODE) for _ in range(JETON_LONGUEUR))
        if not (await db.execute(select(Vgp.id).where(Vgp.jeton_public == j))).first():
            return j
    raise HTTPException(500, "génération du jeton impossible")


async def _contrat_en_cours(db: AsyncSession, parc: str) -> VgpContrat | None:
    """Contrat de location actif à ce jour sur la machine, s'il en existe un."""
    rows = (await db.execute(
        select(VgpContrat).where(VgpContrat.parc == parc)
        .order_by(VgpContrat.date_debut.desc()))).scalars().all()
    for c in rows:
        if _contrat_actif(c):
            return c
    return None


@router.get("/public/{ref}")
async def fiche_publique(
    ref: str,
    request: Request,
    code: str = "",
    db: AsyncSession = Depends(get_db),
):
    """Fiche machine au scan du QR code.

    SANS code — socle de sécurité : n° de parc, modèle, date de la dernière
    VGP publiée, échéance, conformité. C'est l'information dont a besoin
    toute personne qui monte sur la machine, et elle ne doit pas être
    conditionnée à la détention d'un code.

    AVEC code — s'y ajoutent le contrat, l'historique et les documents.

    Aucune donnée client n'est jamais exposée sans code.
    """
    v = await _machine_par_reference(db, ref)
    if not v:
        raise HTTPException(404, "machine inconnue")
    parc = v.parc

    ip = request.client.host if request.client else None
    acces = await _resoudre_acces(db, parc, code, ip) if code else {
        "niveau": "AUCUN", "contrat": None, "libelle": None}
    niveau = acces["niveau"]
    contrat = acces["contrat"]

    # Seul l'atelier voit les rapports non encore publiés.
    raps = await _rapports(db, parc, publies_seulement=(niveau != "ATELIER"))

    # ── Socle de sécurité, accessible sans code ──
    if niveau == "AUCUN":
        levees = await _levees_par_rapport(db, parc)
        etat = _etat_machine(raps, levees)
        return {
            "parc": v.parc,
            "machine_modele": v.machine_modele,
            "date_vgp": raps[0].date_vgp.isoformat() if raps and raps[0].date_vgp else None,
            # La photo aide à vérifier qu'on consulte bien la machine qu'on a
            # sous les yeux : c'est une information d'identification, pas une
            # donnée commerciale.
            "a_photo": bool(v.fichier_photo),
            "niveau": "PUBLIC",
            "code_valide": False,
            "code_requis": False,
            "rappel_documents": (
                "Les documents réglementaires (rapport de VGP, notice, "
                "certificat de conformité) doivent se trouver dans la machine. "
                "Cette fiche les complète, elle ne les remplace pas."),
            "statut": etat["statut"],
            "echeance": etat["echeance"],
            "jours_restants": etat["jours_restants"],
            "anomalie_active": etat["anomalie_active"],
        }
    levees = await _levees_par_rapport(db, parc)
    etat = _etat_machine(raps, levees)

    hist = [{
        "id": r.id,
        "date_vgp": r.date_vgp.isoformat() if r.date_vgp else None,
        "organisme": r.organisme,
        "numero_serie": r.numero_serie,
        "observations": r.observations,
        "anomalie": r.anomalie,
        "publie": r.publie,
        # Date de dépôt du document : distingue la date du contrôle de celle
        # de sa mise à disposition, écart parfois de plusieurs jours.
        "depose_le": r.created_at.date().isoformat() if r.created_at else None,
        "a_fichier": bool(r.fichier),
        "levees": levees.get(r.id, []),
    } for r in raps]

    dernier = raps[0] if raps else None
    out = {
        "parc": v.parc,
        "code_valide": True,
        "niveau": niveau,
        "acces_libelle": acces["libelle"],
        "machine_modele": v.machine_modele,
        "date_vgp": dernier.date_vgp.isoformat() if dernier and dernier.date_vgp else None,
        "numero_serie": dernier.numero_serie if dernier else None,
        "observations": dernier.observations if dernier else None,
        "a_fichier_vgp": bool(dernier and dernier.fichier),
        "a_fichier_notice": bool(v.fichier_notice),
        "a_fichier_fiche_technique": bool(v.fichier_fiche_technique),
        "a_fichier_carnet": bool(v.fichier_carnet),
        "a_photo": bool(v.fichier_photo),
        "nb_rapports": len(hist),
        "rapports": hist,
        **etat,
    }

    if not contrat:
        return out
    out["contrat"] = {
        "numero_contrat": contrat.numero_contrat,
        "client_nom": contrat.client_nom,
        "chantier": contrat.chantier,
        "ville": contrat.ville,
        "date_debut": contrat.date_debut.isoformat() if contrat.date_debut else None,
        "date_fin": contrat.date_fin.isoformat() if contrat.date_fin else None,
    }
    return out


@router.get("/public/{ref}/rapport/{rid}")
async def rapport_public(ref: str, rid: int, request: Request,
                         code: str = "", db: AsyncSession = Depends(get_db)):
    """Téléchargement d'un rapport — code de contrat obligatoire, et
    uniquement si le rapport est publié.

    Sans ce contrôle, une simple énumération des identifiants suffirait à
    récupérer les rapports de tout le parc.
    """
    v = await _machine_par_reference(db, ref)
    if not v:
        raise HTTPException(404, "document non disponible")
    parc = v.parc
    ip = request.client.host if request.client else None
    acces = await _resoudre_acces(db, parc, code, ip) if code else {"niveau": "AUCUN"}
    if acces["niveau"] == "AUCUN":
        raise HTTPException(404, "document non disponible")
    r = (await db.execute(select(VgpRapport).where(
        VgpRapport.id == rid, VgpRapport.parc == parc))).scalar_one_or_none()
    if not r or (not r.publie and acces["niveau"] != "ATELIER"):
        # Même réponse qu'un rapport inexistant : ne pas révéler l'existence
        # d'un rapport en attente de traitement.
        raise HTTPException(404, "document non disponible")
    if not r.fichier or not Path(r.fichier).exists():
        raise HTTPException(404, "document non disponible")
    nom = f"VGP_{parc}_{r.date_vgp.isoformat() if r.date_vgp else rid}.pdf"
    return FileResponse(r.fichier, media_type="application/pdf", filename=nom)


@router.get("/public/{ref}/document/{type}")
async def document_public(ref: str, type: str, request: Request,
                          code: str = "", db: AsyncSession = Depends(get_db)):
    """Dossier machine — code de contrat obligatoire.

    'vgp' = dernier rapport PUBLIÉ ; 'notice' et 'fiche_technique' = pièces
    permanentes du dossier.
    """
    if type not in TYPES_DOCUMENT:
        raise HTTPException(404, "document non disponible")
    v = await _machine_par_reference(db, ref)
    if not v:
        raise HTTPException(404, "machine inconnue")
    parc = v.parc
    ip = request.client.host if request.client else None
    acces = await _resoudre_acces(db, parc, code, ip) if code else {"niveau": "AUCUN"}
    # La photographie sert à identifier la machine devant laquelle on se
    # trouve : elle accompagne le socle de sécurité et ne demande pas de
    # code. Elle ne révèle rien qu'un regard sur l'engin ne montre déjà.
    if acces["niveau"] == "AUCUN" and type != "photo":
        raise HTTPException(404, "document non disponible")

    if type == "vgp":
        raps = await _rapports(db, parc,
                               publies_seulement=(acces["niveau"] != "ATELIER"))
        chemin = raps[0].fichier if raps else None
        libelle = "VGP"
    elif type == "notice":
        chemin, libelle = v.fichier_notice, "Notice"
    elif type == "carnet":
        chemin, libelle = v.fichier_carnet, "Carnet_maintenance"
    elif type == "photo":
        chemin, libelle = v.fichier_photo, "Photo"
    else:
        chemin, libelle = v.fichier_fiche_technique, "Fiche_technique"

    if not chemin or not Path(chemin).exists():
        raise HTTPException(404, "document non disponible")

    if type == "photo":
        ext = Path(chemin).suffix.lower()
        mime = {".png": "image/png", ".webp": "image/webp"}.get(ext, "image/jpeg")
        return FileResponse(chemin, media_type=mime)
    return FileResponse(chemin, media_type="application/pdf",
                        filename=f"{libelle}_{parc}.pdf")
