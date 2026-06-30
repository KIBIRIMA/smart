"""
Géocodage des adresses → coordonnées (lat, lng).

Stratégie en deux temps, pensée pour la fiabilité en démo :
  1. Tentative via l'API officielle adresse.data.gouv.fr (gratuite, sans clé, France)
  2. Repli sur une table de villes d'Île-de-France intégrée si le réseau échoue
     ou si l'adresse est trop imprécise (ex. "ZONE BADGEE ORLY").

Aucune dépendance externe : utilise urllib de la bibliothèque standard.
Le repli garantit qu'une mission obtient toujours des coordonnées exploitables.
"""
from __future__ import annotations
import json
import logging
import urllib.parse
import urllib.request

logger = logging.getLogger("geocode")

VILLES_IDF: dict[str, tuple[float, float]] = {
    "PARIS": (48.8566, 2.3522),
    "CHOISY LE ROI": (48.7686, 2.4189),
    "VILLEJUIF": (48.7919, 2.3636),
    "RUNGIS": (48.7489, 2.3503),
    "ORLY": (48.7233, 2.3925),
    "AEROPORT D ORLY": (48.7262, 2.3652),
    "MONTEREAU FAULT YONNE": (48.3847, 2.9486),
    "CRETEIL": (48.7900, 2.4556),
    "VITRY SUR SEINE": (48.7875, 2.3928),
    "IVRY SUR SEINE": (48.8139, 2.3877),
    "MAISONS ALFORT": (48.8045, 2.4374),
    "SAINT DENIS": (48.9362, 2.3574),
    "MONTREUIL": (48.8638, 2.4485),
    "NANTERRE": (48.8924, 2.2070),
    "VERSAILLES": (48.8044, 2.1232),
    "MASSY": (48.7309, 2.2731),
    "TORCY": (48.8503, 2.6494),
    "ANTONY": (48.7539, 2.2974),
    "CLICHY": (48.9044, 2.3064),
    "BOULOGNE BILLANCOURT": (48.8333, 2.2400),
    "MELUN": (48.5392, 2.6610),
    "EVRY": (48.6328, 2.4406),
    "LIEUSAINT": (48.6320, 2.4700),
}

_API = "https://api-adresse.data.gouv.fr/search/"


def _strip_accents(s: str) -> str:
    table = str.maketrans("ÀÂÄÉÈÊËÎÏÔÖÙÛÜÇàâäéèêëîïôöùûüç",
                          "AAAEEEEIIOOUUUCaaaeeeeiioouuuc")
    return s.translate(table)


def _norm_ville(ville: str) -> str:
    return _strip_accents((ville or "").strip().upper())


def _via_api(adresse: str, code_postal: str | None) -> tuple[float, float] | None:
    """Interroge l'API gouvernementale. Retourne None si échec ou réseau indisponible."""
    q = adresse.strip()
    if not q:
        return None
    params = {"q": q, "limit": 1}
    if code_postal:
        params["postcode"] = code_postal
    url = _API + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        features = data.get("features", [])
        if features:
            lng, lat = features[0]["geometry"]["coordinates"]
            return float(lat), float(lng)
    except Exception as exc:
        logger.warning("Géocodage API indisponible (%s) — repli ville", exc)
    return None


def geocode(adresse: str, ville: str, code_postal: str | None = None) -> tuple[float, float, str]:
    """
    Retourne (lat, lng, source).
    source ∈ {"api", "ville", "defaut"} pour tracer la qualité du géocodage.
    """
    full = ", ".join(p for p in [adresse, code_postal, ville] if p)
    coord = _via_api(full, code_postal)
    if coord:
        return coord[0], coord[1], "api"

    key = _norm_ville(ville)
    if key in VILLES_IDF:
        lat, lng = VILLES_IDF[key]
        return lat, lng, "ville"

    logger.warning("Ville inconnue '%s' — coordonnées par défaut IDF", ville)
    return 48.7500, 2.4000, "defaut"
