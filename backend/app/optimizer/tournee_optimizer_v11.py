# -*- coding: utf-8 -*-
# ================================================================
#  OPTIMISEUR DE TOURNÉES v10 — IDENTIFICATION + BIN-PACKING 2D
#
#  NOUVEAUTÉS v10 :
#  ✅ Identification machines bullet-proof (matching tolérant)
#     - Normalisation casse / espaces / parenthèses
#     - Fuzzy matching constructeur + numéro modèle
#     - Fallback intelligent par catégorie
#     - Log détaillé des machines non reconnues
#  ✅ Bin-packing 2D du plateau (2 rangées côte à côte)
#     - Plateau modélisé en 2D (longueur × largeur)
#     - Ciseaux étroits côte à côte (gain ~40% de longueur)
#     - Nacelles articulées en bout, flèche aérienne 2,5D
#     - Contrôle PTAC (19T porteur / 25T semi)
#  ✅ Construction des tournées avec contrainte chargement
#     - Une mission n'est ajoutée que si elle rentre vraiment
#     - Tri "First Fit Decreasing" optimisé
#     - Ordre de chargement = inverse de l'ordre de livraison (LIFO)
#  ✅ 2 types de camions : porteur 19T et semi 25T
#
#  HÉRITÉ DE v9 :
#  ✅ Grille tarifaire par zone géographique (6 zones)
#     Prix unique livraison/récup, identique pour toute machine
#     Zone déterminée par distance routière depuis Lieusaint
#  ✅ Estimateur commercial mis à jour (tarif zone × nb machines)
#  ✅ Calcul de rentabilité par mission (CA réel zone par zone)
#  ✅ Mode --grille pour afficher la grille tarifaire en console
#
#  HÉRITÉ DE v8 :
#  ✅ Journée 8h : 05h00 → 13h00
#  ✅ Multi-chauffeurs automatique (1 à N camions)
#  ✅ Machines inconnues : ajout automatique dans machines.json
#  ✅ PDF chauffeur avec mini-carte
#  ✅ PDF transport (responsable) avec tous les prix et KPI
#  ✅ Feuille de route = 1 page par chauffeur par jour
# ================================================================

import pandas as pd
import requests
import time, json, os, math
try:
    import folium
except ImportError:
    folium = None
from geopy.distance import geodesic
from collections import defaultdict

try:
    from ortools.constraint_solver import routing_enums_pb2
    from ortools.constraint_solver import pywrapcp
    ORTOOLS_AVAILABLE = True
except ImportError:
    ORTOOLS_AVAILABLE = False

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                     TableStyle, HRFlowable, PageBreak, KeepTogether)
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

# ────────────────────────────────────────────────────────────────
#  CONFIGURATION GLOBALE
# ────────────────────────────────────────────────────────────────
API_KEY            = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6ImNkZmMzNDEzYTYwNTQ4ZTBiZDZjZTFjZjYwNGMxZDlmIiwiaCI6Im11cm11cjY0In0="
VERSION_MOTEUR     = "v12.0-preanalyse-ffd-3rangees"
DEPOT_ADDRESS      = "Boulevard d'espagne, 91250 lieusaint, france"
DEPOT_NOM          = "Accès Industrie Paris Sud — Lieusaint"
DEPOT_TEL          = "01 XX XX XX XX"
GEOCODE_CACHE_FILE = "geocode_cache.json"
ROUTE_CACHE_FILE   = "route_cache.json"
MACHINES_FILE      = "machines.json"
UNKNOWN_LOG_FILE   = "machines_inconnues.json"

# ── Horaires journée 8h
HEURE_DEBUT_MIN  = 5 * 60     # 05h00
HEURE_FIN_MIN    = 13 * 60    # 13h00  ← corrigé v8
MAX_TRAVAIL_MIN  = HEURE_FIN_MIN - HEURE_DEBUT_MIN   # 480 min

# ── Plateau
PLATEAU_LONGUEUR_MAX_M = 12.5
PLATEAU_LARGEUR_MAX_M  = 2.55   # largeur utile standard camion
PLATEAU_POIDS_MAX_T    = 25.0   # PTAC charge utile semi (défaut)

# Types de camions disponibles dans la flotte (v10)
CAMIONS_FLOTTE = {
    "porteur_19t": {
        "type": "porteur",
        "longueur_m": 9.0,     # plateau porteur 9m
        "largeur_m":  2.50,
        "ptac_t":     19.0,    # charge utile
        "label":      "Porteur 19T",
    },
    "semi_25t": {
        "type": "semi",
        "longueur_m": 12.5,
        "largeur_m":  2.55,
        "ptac_t":     25.0,
        "label":      "Semi-remorque 25T",
    },
}
CAMION_DEFAUT = "semi_25t"

# ── Temps opérations terrain
TPS_SANGLE_MIN      = 0    # v8 : inclus dans tps_ch/tps_dech
TPS_ATTENTE_CLIENT  = 0    # v8 : inclus dans tps_ch/tps_dech
TPS_PAUSE_MIN       = 30     # pause réglementaire si > 4h conduite
SEUIL_PAUSE_MIN     = 240

# ── Optimisation
DETOUR_MAX_RECUP_KM  = 45.0   # détour normal sur le retour
RECUP_LOINTAINE_KM   = 40.0   # distance vol d'oiseau au-delà = "récup lointaine"
                               # → forcée en dernier arrêt du tour le plus proche
CLUSTER_RAYON_KM    = 20.0

# ── Financier
CONSO_L_100KM       = 33.0
PRIX_LITRE_EUR      = 1.85
COUT_HEURE_CHAUF    = 35.0
PRIX_LIVRAISON_DEF  = 180.0
PRIX_RECUP_DEF      = 120.0

# ────────────────────────────────────────────────────────────────
#  GRILLE TARIFAIRE PAR ZONE GÉOGRAPHIQUE (v9)
#  Le prix dépend uniquement de la distance routière depuis le dépôt
#  (Lieusaint). Tarif unique quelle que soit la machine transportée.
#
#  Une zone = une plage kilométrique + un prix. Aucun nom de commune
#  n'est nécessaire : seule la distance compte.
# ────────────────────────────────────────────────────────────────
GRILLE_TARIFS_ZONES = [
    # (zone, dist_min_km, dist_max_km, prix_eur)
    (1,  0.0,   15.0,  160.0),
    (2, 15.0,   20.0,  170.0),
    (3, 20.0,   28.0,  220.0),
    (4, 28.0,   38.0,  275.0),
    (5, 38.0,   55.0,  305.0),
    (6, 55.0,  999.0,  350.0),
]

def libelle_zone(zone_num):
    """Retourne un libellé court 'Zone N (X-Y km)' à partir du numéro de zone."""
    for z, dmin, dmax, _ in GRILLE_TARIFS_ZONES:
        if z == zone_num:
            if dmax >= 999:
                return f"Zone {z} ({dmin:.0f} km et plus)"
            return f"Zone {z} ({dmin:.0f}-{dmax:.0f} km)"
    return "Zone inconnue"

def prix_mission_par_zone(distance_km, default=PRIX_LIVRAISON_DEF):
    """
    Retourne (prix_eur, zone_num, libelle) selon la distance routière
    depuis le dépôt de Lieusaint.

    Le prix est unique pour livraison comme récupération, et identique
    quelle que soit la machine transportée.

    Si la distance est None ou invalide, retourne le prix par défaut.
    """
    if distance_km is None or distance_km < 0:
        return (default, 0, "Distance inconnue")
    for zone, dmin, dmax, prix in GRILLE_TARIFS_ZONES:
        if dmin <= distance_km < dmax:
            return (prix, zone, libelle_zone(zone))
    # Au-delà de la dernière borne, on applique la zone 6
    last = GRILLE_TARIFS_ZONES[-1]
    return (last[3], last[0], libelle_zone(last[0]))

def afficher_grille_tarifs():
    """Affiche la grille tarifaire en console (pour vérification)."""
    print()
    print("┌" + "─"*52 + "┐")
    print("│  GRILLE TARIFAIRE PAR ZONE — depuis Lieusaint     │")
    print("├" + "─"*52 + "┤")
    print("│  Zone │ Distance routière      │     Prix HT    │")
    print("├───────┼────────────────────────┼────────────────┤")
    for zone, dmin, dmax, prix in GRILLE_TARIFS_ZONES:
        if dmax >= 999:
            dist_txt = f"{dmin:>4.0f} km et au-delà   "
        else:
            dist_txt = f"{dmin:>4.0f} à {dmax:>4.0f} km        "
        print(f"│   {zone}   │ {dist_txt} │   {prix:>7.0f} €    │")
    print("└" + "─"*52 + "┘")
    print()

# ── Tarification commerciale (estimateur)
TARIF_BASE_EUR      = 80.0   # frais fixes par tournée
TARIF_KM_EUR        = 1.20   # €/km
TARIF_MACHINE_EUR   = 45.0   # €/machine supplémentaire
TARIF_URGENCE_MULT  = 1.30   # multiplicateur urgence

ORS_PAUSE_SEC = 1.6

TOUR_COLORS = {
    1:"blue", 2:"red", 3:"green", 4:"purple", 5:"orange",
    6:"darkred", 7:"cadetblue", 8:"darkgreen", 9:"beige",
    10:"lightblue", 11:"lightgreen", 12:"pink", 13:"darkpurple", 14:"gray",
}
CHAUFFEUR_COLORS = ["#1565C0","#B71C1C","#1B5E20","#4A148C","#E65100"]


# ────────────────────────────────────────────────────────────────
#  MACHINES — gestion des inconnues
# ────────────────────────────────────────────────────────────────
# ── Largeurs réelles : cisceaux compactes ~1.2m, nacelles ~2.3m, chariots ~2.3m
# ── Règle 2D : deux machines tiennent côte à côte si leur largeur totale ≤ 2.55m
DEFAULT_MACHINES = {
    # ═══════════════════════════════════════════════════════════════
    #  BASE ÉTENDUE v12 — Dimensions réelles fiches constructeurs
    #  Source : fiches techniques officielles + mesures terrain
    #  Règle largeur : > 1.275m = machine large (slot entier)
    #                 ≤ 1.275m = machine étroite (côte à côte possible)
    # ═══════════════════════════════════════════════════════════════

    # ── CISEAUX ÉTROITS (≤0.85m) — 3 côte à côte possibles sur 2.55m
    "JCPT0607DCH (DINGLI)":   {"longueur":1.46,"largeur":0.76,"poids":0.96, "tps_ch":15,"tps_dech":15,"categorie":"ciseaux"},
    "JCPT0607DCH":            {"longueur":1.46,"largeur":0.76,"poids":0.96, "tps_ch":15,"tps_dech":15,"categorie":"ciseaux"},
    "S 3215 E (SNORKEL)":     {"longueur":1.78,"largeur":0.81,"poids":1.24, "tps_ch":15,"tps_dech":15,"categorie":"ciseaux"},
    "S 3219 E (SNORKEL)":     {"longueur":1.78,"largeur":0.81,"poids":1.40, "tps_ch":15,"tps_dech":15,"categorie":"ciseaux"},
    "S 4732 E (SNORKEL)":     {"longueur":2.30,"largeur":1.19,"poids":2.30, "tps_ch":15,"tps_dech":15,"categorie":"ciseaux"},
    "S 3010 P (SNORKEL)":     {"longueur":1.26,"largeur":0.88,"poids":0.95, "tps_ch":15,"tps_dech":15,"categorie":"push"},
    "GS 2632 (GENIE)":        {"longueur":2.44,"largeur":0.81,"poids":1.96, "tps_ch":15,"tps_dech":15,"categorie":"ciseaux"},
    "GS 2669 DC (GENIE)":     {"longueur":3.12,"largeur":1.75,"poids":3.44, "tps_ch":15,"tps_dech":15,"categorie":"ciseaux"},
    "GS 3369 DC (GENIE)":     {"longueur":4.50,"largeur":1.75,"poids":4.00, "tps_ch":15,"tps_dech":15,"categorie":"ciseaux"},
    "SJ 3215 E (SKYJACK)":    {"longueur":1.80,"largeur":0.82,"poids":1.24, "tps_ch":15,"tps_dech":15,"categorie":"ciseaux"},
    "SJ 16 (SKYJACK)":        {"longueur":1.37,"largeur":0.76,"poids":0.78, "tps_ch":15,"tps_dech":15,"categorie":"push"},
    "SJ 6832 RTE (SKYJACK)":  {"longueur":4.29,"largeur":2.29,"poids":6.12, "tps_ch":15,"tps_dech":15,"categorie":"ciseaux"},
    "1230 ES (J.L.G)":        {"longueur":1.36,"largeur":0.76,"poids":0.82, "tps_ch":15,"tps_dech":15,"categorie":"ciseaux"},
    "3246 ES (J.L.G)":        {"longueur":2.44,"largeur":0.81,"poids":1.96, "tps_ch":15,"tps_dech":15,"categorie":"ciseaux"},
    "SR1023D (LGMG)":         {"longueur":1.00,"largeur":0.60,"poids":0.50, "tps_ch":10,"tps_dech":10,"categorie":"push"},
    "H 15 SX (HAULOTTE)":     {"longueur":2.50,"largeur":1.19,"poids":2.80, "tps_ch":15,"tps_dech":15,"categorie":"ciseaux"},
    "S212L (CESAB)":          {"longueur":1.29,"largeur":0.77,"poids":0.72, "tps_ch":15,"tps_dech":15,"categorie":"ciseaux"},

    # ── MÂTS VERTICAUX / PUSH-AROUND (étroits)
    "TOUCAN 10E-L (J.L.G)":   {"longueur":2.82,"largeur":0.99,"poids":2.60, "tps_ch":15,"tps_dech":15,"categorie":"mat"},
    "TOUCAN 8E (J.L.G)":      {"longueur":2.10,"largeur":0.99,"poids":2.10, "tps_ch":15,"tps_dech":15,"categorie":"mat"},
    "LIGHTLIFT 20.10 (HINOWA)":{"longueur":5.01,"largeur":1.30,"poids":3.20, "tps_ch":15,"tps_dech":15,"categorie":"mat"},
    "MC 405 CRME (MAEDA)":    {"longueur":4.98,"largeur":1.38,"poids":4.20, "tps_ch":15,"tps_dech":15,"categorie":"mat"},

    # ── NACELLES ARTICULÉES LARGES (>1.275m)
    "A 38 E (SNORKEL)":       {"longueur":4.10,"largeur":1.50,"poids":3.88, "tps_ch":15,"tps_dech":15,"categorie":"articulee"},
    "Z 45/25J RT (GENIE)":    {"longueur":6.65,"largeur":2.29,"poids":6.80, "tps_ch":15,"tps_dech":15,"categorie":"articulee"},
    "ZEBRA 12 (ATN)":         {"longueur":6.05,"largeur":1.94,"poids":5.20, "tps_ch":15,"tps_dech":15,"categorie":"articulee"},
    "ZEBRA 12 V2 (ATN)":      {"longueur":6.05,"largeur":1.99,"poids":5.20, "tps_ch":15,"tps_dech":15,"categorie":"articulee"},
    "ZEBRA 16 (ATN)":         {"longueur":7.12,"largeur":2.24,"poids":7.00, "tps_ch":15,"tps_dech":15,"categorie":"articulee"},
    "E 300 AJP (J.L.G)":      {"longueur":5.74,"largeur":1.22,"poids":5.50, "tps_ch":15,"tps_dech":15,"categorie":"articulee"},
    "E 400 AJPn (J.L.G)":     {"longueur":6.71,"largeur":1.50,"poids":6.80, "tps_ch":15,"tps_dech":15,"categorie":"articulee"},
    "E 450 AJ (J.L.G)":       {"longueur":6.45,"largeur":1.75,"poids":7.40, "tps_ch":15,"tps_dech":15,"categorie":"articulee"},
    "HA 16 RTJ O (HAULOTTE)":  {"longueur":6.75,"largeur":2.30,"poids":8.50, "tps_ch":15,"tps_dech":15,"categorie":"articulee"},
    "HA 16 RTJ PRO (HAULOTTE)":{"longueur":6.75,"largeur":2.30,"poids":8.50, "tps_ch":15,"tps_dech":15,"categorie":"articulee"},
    "HA 20 RTJ PRO (HAULOTTE)":{"longueur":7.00,"largeur":2.45,"poids":11.30,"tps_ch":15,"tps_dech":15,"categorie":"articulee"},

    # ── CHARIOTS TÉLESCOPIQUES / ÉLÉVATEURS
    "MT 1440 EASY (MANITOU)":    {"longueur":6.13,"largeur":2.37,"poids":8.60, "tps_ch":15,"tps_dech":15,"categorie":"chariot"},
    "MT 1440 EASY ST5 (MANITOU)":{"longueur":6.13,"largeur":2.36,"poids":8.60, "tps_ch":15,"tps_dech":15,"categorie":"chariot"},
    "MT 933 EASY (MANITOU)":     {"longueur":5.88,"largeur":2.33,"poids":8.20, "tps_ch":15,"tps_dech":15,"categorie":"chariot"},
    "MRT 2150 (MANITOU)":        {"longueur":5.60,"largeur":2.32,"poids":10.80,"tps_ch":15,"tps_dech":15,"categorie":"chariot_rotatif"},
    "3512 PS (J.L.G)":           {"longueur":5.79,"largeur":2.38,"poids":9.40, "tps_ch":15,"tps_dech":15,"categorie":"chariot"},
    "3614 RS (J.L.G)":           {"longueur":6.35,"largeur":2.49,"poids":10.30,"tps_ch":15,"tps_dech":15,"categorie":"chariot"},
    "4017 RS (J.L.G)":           {"longueur":6.50,"largeur":2.49,"poids":11.00,"tps_ch":15,"tps_dech":15,"categorie":"chariot"},
    "525-60 (J.C.B)":            {"longueur":4.00,"largeur":1.84,"poids":6.50, "tps_ch":15,"tps_dech":15,"categorie":"chariot"},
    "RTH 5.25 SH (MAGNI)":       {"longueur":5.50,"largeur":2.30,"poids":10.50,"tps_ch":15,"tps_dech":15,"categorie":"chariot_rotatif"},
    "CQD12-AD2H (HANGCHA)":      {"longueur":2.80,"largeur":1.20,"poids":3.50, "tps_ch":15,"tps_dech":15,"categorie":"elevateur"},

    # ── ÉLÉVATEURS ÉLECTRIQUES (étroits)
    "8FBE15T (TOYOTA)":          {"longueur":2.77,"largeur":1.06,"poids":3.10, "tps_ch":15,"tps_dech":15,"categorie":"elevateur"},
    "G1Q2L30Q (NISSAN)":         {"longueur":3.00,"largeur":1.16,"poids":3.80, "tps_ch":15,"tps_dech":15,"categorie":"elevateur"},
    "U1D2A25LQ (NISSAN)":        {"longueur":3.71,"largeur":1.16,"poids":4.20, "tps_ch":15,"tps_dech":15,"categorie":"elevateur"},
    "KBE20-N (BAOLI)":           {"longueur":2.65,"largeur":1.06,"poids":2.90, "tps_ch":15,"tps_dech":15,"categorie":"elevateur"},
    "KBE25-N (BAOLI)":           {"longueur":2.75,"largeur":1.10,"poids":3.20, "tps_ch":15,"tps_dech":15,"categorie":"elevateur"},
    "UMS 160 (UNICARRIERS)":     {"longueur":2.90,"largeur":1.20,"poids":3.50, "tps_ch":15,"tps_dech":15,"categorie":"elevateur"},

    # ── ACCESSOIRES (poids / volume négligeable)
    "POTENCE MANITOU P 4000 MT (MANITOU)":{"longueur":2.84,"largeur":0.83,"poids":0.40,"tps_ch":10,"tps_dech":10,"categorie":"accessoire"},
    "TREUIL MAGNI - 6T (MAGNI)":          {"longueur":1.00,"largeur":0.60,"poids":0.80,"tps_ch":10,"tps_dech":10,"categorie":"accessoire"},
    "TELECOMMANDE MAGNI RTH (MAGNI)":     {"longueur":0.50,"largeur":0.30,"poids":0.10,"tps_ch":5, "tps_dech":5, "categorie":"accessoire"},

    # ── GÉNÉRIQUES (fallbacks par marque)
    "SKYJACK":  {"longueur":1.55,"largeur":0.82,"poids":1.2, "tps_ch":15,"tps_dech":15,"categorie":"ciseaux"},
    "SNORKEL":  {"longueur":1.78,"largeur":0.81,"poids":1.4, "tps_ch":15,"tps_dech":15,"categorie":"ciseaux"},
    "GS 26":    {"longueur":2.44,"largeur":0.81,"poids":1.96,"tps_ch":15,"tps_dech":15,"categorie":"ciseaux"},
    "GS 32":    {"longueur":2.44,"largeur":0.81,"poids":1.96,"tps_ch":15,"tps_dech":15,"categorie":"ciseaux"},
    "GS 40":    {"longueur":2.48,"largeur":1.19,"poids":3.26,"tps_ch":15,"tps_dech":15,"categorie":"ciseaux"},
    "Z 45":     {"longueur":6.65,"largeur":2.29,"poids":6.50,"tps_ch":15,"tps_dech":15,"categorie":"articulee"},
    "Z 60":     {"longueur":7.20,"largeur":2.29,"poids":8.50,"tps_ch":15,"tps_dech":15,"categorie":"articulee"},
    "HAULOTTE": {"longueur":6.80,"largeur":2.30,"poids":8.50,"tps_ch":15,"tps_dech":15,"categorie":"articulee"},
    "JLG":      {"longueur":6.50,"largeur":2.30,"poids":8.00,"tps_ch":15,"tps_dech":15,"categorie":"articulee"},
    "ATN":      {"longueur":6.05,"largeur":2.00,"poids":5.50,"tps_ch":15,"tps_dech":15,"categorie":"articulee"},
    "MANITOU":  {"longueur":6.13,"largeur":2.37,"poids":8.60,"tps_ch":15,"tps_dech":15,"categorie":"chariot"},
    "MT":       {"longueur":6.13,"largeur":2.37,"poids":8.60,"tps_ch":15,"tps_dech":15,"categorie":"chariot"},
    "MAGNI":    {"longueur":5.50,"largeur":2.30,"poids":10.5,"tps_ch":15,"tps_dech":15,"categorie":"chariot_rotatif"},
    "HANGCHA":  {"longueur":2.80,"largeur":1.20,"poids":3.50,"tps_ch":15,"tps_dech":15,"categorie":"elevateur"},
    "TOYOTA":   {"longueur":2.77,"largeur":1.06,"poids":3.10,"tps_ch":15,"tps_dech":15,"categorie":"elevateur"},
    "NISSAN":   {"longueur":3.00,"largeur":1.16,"poids":3.80,"tps_ch":15,"tps_dech":15,"categorie":"elevateur"},
    "DINGLI":   {"longueur":1.46,"largeur":0.76,"poids":0.96,"tps_ch":15,"tps_dech":15,"categorie":"ciseaux"},
    "TOUCAN":   {"longueur":2.50,"largeur":0.99,"poids":2.40,"tps_ch":15,"tps_dech":15,"categorie":"mat"},
    "DEFAULT":  {"longueur":5.00,"largeur":2.30,"poids":7.0, "tps_ch":15,"tps_dech":15,"categorie":"articulee"},
}

# Gabarits de référence par catégorie pour inférer une machine inconnue
# Aligné sur les catégories réellement utilisées dans le CSV ET machines.json
GABARITS_REF = {
    "ciseaux":         {"longueur":2.40,"largeur":0.85,"poids":1.8, "tps_ch":15,"tps_dech":15},
    "push":            {"longueur":1.35,"largeur":0.76,"poids":0.8, "tps_ch":15,"tps_dech":15},
    "mat":             {"longueur":2.80,"largeur":1.00,"poids":2.5, "tps_ch":15,"tps_dech":15},
    "articulee":       {"longueur":6.50,"largeur":2.30,"poids":7.0, "tps_ch":15,"tps_dech":15},
    "nacelle":         {"longueur":6.50,"largeur":2.30,"poids":7.0, "tps_ch":15,"tps_dech":15},  # alias
    "chariot":         {"longueur":6.00,"largeur":2.35,"poids":10.0,"tps_ch":15,"tps_dech":15},
    "chariot_rotatif": {"longueur":6.80,"largeur":2.45,"poids":17.0,"tps_ch":15,"tps_dech":15},
    "elevateur":       {"longueur":2.80,"largeur":1.20,"poids":3.0, "tps_ch":15,"tps_dech":15},
    "accessoire":      {"longueur":1.00,"largeur":0.60,"poids":0.3, "tps_ch":10,"tps_dech":10},
    # Compatibilité ascendante
    "cisceaux":        {"longueur":2.40,"largeur":0.85,"poids":1.8, "tps_ch":15,"tps_dech":15},
}

# Mots-clés pour deviner la catégorie d'une machine inconnue
# Ordre = priorité de matching (premier qui matche gagne)
CAT_KEYWORDS = {
    "chariot_rotatif": ["MRT", "RTH", " ROTO ", "ROTATIF"],
    "accessoire":      ["TELECOMMANDE", "TREUIL", "POTENCE", "ATTACHE", "FOURCHE"],
    "push":            ["S 3010", "S3010", "PUSH", "MAT VERTICAL", "1230 ES", "SJ 16", "SJ16"],
    "mat":             ["TOUCAN", "PIAF", "1100 R", "880 R", "LIGHTLIFT", "MC 405", "MAT "],
    "articulee":       ["ATJ", " AJ", "AJP", "AJPN", " RTJ", "BOOM", "NACELLE", "ARTICUL",
                        "ZEBRA", "Z 34", "Z 45", "HA 16", "HA 20", "HA 26", "BA18"],
    "ciseaux":         ["SCISSOR", "CISEAU", "PLATEFORME", "VERTICAL",
                        " ES ", " ES)", "JCPT", "GS ", "SJ 32", "SJ32",
                        "S 3215", "S 3219", "S 4726", "S 4732", "PSS", "EWS",
                        "SR1023", "DS 1523", "H 12 SX", "H 15 SX", "CX 15",
                        "2646 ES", "3246 ES"],
    "chariot":         ["MT 9", "MT 14", "MT 18", "MT 19", "MT 20", "MT 22", "MT 24",
                        "JCB", "MERLO", "TELEHANDLER", "TELESCOP", "FORKLIFT",
                        "TH ", "3512 PS", "3614 RS", "4017 RS", "525-"],
    "elevateur":       ["FB ", "FBE", "8FB", "TOYOTA", "NISSAN", "STILL", "CESAB",
                        "UNICARRIERS", "FMX", "DX-", "UMS", "ELEVATEUR"],
}

def load_machine_specs() -> dict:
    if os.path.exists(MACHINES_FILE):
        with open(MACHINES_FILE) as f:
            data = json.load(f)
        # Migration ancien format
        first = next((v for k,v in data.items() if k!="DEFAULT"), {})
        if "tps_chargement" in first and "tps_ch" not in first:
            print("[INFO] Migration machines.json v7→v8...")
            for v in data.values():
                if "tps_chargement" in v:
                    v["tps_ch"]=v["tps_dech"]=v.pop("tps_chargement")
            with open(MACHINES_FILE,"w") as f:
                json.dump(data,f,indent=2,ensure_ascii=False)
        # Forcer mise à jour vers 15/15 min si anciennes valeurs différentes
        for k,v in data.items():
            if k=="DEFAULT": continue
            if v.get("tps_ch",0) != 15 or v.get("tps_dech",0) != 15:
                print(f"  [INFO] Mise à jour {k} : tps_ch/dech → 15 min")
                v["tps_ch"]=15; v["tps_dech"]=15
        with open(MACHINES_FILE,"w") as f:
            json.dump(data,f,indent=2,ensure_ascii=False)
        return data
    with open(MACHINES_FILE,"w") as f:
        json.dump(DEFAULT_MACHINES,f,indent=2,ensure_ascii=False)
    return DEFAULT_MACHINES.copy()

MACHINE_SPECS = load_machine_specs()

# ─────────────────────────────────────────────────────────────────
#  IDENTIFICATION MACHINES — v10 : Matching tolérant
#  Stratégies de matching, dans l'ordre :
#    1. Match exact (clé identique)
#    2. Match normalisé (casse, espaces, parenthèses, points)
#    3. Match sur (constructeur + modèle) extrait par regex
#    4. Match sur tokens partagés (≥2 tokens)
#    5. Inférence par catégorie (fallback)
# ─────────────────────────────────────────────────────────────────

# Normalisation des catégories CSV → catégorie canonique
CATEGORIE_NORMALISEE = {
    "cisceaux":         "ciseaux",
    "ciseaux":          "ciseaux",
    "scissor":          "ciseaux",
    "push":             "push",
    "vertical_mat":     "mat",
    "mat":              "mat",
    "mat_vertical":     "mat",
    "nacelle":          "articulee",
    "articulee":        "articulee",
    "articulée":        "articulee",
    "boom":             "articulee",
    "chariot":          "chariot",
    "telehandler":      "chariot",
    "chariot_rotatif":  "chariot_rotatif",
    "roto":             "chariot_rotatif",
    "elevateur":        "elevateur",
    "élévateur":        "elevateur",
    "forklift":         "elevateur",
    "accessoire":       "accessoire",
}

def normaliser_cat(cat: str) -> str:
    """Retourne la catégorie canonique."""
    if not cat:
        return "articulee"
    return CATEGORIE_NORMALISEE.get(cat.lower().strip(), cat.lower().strip())

def _normaliser_nom(s: str) -> str:
    """Normalise un nom de machine pour matching tolérant."""
    import re as _re
    if not s:
        return ""
    n = str(s).upper()
    # J.L.G → JLG, J.C.B → JCB, etc.
    n = _re.sub(r'\b([A-Z])\.([A-Z])\.([A-Z])\b', r'\1\2\3', n)
    n = _re.sub(r'\b([A-Z])\.([A-Z])\b', r'\1\2', n)
    # Retire ponctuation
    n = n.replace("&", " ").replace("/", " ").replace("-", " ")
    n = n.replace("(", " ").replace(")", " ")
    # Insère un espace entre lettre et chiffre, et chiffre et lettre
    # → "S3219E" devient "S 3219 E", "MRT2150" devient "MRT 2150"
    n = _re.sub(r'([A-Z])(\d)', r'\1 \2', n)
    n = _re.sub(r'(\d)([A-Z])', r'\1 \2', n)
    n = _re.sub(r'\s+', ' ', n).strip()
    return n

def _tokens(s: str) -> list:
    """Tokens utiles d'un nom (≥2 caractères, alphanumérique)."""
    import re as _re
    return [t for t in _re.split(r'[\s,;]+', _normaliser_nom(s)) if len(t) >= 2]

def _deviner_categorie(machine_name: str) -> str:
    """Devine la catégorie d'une machine inconnue à partir de son nom."""
    mu = " " + _normaliser_nom(machine_name) + " "
    for cat, kws in CAT_KEYWORDS.items():
        for kw in kws:
            kw_norm = " " + _normaliser_nom(kw).strip() + " "
            if kw_norm in mu:
                return cat
    return "articulee"  # par défaut nacelle articulée (cas le plus courant)

def _migration_categories_legacy():
    """Migre les anciennes catégories (cisceaux) vers les nouvelles (ciseaux)."""
    modif = False
    for k, v in MACHINE_SPECS.items():
        if k == "DEFAULT":
            continue
        old_cat = v.get("categorie", "")
        new_cat = normaliser_cat(old_cat)
        if new_cat != old_cat:
            v["categorie"] = new_cat
            modif = True
    if modif:
        try:
            with open(MACHINES_FILE, "w") as f:
                json.dump(MACHINE_SPECS, f, indent=2, ensure_ascii=False)
            print(f"[INFO] Migration catégories OK")
        except Exception as e:
            print(f"[WARN] Migration catégories impossible : {e}")

_migration_categories_legacy()

def get_specs(machine_name: str) -> dict:
    """
    Retourne les spécifications d'une machine.
    v10 : matching tolérant + fallback intelligent.
    """
    if not machine_name:
        return GABARITS_REF["articulee"].copy()

    machine_str = str(machine_name).strip()
    mu_norm = _normaliser_nom(machine_str)

    # ── 1. Match exact (insensible casse)
    for k, v in MACHINE_SPECS.items():
        if k == "DEFAULT":
            continue
        if k.strip().upper() == machine_str.upper():
            return v

    # ── 2. Match normalisé (sans points, parenthèses, etc.)
    for k, v in MACHINE_SPECS.items():
        if k == "DEFAULT":
            continue
        k_norm = _normaliser_nom(k)
        if k_norm == mu_norm:
            return v

    # ── 3. Match "contient" : clé courte contenue dans le nom long, ou inverse
    candidates = []
    for k, v in MACHINE_SPECS.items():
        if k == "DEFAULT":
            continue
        k_norm = _normaliser_nom(k)
        if not k_norm:
            continue
        if k_norm in mu_norm or mu_norm in k_norm:
            candidates.append((k, v, len(k_norm)))
    if candidates:
        # Prend le match le plus long (le plus précis)
        candidates.sort(key=lambda x: -x[2])
        return candidates[0][1]

    # ── 4. Match par tokens (au moins 2 tokens partagés)
    tokens_req = set(_tokens(machine_str))
    best = None
    best_score = 0
    for k, v in MACHINE_SPECS.items():
        if k == "DEFAULT":
            continue
        tokens_k = set(_tokens(k))
        partages = tokens_req & tokens_k
        # Bonus si un nombre est partagé (ex: "200ATJ" → "200")
        nombres_partages = sum(1 for t in partages if any(c.isdigit() for c in t))
        score = len(partages) + nombres_partages * 2
        if score >= 2 and score > best_score:
            best, best_score = v, score
    if best:
        return best

    # ── 5. Fallback : inférence par catégorie
    cat = _deviner_categorie(machine_str)
    specs = GABARITS_REF.get(cat, GABARITS_REF["articulee"]).copy()
    specs["categorie"] = cat
    specs["source"] = "AUTO_INFERE"

    # Enregistre l'inconnue pour suivi
    key = machine_str.strip().upper()[:60]
    if key not in MACHINE_SPECS:
        MACHINE_SPECS[key] = specs
        try:
            with open(MACHINES_FILE, "w") as f:
                json.dump(MACHINE_SPECS, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    # Log structuré des inconnues
    try:
        unknown_log = json.load(open(UNKNOWN_LOG_FILE)) if os.path.exists(UNKNOWN_LOG_FILE) else {}
        if key not in unknown_log:
            unknown_log[key] = {
                "nom_original": machine_str,
                "categorie_inferee": cat,
                "specs_appliquees": specs,
                "statut": "A_VALIDER",
            }
            with open(UNKNOWN_LOG_FILE, "w") as f:
                json.dump(unknown_log, f, indent=2, ensure_ascii=False)
        print(f"[WARN] Machine inconnue '{machine_str}' → inférée comme {cat}")
    except Exception:
        pass

    return specs

def tps_operation(specs: dict, phase: str) -> int:
    base = specs.get("tps_dech") or specs.get("tps_chargement") or 30 \
           if phase == "livraison" \
           else specs.get("tps_ch") or specs.get("tps_chargement") or 30
    return base + TPS_SANGLE_MIN + TPS_ATTENTE_CLIENT


# ────────────────────────────────────────────────────────────────
#  CACHE + API
# ────────────────────────────────────────────────────────────────
def load_cache(p): return json.load(open(p)) if os.path.exists(p) else {}
def save_cache(p,d):
    with open(p,"w") as f: json.dump(d,f,indent=2,ensure_ascii=False)

def geocode(address, cache):
    if address in cache: return cache[address]
    for attempt in range(3):
        try:
            r = requests.get("https://api.openrouteservice.org/geocode/search",
                             params={"api_key":API_KEY,"text":address},timeout=10).json()
            res = None
            if r.get("features"):
                c = r["features"][0]["geometry"]["coordinates"]
                res = {"lng":c[0],"lat":c[1]}
            else:
                print(f"  ⚠️  Adresse non reconnue par ORS : '{address}'")
                print(f"      → Mission sera planifiée avec distance estimée")
            cache[address]=res; save_cache(GEOCODE_CACHE_FILE,cache); return res
        except Exception as e:
            print(f"  [retry {attempt+1}] géocode: {e}"); time.sleep(2**attempt)
    cache[address]=None; return None

def get_route(a, b, rc):
    if not a or not b:
        return {"distance_km":None,"duration_min":None}
    if abs(a["lat"]-b["lat"])<1e-6 and abs(a["lng"]-b["lng"])<1e-6:
        return {"distance_km":0.0,"duration_min":0}
    key = f"{a['lng']:.5f},{a['lat']:.5f}->{b['lng']:.5f},{b['lat']:.5f}"
    if key in rc: return rc[key]
    time.sleep(ORS_PAUSE_SEC)
    for attempt in range(3):
        try:
            r = requests.post("https://api.openrouteservice.org/v2/directions/driving-car",
                json={"coordinates":[[a["lng"],a["lat"]],[b["lng"],b["lat"]]]},
                headers={"Authorization":API_KEY,"Content-Type":"application/json"},
                timeout=15).json()
            if "routes" in r:
                s = r["routes"][0]["summary"]
                res = {"distance_km":round(s["distance"]/1000,2),
                       "duration_min":round(s["duration"]/60)}
                rc[key]=res; save_cache(ROUTE_CACHE_FILE,rc); return res
            if attempt < 2: time.sleep(3*(attempt+1))
        except Exception as e:
            print(f"  [retry {attempt+1}] route: {e}"); time.sleep(2**attempt)
    # Fallback : estimation vol d'oiseau × 1.4 (facteur route) à 50 km/h moyenne
    dist_vd = vd(a, b)
    dist_km = round(dist_vd * 1.4, 2)
    dur_min = round(dist_km / 50 * 60)
    return {"distance_km": dist_km, "duration_min": dur_min}


# ────────────────────────────────────────────────────────────────
#  UTILITAIRES
# ────────────────────────────────────────────────────────────────
def vd(a,b):
    if not a or not b: return 9999.0
    return geodesic((a["lat"],a["lng"]),(b["lat"],b["lng"])).km

def fmt_h(m):
    m = max(0,int(m)); return f"{m//60:02d}h{m%60:02d}"

# ─────────────────────────────────────────────────────────────────
#  PLATEAU 2D — Strip Packing
#  Le plateau est modélisé comme une grille de "bandes" en largeur.
#
#  Règle :
#  - Une machine large (largeur > PLATEAU_LARGEUR_MAX_M/2 = >1.275m)
#    occupe toute la largeur → elle prend toute la longueur de sa tranche
#  - Une machine étroite (largeur ≤ 1.275m = cisceaux compactes)
#    peut être mise côte à côte avec une autre machine étroite
#    sur la même longueur → longueur partagée = max(lon_A, lon_B)
#
#  Représentation interne : liste de "slots"
#  slot = {"longueur_utilisee": float, "largeur_restante": float, "poids": float}
#  Chaque slot = une tranche transversale du plateau
# ─────────────────────────────────────────────────────────────────

PLATEAU_DEMI_LARGEUR  = PLATEAU_LARGEUR_MAX_M / 2    # 1.275m
PLATEAU_TIERS_LARGEUR = PLATEAU_LARGEUR_MAX_M / 3    # 0.850m — seuil 3 rangées

class Plateau2D:
    """
    Modélise le plateau en 2D avec bin-packing multi-rangées.

    v12 — 3 niveaux de rangée :
      • Machine très étroite (largeur ≤ 0.85m) : jusqu'à 3 côte à côte
      • Machine étroite (largeur ≤ 1.275m)     : 2 côte à côte
      • Machine large   (largeur > 1.275m)      : slot entier dédié

    Chaque slot = tranche transversale du plateau :
      slot["longueur"]         : longueur occupée (m)
      slot["largeur_restante"] : largeur encore disponible (m)
      slot["poids"]            : poids cumulé sur ce slot (T)
    """
    def __init__(self, type_camion: str = CAMION_DEFAUT):
        self.slots   = []
        self.poids   = 0.0
        self.type_camion = type_camion
        camion = CAMIONS_FLOTTE.get(type_camion, CAMIONS_FLOTTE[CAMION_DEFAUT])
        self.lon_max      = camion["longueur_m"]
        self.larg_max     = camion["largeur_m"]
        self.ptac_max     = camion["ptac_t"]
        self.demi_largeur = self.larg_max / 2      # 1.275m
        self.tiers_largeur= self.larg_max / 3      # 0.850m

    def copie(self):
        p = Plateau2D(self.type_camion)
        p.slots = [dict(s) for s in self.slots]
        p.poids = self.poids
        return p

    def longueur_totale(self) -> float:
        return sum(s["longueur"] for s in self.slots)

    def peut_ajouter(self, specs: dict) -> bool:
        return self._essayer(specs, commit=False)

    def ajouter(self, specs: dict) -> bool:
        return self._essayer(specs, commit=True)

    def _essayer(self, specs: dict, commit: bool) -> bool:
        lon  = specs["longueur"]
        larg = specs.get("largeur", self.larg_max)
        pds  = specs["poids"]

        # Vérification PTAC
        if self.poids + pds > self.ptac_max:
            return False

        # Machine hors-gabarit en largeur → refus immédiat
        if larg > self.larg_max:
            return False

        # ── Machine LARGE (> demi-largeur) → slot entier
        if larg > self.demi_largeur:
            if self.longueur_totale() + lon > self.lon_max:
                return False
            if commit:
                self.slots.append({
                    "longueur": lon,
                    "largeur_restante": 0.0,
                    "poids": pds
                })
                self.poids += pds
            return True

        # ── Machine ÉTROITE ou TRÈS ÉTROITE → chercher slot existant
        # Trier les slots par largeur restante décroissante
        # pour remplir d'abord les slots déjà partiellement utilisés
        slots_tries = sorted(
            enumerate(self.slots),
            key=lambda x: x[1]["largeur_restante"],
            reverse=False  # préférer le slot le plus rempli qui peut encore accueillir
        )
        for idx, slot in slots_tries:
            if slot["largeur_restante"] >= larg - 0.01:  # tolérance 1cm
                nouvelle_lon = max(slot["longueur"], lon)
                delta = nouvelle_lon - slot["longueur"]
                if self.longueur_totale() + delta > self.lon_max:
                    continue
                if commit:
                    self.slots[idx]["longueur"]          = nouvelle_lon
                    self.slots[idx]["largeur_restante"] -= larg
                    self.slots[idx]["poids"]            += pds
                    self.poids                          += pds
                return True

        # Pas de slot compatible → créer nouveau slot
        if self.longueur_totale() + lon > self.lon_max:
            return False
        if commit:
            self.slots.append({
                "longueur":         lon,
                "largeur_restante": self.larg_max - larg,
                "poids":            pds,
            })
            self.poids += pds
        return True

    def resume(self) -> str:
        lon = self.longueur_totale()
        tl  = round(lon / self.lon_max * 100, 1)
        tp  = round(self.poids / self.ptac_max * 100, 1)
        return f"{lon:.2f}m ({tl}%) | {self.poids:.1f}T ({tp}%)"

    def taux_longueur_pct(self) -> float:
        return round(self.longueur_totale() / self.lon_max * 100, 1)

    def taux_poids_pct(self) -> float:
        return round(self.poids / self.ptac_max * 100, 1)


def peut_charger(plateau: "Plateau2D", specs: dict) -> bool:
    """Wrapper pour compatibilité — vérifie si specs tient sur le plateau 2D."""
    return plateau.peut_ajouter(specs)

def full_addr(row):
    a=str(row.get("adresse","")).strip(); v=str(row.get("ville","")).strip()
    if a in ("","nan") or v in ("","nan"): return None
    return f"{a}, {row['code_postal']} {v}, france"

def get_zone(coords, depot) -> str:
    """Zone géographique pour regroupement — basée sur l'angle depuis le dépôt."""
    if not coords or not depot: return "?"
    dlat = coords["lat"]-depot["lat"]; dlng = coords["lng"]-depot["lng"]
    if abs(dlat)<0.05 and abs(dlng)<0.05: return "CENTRE"
    # Découpage en 8 secteurs pour un groupement plus précis
    angle = math.degrees(math.atan2(dlat, dlng))
    if   67.5 <= angle < 112.5: return "NORD"
    elif 22.5 <= angle < 67.5:  return "NORD-EST"
    elif -22.5<= angle < 22.5:  return "EST"
    elif -67.5<= angle < -22.5: return "SUD-EST"
    elif -112.5<=angle < -67.5: return "SUD"
    elif -157.5<=angle <-112.5: return "SUD-OUEST"
    elif angle >= 112.5 or angle < -157.5: return "OUEST"
    else:                       return "NORD-OUEST"


# ────────────────────────────────────────────────────────────────
#  OPTIMISATION LK (Or-opt + 2-opt)
# ────────────────────────────────────────────────────────────────
def or_opt(route, gcache, seg=1):
    best = route[:]
    improved = True
    while improved:
        improved = False
        n = len(best)
        for i in range(n-seg):
            segment = best[i:i+seg]
            rest    = best[:i]+best[i+seg:]
            def d(a,b): return vd(gcache.get(a),gcache.get(b))
            prev = best[i-1] if i>0 else None
            nxt  = best[i+seg] if i+seg<n else None
            cost_rem = (d(prev,segment[0]) if prev else 0) + \
                       (d(segment[-1],nxt) if nxt else 0) - \
                       (d(prev,nxt) if prev and nxt else 0)
            for j in range(1,len(rest)):
                cost_ins = d(rest[j-1],segment[0])+d(segment[-1],rest[j])-d(rest[j-1],rest[j])
                if cost_ins-cost_rem < -1e-6:
                    best = rest[:j]+segment+rest[j:]; improved=True; break
            if improved: break
    return best

def lk_optimize(rows, gcache):
    if len(rows)<=1: return rows
    addrs = [r["full_adresse"] for r in rows]
    remaining = addrs[:]
    ordered = []; pos = None
    while remaining:
        bi = min(range(len(remaining)),
                 key=lambda i: vd(gcache.get(pos) if pos else None, gcache.get(remaining[i])))
        ordered.append(remaining.pop(bi)); pos = ordered[-1]
    for seg in [1,2,3]: ordered = or_opt(ordered,gcache,seg)
    improved = True
    while improved:
        improved = False
        for i in range(len(ordered)-1):
            for j in range(i+2,len(ordered)):
                a,b,c,e = ordered[i],ordered[i+1],ordered[j-1],ordered[j] if j<len(ordered) else ordered[0]
                if vd(gcache.get(a),gcache.get(c))+vd(gcache.get(b),gcache.get(e)) < \
                   vd(gcache.get(a),gcache.get(b))+vd(gcache.get(c),gcache.get(e))-1e-6:
                    ordered[i+1:j]=ordered[i+1:j][::-1]; improved=True
    addr_map = defaultdict(list)
    for r in rows: addr_map[r["full_adresse"]].append(r)
    result = []
    for addr in ordered:
        if addr_map[addr]: result.append(addr_map[addr].pop(0))
    return result

def nearest_neighbor(rows, gcache, start):
    remaining=rows[:]; ordered=[]; pos=start
    while remaining:
        bi = min(range(len(remaining)),key=lambda i: vd(pos,gcache.get(remaining[i].get("full_adresse"))))
        chosen=remaining.pop(bi); ordered.append(chosen)
        pos=gcache.get(chosen["full_adresse"]) or pos
    return ordered


# ────────────────────────────────────────────────────────────────
#  CLUSTERING PAR ZONE
# ────────────────────────────────────────────────────────────────
def cluster_by_zone(rows, gcache, depot):
    zones = defaultdict(list)
    for r in rows:
        c=gcache.get(r.get("full_adresse")); z=get_zone(c,depot)
        r["_zone"]=z; zones[z].append(r)
    result = {}
    for zone,zrows in zones.items():
        n=len(zrows); cid=list(range(n))
        def find(i):
            while cid[i]!=i: cid[i]=cid[cid[i]]; i=cid[i]
            return i
        def union(i,j):
            ci,cj=find(i),find(j)
            if ci!=cj: cid[ci]=cj
        for i in range(n):
            for j in range(i+1,n):
                ca=gcache.get(zrows[i].get("full_adresse"))
                cb=gcache.get(zrows[j].get("full_adresse"))
                if vd(ca,cb)<=CLUSTER_RAYON_KM: union(i,j)
        sub=defaultdict(list)
        for i,r in enumerate(zrows): sub[find(i)].append(r)
        result[zone]=list(sub.values())
    return result


# ────────────────────────────────────────────────────────────────
#  RÉCUPÉRATIONS AU RETOUR
# ────────────────────────────────────────────────────────────────
def select_recups(pivot, depot, dispo, gcache, rc, tps_rest,
                  plateau_entrant: "Plateau2D | None" = None,
                  adresses_livrees: list = None):
    """
    Sélectionne les récups compatibles sur le retour.
    plateau_entrant : état du plateau au moment de la recherche
    adresses_livrees : coordonnées des adresses déjà visitées pour les livraisons
                       → récups à ces adresses = détour 0, priorité maximale
    """
    sel   = []
    plat  = plateau_entrant.copie() if plateau_entrant else Plateau2D()
    tps   = 0
    pos   = pivot
    cands = dispo[:]
    lieux_livres = adresses_livrees or []

    while cands:
        best_i = None; best_s = 9999.0
        for i,r in enumerate(cands):
            c     = gcache.get(r.get("full_adresse"))
            specs = get_specs(r["machine"])
            if not c or not plat.peut_ajouter(specs): continue
            ra    = get_route(pos, c, rc)
            rr    = get_route(c, depot, rc)
            tps_si= tps+(ra["duration_min"] or 0)+tps_operation(specs,"recuperation")+(rr["duration_min"] or 0)
            if tps_si > tps_rest: continue
            # Détour réel
            detour = vd(pos,c)+vd(c,depot)-vd(pos,depot)
            if detour > DETOUR_MAX_RECUP_KM: continue
            # Bonus si l'adresse a déjà été visitée pour une livraison (détour = 0)
            deja_livre = any(vd(c, cl) < 0.3 for cl in lieux_livres)
            score = -999 if deja_livre else detour / max(specs["longueur"],1)
            if score < best_s: best_s=score; best_i=i
        if best_i is None: break
        ch    = cands.pop(best_i)
        specs = get_specs(ch["machine"])
        c     = gcache.get(ch["full_adresse"])
        ra    = get_route(pos, c, rc)
        tps_tr= ra["duration_min"] or 0
        tps_op= tps_operation(specs,"recuperation")
        ch["_dist_r"] = ra["distance_km"]
        ch["_dur_r"]  = tps_tr + tps_op
        tps += tps_tr + tps_op
        plat.ajouter(specs)
        pos = c
        sel.append(ch)
    return sel


# ────────────────────────────────────────────────────────────────
#  RÉCUPÉRATION LOINTAINE — dernier arrêt obligatoire
# ────────────────────────────────────────────────────────────────
def select_recup_lointaine(recups_lointaines: list, pos_fin_livraisons: dict,
                            depot: dict, gcache: dict, rc: dict,
                            tps_restant: int, plateau_recups: "Plateau2D") -> dict | None:
    """
    Choisit LA récupération lointaine à placer en dernier arrêt d'un tour.
    Critères :
      1. Le plateau est vide (livraisons terminées) → peut charger
      2. Le temps aller + opération + retour dépôt tient dans tps_restant
      3. Parmi les candidats, on prend le plus proche de pos_fin_livraisons
         (= le moins de détour sur le chemin retour)
    """
    best = None
    best_dist = float("inf")

    for r in recups_lointaines:
        c     = gcache.get(r.get("full_adresse"))
        specs = get_specs(r["machine"])
        if not c: continue
        if not plateau_recups.peut_ajouter(specs): continue

        ra = get_route(pos_fin_livraisons, c, rc)
        rr = get_route(c, depot, rc)
        tps_tr  = ra["duration_min"] or 0
        tps_op  = tps_operation(specs, "recuperation")
        tps_ret = rr["duration_min"] or 0
        tps_tot = tps_tr + tps_op + tps_ret

        if tps_tot > tps_restant:
            continue

        dist_depuis_pivot = vd(pos_fin_livraisons, c)
        if dist_depuis_pivot < best_dist:
            best_dist = dist_depuis_pivot
            best = r
            best["_dist_r"]  = ra["distance_km"]
            best["_dur_r"]   = tps_tr + tps_op
            best["_tps_ret"] = tps_ret

    return best


# ────────────────────────────────────────────────────────────────
#  OR-TOOLS VRP — optimisation globale
# ────────────────────────────────────────────────────────────────
def _mat_temps(missions, gcache, rc, depot):
    pts=[depot]+[gcache.get(m.get("full_adresse")) for m in missions]
    n=len(pts); mat=[[0]*n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i==j: continue
            if not pts[i] or not pts[j]: mat[i][j]=9999; continue
            mat[i][j]=int(get_route(pts[i],pts[j],rc)["duration_min"] or 0)
    return mat

def _mat_dist(missions, gcache, rc, depot):
    pts=[depot]+[gcache.get(m.get("full_adresse")) for m in missions]
    n=len(pts); mat=[[0]*n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i==j: continue
            if not pts[i] or not pts[j]: mat[i][j]=999999; continue
            mat[i][j]=int((get_route(pts[i],pts[j],rc)["distance_km"] or 0)*1000)
    return mat

def build_tours_ortools(livraisons, recups, gcache, rc, depot, nb_vehicules=24):
    """
    VRP OR-Tools : toutes contraintes simultanées.
    nb_vehicules doit être >= nombre de tours nécessaires.
    Fallback automatique sur build_tours() si pas de solution.
    """
    if not ORTOOLS_AVAILABLE:
        return build_tours(livraisons, recups, gcache, rc, depot)

    toutes = livraisons + recups
    n      = len(toutes)
    if n == 0: return []
    nb_v   = min(nb_vehicules, n)
    print(f"  OR-Tools : {n} missions, {nb_v} véhicules max")

    print("  Calcul matrices...")
    mat_d = _mat_dist(toutes, gcache, rc, depot)
    mat_t = _mat_temps(toutes, gcache, rc, depot)

    dem_lon=[]; dem_pds=[]; tps_svc=[]
    for m in toutes:
        specs=get_specs(m["machine"])
        s=1 if m.get("type_mission_norm","livraison")=="livraison" else -1
        dem_lon.append(int(specs["longueur"]*10)*s)
        dem_pds.append(int(specs["poids"]*10)*s)
        tps_svc.append(tps_operation(specs,m.get("type_mission_norm","livraison")))

    cap_lon=int(PLATEAU_LONGUEUR_MAX_M*10); cap_pds=int(PLATEAU_POIDS_MAX_T*10)
    manager=pywrapcp.RoutingIndexManager(n+1,nb_v,0)
    routing=pywrapcp.RoutingModel(manager)

    def cb_d(fi,fj):
        i=manager.IndexToNode(fi)-1; j=manager.IndexToNode(fj)-1
        return mat_d[i+1 if i>=0 else 0][j+1 if j>=0 else 0]
    dc=routing.RegisterTransitCallback(cb_d)
    routing.SetArcCostEvaluatorOfAllVehicles(dc)

    def cb_t(fi,fj):
        i=manager.IndexToNode(fi)-1; j=manager.IndexToNode(fj)-1
        svc=tps_svc[i] if i>=0 else 0
        return mat_t[i+1 if i>=0 else 0][j+1 if j>=0 else 0]+svc
    tc=routing.RegisterTransitCallback(cb_t)
    routing.AddDimension(tc,60,MAX_TRAVAIL_MIN,False,"Temps")
    tps_dim=routing.GetDimensionOrDie("Temps")
    for i in range(1,n+1):
        tps_dim.CumulVar(manager.NodeToIndex(i)).SetRange(0,MAX_TRAVAIL_MIN)

    def cb_lon(fi):
        i=manager.IndexToNode(fi)-1; return dem_lon[i] if i>=0 else 0
    routing.AddDimensionWithVehicleCapacity(
        routing.RegisterUnaryTransitCallback(cb_lon),0,[cap_lon]*nb_v,True,"Longueur")

    def cb_pds(fi):
        i=manager.IndexToNode(fi)-1; return dem_pds[i] if i>=0 else 0
    routing.AddDimensionWithVehicleCapacity(
        routing.RegisterUnaryTransitCallback(cb_pds),0,[cap_pds]*nb_v,True,"Poids")

    params=pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy=(
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC)
    params.local_search_metaheuristic=(
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH)
    params.time_limit.seconds=45

    print("  Résolution OR-Tools (45s)...")
    sol=routing.SolveWithParameters(params)
    if not sol:
        print("  ⚠️  Pas de solution → fallback v8")
        return build_tours(livraisons,recups,gcache,rc,depot)

    print("  ✅ Solution OR-Tools trouvée !")
    tournees=[]; tour_id=1

    # ── v11 : OR-Tools donne l'ordre des missions mais le Plateau2D physique
    #         reste la contrainte AUTORITÉ. On redécoupe en tours réels ici.
    missions_ordonnees = []
    for v in range(nb_v):
        idx=routing.Start(v); route=[]
        while not routing.IsEnd(idx):
            node=manager.IndexToNode(idx)
            if node>0: route.append(toutes[node-1])
            idx=sol.Value(routing.NextVar(idx))
        missions_ordonnees.extend(route)

    # Séparer livraisons et récups dans l'ordre OR-Tools suggéré
    livs_ord = [r for r in missions_ordonnees if r.get("type_mission_norm","livraison")=="livraison"]
    recs_ord  = [r for r in missions_ordonnees if r.get("type_mission_norm","livraison")!="livraison"]

    # Reconstruire les tours en respectant le plateau physique (comme build_tours)
    liv_rest = livs_ord[:]
    rec_rest  = recs_ord[:]

    while liv_rest or rec_rest:
        b_liv=[]; plat_liv=Plateau2D()
        pos=depot; heure=HEURE_DEBUT_MIN; tps=0.0

        # Phase livraison : remplir le plateau SANS dépasser 100%
        for r in liv_rest[:]:
            specs=get_specs(r["machine"]); c=gcache.get(r.get("full_adresse"))
            if not c: continue
            if not plat_liv.peut_ajouter(specs): continue   # ← vérification physique
            ra=get_route(pos,c,rc); rr=get_route(c,depot,rc)
            tps_tr=ra["duration_min"] or 0; tps_op=tps_operation(specs,"livraison")
            if tps+tps_tr+tps_op+(rr["duration_min"] or 0) > MAX_TRAVAIL_MIN*1.05:
                continue
            r.update({"_dist":ra["distance_km"],"_dur":tps_tr+tps_op,"_pause":0,
                      "_heure":fmt_h(heure+tps_tr),"_phase":"livraison",
                      "_tour_id":tour_id,"_chauffeur_id":1,"_chauffeur_nom":"Chauffeur 1"})
            plat_liv.ajouter(specs); tps+=tps_tr+tps_op; heure+=tps_tr+tps_op
            r["_lon"]=round(plat_liv.longueur_totale(),2); r["_pds"]=round(plat_liv.poids,2)
            pos=c; b_liv.append(r); liv_rest.remove(r)

        if not b_liv:
            # Récups seules restantes
            if not rec_rest: break
            b_rec=[]; plat_rec=Plateau2D(); pos_r=depot; heure_r=HEURE_DEBUT_MIN
            for r in rec_rest[:]:
                specs=get_specs(r["machine"]); c=gcache.get(r.get("full_adresse"))
                if not c or not plat_rec.peut_ajouter(specs): continue
                ra=get_route(pos_r,c,rc); tps_tr=ra["duration_min"] or 0
                tps_op=tps_operation(specs,"recuperation")
                r.update({"_dist":ra["distance_km"],"_dur":tps_tr+tps_op,"_pause":0,
                          "_heure":fmt_h(heure_r+tps_tr),"_phase":"recuperation",
                          "_tour_id":tour_id,"_chauffeur_id":1,"_chauffeur_nom":"Chauffeur 1"})
                plat_rec.ajouter(specs); heure_r+=tps_tr+tps_op
                r["_lon"]=round(plat_rec.longueur_totale(),2); r["_pds"]=round(plat_rec.poids,2)
                pos_r=c; b_rec.append(r); rec_rest.remove(r)
            if not b_rec: break
            rr=get_route(pos_r,depot,rc); dist_ret=rr["distance_km"] or 0
            dist_tot=sum((m.get("_dist") or 0) for m in b_rec)+dist_ret
            _save_tour(tour_id,[],b_rec,dist_tot,dist_ret,plat_rec.longueur_totale(),plat_rec.poids,"CHARGÉ","OR-TOOLS",tournees)
            tour_id+=1
            continue

        # Phase récup : plateau vide, chercher récups compatibles
        plat_rec=Plateau2D(); pos_r=pos; heure_r=heure; b_rec=[]
        tps_rest=MAX_TRAVAIL_MIN-tps
        adresses_livrees=[gcache.get(r["full_adresse"]) for r in b_liv if gcache.get(r["full_adresse"])]
        b_rec=select_recups(pos_r,depot,rec_rest,gcache,rc,tps_rest,plat_rec,adresses_livrees)
        for r in b_rec:
            if r in rec_rest: rec_rest.remove(r)
            c=gcache.get(r["full_adresse"]); ra=get_route(pos_r,c,rc)
            tps_tr=ra["duration_min"] or 0; tps_op=tps_operation(get_specs(r["machine"]),"recuperation")
            r.update({"_dist":r.get("_dist_r") or ra["distance_km"],
                      "_dur":r.get("_dur_r") or (tps_tr+tps_op),"_pause":0,
                      "_heure":fmt_h(heure_r+tps_tr),"_phase":"recuperation",
                      "_tour_id":tour_id,"_chauffeur_id":1,"_chauffeur_nom":"Chauffeur 1"})
            specs=get_specs(r["machine"]); plat_rec.ajouter(specs)
            r["_lon"]=round(plat_rec.longueur_totale(),2); r["_pds"]=round(plat_rec.poids,2)
            pos_r=c or pos_r; heure_r+=tps_tr+tps_op

        rr=get_route(pos_r,depot,rc); dist_ret=rr["distance_km"] or 0
        dist_tot=sum((m.get("_dist") or 0) for m in b_liv+b_rec)+dist_ret
        charge="CHARGÉ" if b_rec else "À VIDE"
        lon_liv=plat_liv.longueur_totale(); pds_liv=plat_liv.poids
        print(f"  ✓ Tour {tour_id} [OR-Tools v11] : {len(b_liv)}🚚+{len(b_rec)}📦 | "
              f"{round(dist_tot,1)}km | {charge} | "
              f"plat {round(lon_liv/PLATEAU_LONGUEUR_MAX_M*100,1)}%")
        _save_tour(tour_id,b_liv,b_rec,dist_tot,dist_ret,lon_liv,pds_liv,charge,"OR-TOOLS",tournees)
        tour_id+=1

    return tournees


# ────────────────────────────────────────────────────────────────
#  CONSTRUCTION TOURS
# ────────────────────────────────────────────────────────────────
def _construire_tour_zone(livs_zone, recups_zone, lointaines_rest,
                          gcache, rc, depot, tournees, tour_id_start):
    """
    Construit les tours pour une zone en traitant livraisons ET récups
    ensemble dès le départ :

    Algorithme :
    1. Trier TOUTES les missions (livraisons + récups) par ordre géographique
       depuis le dépôt (LK-optimize sur le pool complet)
    2. Remplir le plateau en respectant la règle :
       - LIVRAISONS d'abord (plateau chargé au départ)
       - RÉCUPS après (plateau se vide au fil des livraisons, puis se recharge)
    3. Contrainte : aucune récup ne peut être chargée tant qu'une livraison
       est encore sur le plateau (règle métier fondamentale)
    4. Récups lointaines → dernier arrêt après toutes les livraisons

    Retourne le dernier tour_id utilisé.
    """
    tour_id  = tour_id_start
    liv_rest = livs_zone[:]
    rec_rest = recups_zone[:]

    while liv_rest or rec_rest:
        # ── Construire un tour : livraisons d'abord, puis récups
        batch_liv = []; batch_rec = []
        plat_liv  = Plateau2D()   # plateau au départ (livraisons)
        tps = 0.0; pos = depot; heure = HEURE_DEBUT_MIN; conduite = 0

        # ── Phase 1 : remplir le plateau au maximum avec toutes les livraisons possibles
        # v12 : tri FFD d'abord (grandes machines contraignantes en tête),
        #       puis optimisation géographique LK sur l'ordre obtenu
        livs_ffd = trier_ffd_plateau(liv_rest[:])
        livs_ord = lk_optimize(livs_ffd, gcache) if len(livs_ffd) > 1 else livs_ffd[:]

        # Identifier les livraisons dont l'adresse a aussi une récup
        # → les déplacer en fin de circuit
        rec_addrs_coords = []
        for rec in rec_rest:
            c_rec = gcache.get(rec.get("full_adresse"))
            if c_rec:
                rec_addrs_coords.append((c_rec["lat"], c_rec["lng"]))

        def a_recup_meme_endroit(r):
            c = gcache.get(r.get("full_adresse"))
            if not c: return False
            # Rayon élargi à 2km pour regrouper les zones étendues (ex: Aéroport Orly)
            return any(
                vd(c, {"lat": lat, "lng": lng}) < 2.0
                for lat, lng in rec_addrs_coords
            )

        livs_sans_recup = [r for r in livs_ord if not a_recup_meme_endroit(r)]
        livs_avec_recup = [r for r in livs_ord if a_recup_meme_endroit(r)]
        livs_ord = livs_sans_recup + livs_avec_recup

        # Construire un index id→objet pour retrouver les vrais objets de liv_rest
        liv_rest_by_id = {id(r): r for r in liv_rest}

        for r_opt in livs_ord:
            # Retrouver l'objet original dans liv_rest (lk_optimize peut retourner des copies)
            r = liv_rest_by_id.get(id(r_opt), r_opt)
            if r not in liv_rest:
                # Chercher par contenu (full_adresse + machine)
                match = next((x for x in liv_rest
                              if x.get("full_adresse") == r_opt.get("full_adresse")
                              and x.get("machine") == r_opt.get("machine")
                              and x not in batch_liv), None)
                if match is None:
                    continue
                r = match

            specs  = get_specs(r["machine"])
            c      = gcache.get(r["full_adresse"])
            if not c:
                continue  # adresse non géocodée → ignorée, sera traitée séparément
            if not plat_liv.peut_ajouter(specs):
                continue  # plateau plein pour cette machine → on cherche une plus petite

            ra     = get_route(pos, c, rc)
            rr     = get_route(c, depot, rc)
            tps_tr = ra["duration_min"] or 0
            tps_op = tps_operation(specs, "livraison")
            pause  = TPS_PAUSE_MIN if conduite + tps_tr >= SEUIL_PAUSE_MIN else 0
            tps_si = tps + tps_tr + pause + tps_op + (rr["duration_min"] or 0)
            if tps_si > MAX_TRAVAIL_MIN * 1.05:
                continue

            conduite += tps_tr
            if pause: tps += TPS_PAUSE_MIN; heure += TPS_PAUSE_MIN; conduite = 0
            r.update({"_dist": ra["distance_km"], "_dur": tps_tr + tps_op,
                      "_pause": pause, "_heure": fmt_h(heure + tps_tr),
                      "_phase": "livraison"})
            plat_liv.ajouter(specs)
            tps  += tps_tr + tps_op
            heure+= tps_tr + tps_op
            r["_lon"] = round(plat_liv.longueur_totale(), 2)
            r["_pds"] = round(plat_liv.poids, 2)
            pos = c or pos
            batch_liv.append(r)
            if r in liv_rest:
                liv_rest.remove(r)
            liv_rest_by_id = {id(x): x for x in liv_rest}  # reconstruire l'index

        if not batch_liv:
            # Plus de livraisons possibles → passer aux récups seules
            break

        # ── Phase 2 : récups proches sur le retour (plateau vide)
        # La co-localisation est gérée ici : quand on repasse par une adresse
        # où on a livré, le plateau est vide → on peut charger les récups
        # Filtrer les récups sans coordonnées valides — elles seront traitées séparément
        rec_valides    = [r for r in rec_rest if gcache.get(r.get("full_adresse"))]
        rec_sans_coord = [r for r in rec_rest if not gcache.get(r.get("full_adresse"))]
        if rec_sans_coord:
            for r in rec_sans_coord:
                addr = r.get("full_adresse","?").split(",")[0]
                print(f"  ⚠️  Récup '{r.get('client','?')}' ({addr}) : "
                      f"coordonnées manquantes → tour dédié nécessaire")
        plat_rec  = Plateau2D()
        tps_rest  = MAX_TRAVAIL_MIN - tps
        # Coordonnées des adresses déjà visitées pour les livraisons
        adresses_livrees = [gcache.get(r["full_adresse"]) for r in batch_liv
                            if gcache.get(r["full_adresse"])]
        recups_sel = select_recups(pos, depot, rec_valides, gcache, rc, tps_rest,
                                   plat_rec, adresses_livrees)
        # Retirer les récups sélectionnées de rec_rest (pas rec_valides)
        for r in recups_sel:
            if r in rec_rest: rec_rest.remove(r)
        # Les récups sans coord restent dans rec_rest pour traitement séparé
        pos_r = pos; heure_r = heure; lon_r = pds_r = 0.0
        for r in recups_sel:
            c      = gcache.get(r["full_adresse"])
            specs  = get_specs(r["machine"])
            ra     = get_route(pos_r, c, rc)
            tps_tr = ra["duration_min"] or 0
            tps_op = tps_operation(specs, "recuperation")
            r.update({"_dist": r.get("_dist_r") or ra["distance_km"],
                      "_dur":  r.get("_dur_r")  or (tps_tr + tps_op),
                      "_pause": 0, "_heure": fmt_h(heure_r + tps_tr),
                      "_phase": "recuperation"})
            plat_rec.ajouter(specs)
            r["_lon"] = round(plat_rec.longueur_totale(), 2)
            r["_pds"] = round(plat_rec.poids, 2)
            pos_r    = c or pos_r
            heure_r += tps_tr + tps_op

        # ── Phase 3 : récup lointaine en dernier arrêt si temps disponible
        tps_apres = tps + sum((r.get("_dur") or 0) for r in recups_sel)
        recup_loint = None
        if lointaines_rest:
            tps_rest_l = MAX_TRAVAIL_MIN - tps_apres
            recup_loint = select_recup_lointaine(
                lointaines_rest, pos_r, depot,
                gcache, rc, tps_rest_l, plat_rec)
            if recup_loint:
                if recup_loint in lointaines_rest:
                    lointaines_rest.remove(recup_loint)
                c      = gcache.get(recup_loint["full_adresse"])
                specs  = get_specs(recup_loint["machine"])
                ra     = get_route(pos_r, c, rc)
                tps_tr = ra["duration_min"] or 0
                tps_op = tps_operation(specs, "recuperation")
                recup_loint.update({
                    "_dist":  recup_loint.get("_dist_r") or ra["distance_km"],
                    "_dur":   recup_loint.get("_dur_r")  or (tps_tr + tps_op),
                    "_pause": 0, "_heure": fmt_h(heure_r + tps_tr),
                    "_phase": "recuperation",
                })
                plat_rec.ajouter(specs)
                recup_loint["_lon"] = round(plat_rec.longueur_totale(), 2)
                recup_loint["_pds"] = round(plat_rec.poids, 2)
                pos_r    = c or pos_r
                heure_r += tps_tr + tps_op
                print(f"  🏁 Récup lointaine '{recup_loint.get('client','?')}' "
                      f"→ dernier arrêt Tour {tour_id} "
                      f"({recup_loint.get('ville','?')})")

        all_recups = recups_sel + ([recup_loint] if recup_loint else [])
        rr         = get_route(pos_r, depot, rc)
        dist_ret   = rr["distance_km"] or 0
        dist_tot   = sum((m.get("_dist") or 0) for m in batch_liv + all_recups) + dist_ret
        charge     = "CHARGÉ" if all_recups else "À VIDE"
        zone_label = batch_liv[0].get("_zone", "?") if batch_liv else "?"

        print(f"  ✓ Tour {tour_id} [{zone_label}] : "
              f"{len(batch_liv)}🚚+{len(all_recups)}📦 | "
              f"{round(dist_tot,1)}km | {charge} | "
              f"plat liv {round(plat_liv.longueur_totale()/PLATEAU_LONGUEUR_MAX_M*100,1)}%")

        _save_tour(tour_id, batch_liv, all_recups, dist_tot, dist_ret,
                   plat_liv.longueur_totale(), plat_liv.poids, charge,
                   zone_label, tournees)
        tour_id += 1

    return tour_id, rec_rest


# ────────────────────────────────────────────────────────────────
#  PRÉ-ANALYSE v12 — Rapport avant optimisation
#  Analyse le volume de missions et produit :
#    1. Rapport dimensions manquantes / hors-gabarit
#    2. Estimation du nombre minimal de tours physiques
#    3. Tri FFD (First Fit Decreasing) pour maximiser remplissage
# ────────────────────────────────────────────────────────────────

def preanalyse(livraisons: list, recups: list) -> dict:
    """
    Analyse complète avant optimisation.
    Retourne un dict avec rapport et missions retriées.
    """
    toutes = livraisons + recups
    rapport = {
        "nb_missions":        len(toutes),
        "nb_livraisons":      len(livraisons),
        "nb_recups":          len(recups),
        "machines_inconnues": [],
        "machines_hors_gabarit": [],
        "machines_etroites":  [],
        "machines_larges":    [],
        "longueur_totale_m":  0.0,
        "poids_total_t":      0.0,
        "tours_min_theorique": 0,
        "gains_potentiels":   [],
    }

    lon_etroites = 0.0  # longueur cumulée machines étroites (côte à côte possible)
    lon_larges   = 0.0  # longueur cumulée machines larges (slot entier)
    poids_total  = 0.0

    for r in toutes:
        nom = r.get("machine", "?")
        specs = get_specs(nom)
        larg  = specs.get("largeur", 2.30)
        lon   = specs.get("longueur", 5.00)
        pds   = specs.get("poids", 7.0)
        source = specs.get("source", "")

        poids_total += pds

        # Machine hors-gabarit (>2.55m de large)
        if larg > PLATEAU_LARGEUR_MAX_M:
            rapport["machines_hors_gabarit"].append({
                "machine": nom, "largeur": larg,
                "action": "Tour dédié obligatoire ou transport spécial"
            })
            lon_larges += lon

        # Machine inconnue (dimensions inférées)
        elif source == "AUTO_INFERE":
            rapport["machines_inconnues"].append({
                "machine": nom, "specs_appliquees": specs,
                "action": "Vérifier dimensions réelles"
            })
            lon_larges += lon

        # Machine étroite (peut aller côte à côte)
        elif larg <= PLATEAU_DEMI_LARGEUR:
            rapport["machines_etroites"].append({"machine": nom, "largeur": larg, "longueur": lon})
            lon_etroites += lon

        # Machine large (slot entier)
        else:
            rapport["machines_larges"].append({"machine": nom, "largeur": larg, "longueur": lon})
            lon_larges += lon

    rapport["longueur_totale_m"] = round(lon_etroites + lon_larges, 1)
    rapport["poids_total_t"]     = round(poids_total, 1)

    # Estimation tours minimum :
    # Machines larges : chacune prend ~lon m sur 12.5m
    # Machines étroites : peuvent se combiner → diviser par 2 (ou 3 si très étroites)
    lon_etroites_effectives = lon_etroites / 2.0  # pessimiste : 2 côte à côte
    tours_min = math.ceil((lon_larges + lon_etroites_effectives) / PLATEAU_LONGUEUR_MAX_M)
    rapport["tours_min_theorique"] = max(tours_min, 1)

    # Gains potentiels identifiés
    nb_etroites = len(rapport["machines_etroites"])
    if nb_etroites >= 2:
        gain_tours = nb_etroites // 2
        rapport["gains_potentiels"].append(
            f"{nb_etroites} machines étroites → regroupement 2-3 par camion "
            f"(-{gain_tours} tour(s) potentiel)"
        )
    if rapport["machines_inconnues"]:
        rapport["gains_potentiels"].append(
            f"{len(rapport['machines_inconnues'])} machine(s) à dimensions inconnues → "
            f"risque sur-estimation longueur"
        )
    if rapport["machines_hors_gabarit"]:
        rapport["gains_potentiels"].append(
            f"⚠️  {len(rapport['machines_hors_gabarit'])} machine(s) hors-gabarit "
            f"(largeur > {PLATEAU_LARGEUR_MAX_M}m) → tour dédié chacune"
        )

    return rapport


def afficher_preanalyse(rapport: dict):
    """Affiche le rapport de pré-analyse en console."""
    print()
    print("╔" + "═"*68 + "╗")
    print("║  PRÉ-ANALYSE v12 — Rapport avant optimisation" + " "*22 + "║")
    print("╠" + "═"*68 + "╣")
    print(f"║  {rapport['nb_missions']} missions : "
          f"{rapport['nb_livraisons']} livraisons + {rapport['nb_recups']} récupérations"
          + " "*max(0, 30-len(str(rapport['nb_missions']))) + "║")
    print(f"║  Longueur cumulée : {rapport['longueur_totale_m']}m  |  "
          f"Poids cumulé : {rapport['poids_total_t']}T" + " "*20 + "║")
    print(f"║  Tours minimum théorique : {rapport['tours_min_theorique']}" + " "*42 + "║")
    print("╠" + "═"*68 + "╣")

    if rapport["machines_hors_gabarit"]:
        print(f"║  🔴 HORS-GABARIT ({len(rapport['machines_hors_gabarit'])} machine(s)) :" + " "*40 + "║")
        for m in rapport["machines_hors_gabarit"]:
            print(f"║    • {m['machine'][:45]:45s} {m['largeur']:.2f}m  ║")

    if rapport["machines_inconnues"]:
        print(f"║  🟡 DIMENSIONS INCONNUES ({len(rapport['machines_inconnues'])} machine(s)) :" + " "*33 + "║")
        for m in rapport["machines_inconnues"][:5]:
            print(f"║    • {m['machine'][:60]:60s}  ║")
        if len(rapport["machines_inconnues"]) > 5:
            print(f"║    ... et {len(rapport['machines_inconnues'])-5} autres" + " "*50 + "║")

    if rapport["gains_potentiels"]:
        print("╠" + "═"*68 + "╣")
        print("║  ✅ GAINS POTENTIELS IDENTIFIÉS :" + " "*35 + "║")
        for g in rapport["gains_potentiels"]:
            print(f"║    → {g[:62]:62s}  ║")

    print("╚" + "═"*68 + "╝")
    print()


def trier_ffd_plateau(missions: list) -> list:
    """
    First Fit Decreasing pour le plateau :
    Trie les missions pour maximiser le remplissage.

    Ordre de priorité :
    1. Machines larges longues EN PREMIER (elles contraignent le plus)
    2. Machines larges courtes
    3. Machines étroites longues (peuvent se combiner)
    4. Accessoires en dernier

    Ce tri assure que les grandes machines sont placées quand le plateau
    est encore vide, et les petites comblent les espaces restants.
    """
    def score_ffd(r):
        specs = get_specs(r.get("machine", ""))
        lon   = specs.get("longueur", 5.0)
        larg  = specs.get("largeur",  2.3)
        cat   = specs.get("categorie", "articulee")

        if cat == "accessoire":
            return (4, -lon)   # accessoires en dernier
        if larg > PLATEAU_DEMI_LARGEUR:
            return (1, -lon)   # larges d'abord, plus longues en tête
        else:
            return (2, -lon)   # étroites ensuite, plus longues en tête

    return sorted(missions, key=score_ffd)


def build_tours(livraisons, recups, gcache, rc, depot):
    """
    Construction intelligente v8 :
    - Livraisons ET récups de la MÊME ZONE traitées ensemble
    - Algorithme : livraisons d'abord → récups proches → récup lointaine dernier arrêt
    - Résultat : un chauffeur qui va à Orly livre ET récupère à Orly dans le même tour
    """
    # Séparer récups lointaines
    recups_proches    = [r for r in recups
                         if vd(gcache.get(r.get("full_adresse")), depot) <= RECUP_LOINTAINE_KM]
    recups_lointaines = [r for r in recups
                         if vd(gcache.get(r.get("full_adresse")), depot) >  RECUP_LOINTAINE_KM]

    if recups_lointaines:
        noms = [r.get("full_adresse","?").split(",")[0] for r in recups_lointaines]
        print(f"  🗺  {len(recups_lointaines)} récup(s) lointaine(s) → dernier arrêt : {noms}")

    lointaines_rest = recups_lointaines[:]
    tournees        = []
    tour_id         = 1

    # ── Grouper livraisons ET récups proches par zone géographique
    # EXCEPTION : si peu de missions (<= 20), traiter tout en une seule zone
    # Le découpage par zone est contre-productif sur de petits volumes
    toutes_missions = [(r, "livraison")  for r in livraisons] + \
                      [(r, "recuperation") for r in recups_proches]

    nb_total = len(livraisons) + len(recups_proches)
    zones = defaultdict(lambda: {"livraisons": [], "recups": []})

    if nb_total <= 20:
        # Toutes les missions dans une seule zone → circuit optimal global
        print(f"  ℹ️  {nb_total} missions → optimisation globale (pas de découpage par zone)")
        for r, phase in toutes_missions:
            r["_zone"] = "GLOBAL"
            zones["GLOBAL"][("livraisons" if phase == "livraison" else "recups")].append(r)
    else:
        for r, phase in toutes_missions:
            c    = gcache.get(r.get("full_adresse"))
            zone = get_zone(c, depot)
            r["_zone"] = zone
            zones[zone][("livraisons" if phase == "livraison" else "recups")].append(r)

    # Traiter les zones les plus lointaines en premier
    def zone_max_dist(z):
        all_r = zones[z]["livraisons"] + zones[z]["recups"]
        return max((vd(gcache.get(r.get("full_adresse")), depot) for r in all_r), default=0)

    recups_restantes_globales = []

    for zone in sorted(zones.keys(), key=zone_max_dist, reverse=True):
        livs_z = zones[zone]["livraisons"]
        recs_z = zones[zone]["recups"]
        if not livs_z and not recs_z:
            continue
        print(f"\n  ── Zone {zone} : {len(livs_z)} livraisons + {len(recs_z)} récups ──")
        tour_id, recs_non_assignees = _construire_tour_zone(
            livs_z, recs_z, lointaines_rest,
            gcache, rc, depot, tournees, tour_id)
        recups_restantes_globales.extend(recs_non_assignees)

    # ── Récups restantes non couvertes → tours dédiés
    all_restantes = recups_restantes_globales + lointaines_rest
    if all_restantes:
        print(f"\n  ── {len(all_restantes)} récup(s) non assignées → tours dédiés ──")
        zones_r = cluster_by_zone(all_restantes, gcache, depot)
        for zone, clusters in zones_r.items():
            for cluster in clusters:
                cl_opt = lk_optimize(cluster, gcache)
                batch=[]; plat=Plateau2D(); tps=0.0; pos=depot; heure=HEURE_DEBUT_MIN
                for r in cl_opt:
                    specs=get_specs(r["machine"]); c=gcache.get(r["full_adresse"])
                    if not c or not plat.peut_ajouter(specs):
                        # Machine ne tient pas → clore le tour en cours et en ouvrir un nouveau
                        if batch:
                            _save_recup(batch,plat,pos,depot,gcache,rc,tournees,tour_id,zone)
                            tour_id+=1; batch=[]; plat=Plateau2D(); tps=0.0; pos=depot; heure=HEURE_DEBUT_MIN
                        if not c:
                            continue  # adresse inconnue → on skip
                        if not plat.peut_ajouter(specs):
                            print(f"  ⚠️  Machine '{r.get('machine','?')}' trop grande même sur plateau vide → ignorée")
                            continue
                    ra=get_route(pos,c,rc); rr=get_route(c,depot,rc)
                    tps_tr=ra["duration_min"] or 0; tps_op=tps_operation(specs,"recuperation")
                    tps_si=tps+tps_tr+tps_op+(rr["duration_min"] or 0)
                    if batch and tps_si>MAX_TRAVAIL_MIN:
                        _save_recup(batch,plat,pos,depot,gcache,rc,tournees,tour_id,zone)
                        tour_id+=1; batch=[]; plat=Plateau2D(); tps=0.0; pos=depot; heure=HEURE_DEBUT_MIN
                        ra=get_route(depot,c,rc); tps_tr=ra["duration_min"] or 0
                        _save_recup(batch,plat,pos,depot,gcache,rc,tournees,tour_id,zone)
                        tour_id+=1; batch=[]; plat=Plateau2D(); tps=0.0; pos=depot; heure=HEURE_DEBUT_MIN
                        ra=get_route(depot,c,rc); tps_tr=ra["duration_min"] or 0
                    r.update({"_dist":ra["distance_km"],"_dur":tps_tr+tps_op,"_pause":0,
                              "_heure":fmt_h(heure+tps_tr),"_phase":"recuperation","_zone":zone})
                    plat.ajouter(specs); tps+=tps_tr+tps_op; heure+=tps_tr+tps_op
                    r["_lon"]=round(plat.longueur_totale(),2); r["_pds"]=round(plat.poids,2)
                    pos=c or pos; batch.append(r)
                if batch:
                    _save_recup(batch,plat,pos,depot,gcache,rc,tournees,tour_id,zone)
                    tour_id+=1

    return tournees

    return tournees

def _close_tour_v8(batch, recups_proches, lointaines_rest,
                   gcache, rc, depot, pos, tps, heure,
                   plat_liv: "Plateau2D", tournees, tour_id, zone):
    """
    Clôture un tour en deux phases :
    Phase A : récupérations proches sur le chemin de retour (comportement standard)
    Phase B : récupération lointaine en DERNIER ARRÊT si le temps le permet
              → chauffeur rentre chargé, journée terminée
    """
    tps_rest  = MAX_TRAVAIL_MIN - tps
    lon_liv   = plat_liv.longueur_totale()
    pds_liv   = plat_liv.poids
    # Plateau vide pour les récups (livraisons terminées)
    plat_recups = Plateau2D()

    # ── Phase A : récups proches normales
    recups_sel = select_recups(pos, depot, recups_proches, gcache, rc, tps_rest, plat_recups)
    for r in recups_sel:
        if r in recups_proches: recups_proches.remove(r)

    # Calculer position et temps après les récups proches
    pos_r=pos; heure_r=heure; lon_r=pds_r=0.0; tps_apres_proches=tps
    for r in recups_sel:
        c=gcache.get(r["full_adresse"]); specs=get_specs(r["machine"])
        ra=get_route(pos_r,c,rc); tps_tr=ra["duration_min"] or 0
        tps_op=tps_operation(specs,"recuperation")
        r.update({"_dist":r.get("_dist_r") or ra["distance_km"],
                  "_dur":r.get("_dur_r") or (tps_tr+tps_op),
                  "_pause":0,"_heure":fmt_h(heure_r+tps_tr),
                  "_phase":"recuperation","_zone":zone})
        lon_r+=specs["longueur"]; pds_r+=specs["poids"]
        r["_lon"]=round(lon_r,2); r["_pds"]=round(pds_r,2)
        pos_r=c or pos_r; heure_r+=tps_tr+tps_op
        tps_apres_proches+=tps_tr+tps_op

    # ── Phase B : récupération lointaine en dernier arrêt
    #    Plateau vide après livraisons = peut charger une machine lointaine
    #    On cherche la lointaine la plus proche de la position actuelle
    recup_loint = None
    if lointaines_rest:
        tps_rest_b = MAX_TRAVAIL_MIN - tps_apres_proches
        recup_loint = select_recup_lointaine(
            lointaines_rest, pos_r, depot,
            gcache, rc, tps_rest_b,
            plat_recups   # état plateau après récups proches
        )
        if recup_loint:
            if recup_loint in lointaines_rest: lointaines_rest.remove(recup_loint)
            c     = gcache.get(recup_loint["full_adresse"])
            specs = get_specs(recup_loint["machine"])
            tps_tr= recup_loint.get("_dist_r") and 0 or (get_route(pos_r,c,rc)["duration_min"] or 0)
            tps_tr= get_route(pos_r, c, rc)["duration_min"] or 0
            tps_op= tps_operation(specs, "recuperation")
            recup_loint.update({
                "_dist":  recup_loint.get("_dist_r") or get_route(pos_r,c,rc)["distance_km"],
                "_dur":   recup_loint.get("_dur_r")  or (tps_tr+tps_op),
                "_pause": 0,
                "_heure": fmt_h(heure_r+tps_tr),
                "_phase": "recuperation",
                "_zone":  zone,
            })
            lon_l = specs["longueur"]; pds_l = specs["poids"]
            recup_loint["_lon"] = round(lon_r+lon_l, 2)
            recup_loint["_pds"] = round(pds_r+pds_l, 2)
            pos_r   = c or pos_r
            heure_r+= tps_tr+tps_op
            print(f"  🏁 Récup lointaine '{recup_loint.get('client','?')}' "
                  f"→ dernier arrêt Tour {tour_id} ({recup_loint.get('ville','?')})")

    all_recups = recups_sel + ([recup_loint] if recup_loint else [])
    rr = get_route(pos_r, depot, rc); dist_ret = rr["distance_km"] or 0
    dist_tot = sum((m.get("_dist") or 0) for m in batch+all_recups)+dist_ret
    charge   = "CHARGÉ" if all_recups else "À VIDE"
    print(f"  ✓ Tour {tour_id} [{zone}] : {len(batch)}🚚+{len(all_recups)}📦 | "
          f"{round(dist_tot,1)}km | {charge} | plat {round(lon_liv/PLATEAU_LONGUEUR_MAX_M*100,1)}%")
    _save_tour(tour_id, batch, all_recups, dist_tot, dist_ret, lon_liv, pds_liv, charge, zone, tournees)

def _save_recup(batch, plat: "Plateau2D", pos,depot,gcache,rc,tournees,tour_id,zone):
    rr=get_route(pos,depot,rc); dist_ret=rr["distance_km"] or 0
    dist_tot=sum((m.get("_dist") or 0) for m in batch)+dist_ret
    print(f"  📦 Tour {tour_id} [{zone}] récup : {len(batch)} missions | {round(dist_tot,1)}km | {plat.resume()}")
    _save_tour(tour_id,[],batch,dist_tot,dist_ret,plat.longueur_totale(),plat.poids,"CHARGÉ",zone,tournees)

def choisir_camion(longueur_m: float, poids_t: float, largeur_max_m: float = 0) -> dict:
    """
    Sélection automatique du camion adapté.
    v10 : préfère le porteur 19T (moins cher) si la charge le permet.

    Règles :
    - Porteur 19T : si poids ≤ 18T (marge 1T) ET longueur ≤ 8.5m (marge 0.5m)
    - Semi 25T : sinon
    - SURCHARGE : si même le semi ne peut pas accueillir
    """
    porteur = CAMIONS_FLOTTE["porteur_19t"]
    semi    = CAMIONS_FLOTTE["semi_25t"]

    # Vérifier qu'on tient dans le porteur (avec marge sécurité)
    if (poids_t <= porteur["ptac_t"] - 1.0
        and longueur_m <= porteur["longueur_m"] - 0.5):
        return {**porteur, "id": "porteur_19t", "surcharge": False}

    # Sinon semi
    if (poids_t <= semi["ptac_t"]
        and longueur_m <= semi["longueur_m"]):
        return {**semi, "id": "semi_25t", "surcharge": False}

    # Dépassement → on retourne le semi avec drapeau surcharge
    return {**semi, "id": "semi_25t", "surcharge": True}


def _save_tour(tid,livs,recs,dist,dist_ret,lon,pds,charge,zone,tournees):
    for m in livs+recs: m["_tour_id"]=tid

    # ── Sélection automatique du camion adapté (v11)
    largeur_max = 0.0
    for m in livs + recs:
        specs = get_specs(m.get("machine", ""))
        larg = specs.get("largeur", 0) if specs else 0
        if larg > largeur_max:
            largeur_max = larg

    camion = choisir_camion(lon, pds, largeur_max)

    # ── v11 : Vérification HARD — un tour ne peut jamais dépasser 100%
    #         Si longueur > lon_max ou poids > ptac, c'est une erreur moteur
    lon_max   = camion["longueur_m"]
    ptac_max  = camion["ptac_t"]
    taux_lon  = round(lon / lon_max * 100, 1)
    taux_pds  = round(pds / ptac_max * 100, 1)

    if lon > lon_max + 0.05 or pds > ptac_max + 0.1:
        # Signaler clairement — ne pas masquer avec un simple flag
        print(f"  🔴 ERREUR MOTEUR Tour {tid} : plateau={lon:.2f}m/{lon_max}m "
              f"({taux_lon}%) poids={pds:.2f}T/{ptac_max}T ({taux_pds}%)")
        print(f"       → Ce tour a été créé avec des machines qui ne tiennent pas.")
        print(f"       → Vérifier get_specs() ou les contraintes d'ajout.")
        charge = "SURCHARGE ⚠️"
    elif camion["surcharge"]:
        print(f"  ⚠️  Tour {tid} EN SURCHARGE : {lon:.1f}m / {pds:.2f}T "
              f"→ dépasse PTAC max {camion['ptac_t']}T ou longueur {camion['longueur_m']}m")
        charge = "SURCHARGE"

    tournees.append({"tour_id":tid,"livraisons":livs,"recups":recs,"zone":zone,
        "type_camion": camion["id"],
        "camion_label": camion["label"],
        "camion_ptac_t": camion["ptac_t"],
        "camion_longueur_m": camion["longueur_m"],
        "stats":{"nb_liv":len(livs),"nb_rec":len(recs),"dist_km":round(dist,1),
                 "dist_ret":dist_ret or 0,
                 "taux_lon":taux_lon,
                 "taux_pds":taux_pds,
                 "longueur_m": round(lon, 2),
                 "poids_t": round(pds, 2),
                 "charge":charge}})


# ────────────────────────────────────────────────────────────────
#  AFFECTATION MULTI-CHAUFFEURS — Bin-Packing équilibré
# ────────────────────────────────────────────────────────────────
def _tps_reel_tour(t: dict) -> int:
    """
    Calcule le temps RÉEL d'un tour :
    - Temps trajets (depuis les distances ORS stockées dans chaque mission)
    - Temps opérations sur site (déjà dans _dur)
    - Temps retour dépôt (dist_ret / vitesse moyenne)
    Un chauffeur roule en moyenne à 60 km/h hors agglomération.
    """
    VITESSE_MOY_KM_MIN = 60 / 60   # 1 km/min = 60 km/h

    tps_missions = sum((m.get("_dur") or 0) for m in t["livraisons"] + t["recups"])
    # Le trajet retour n'est pas dans les missions, on l'estime depuis dist_ret
    dist_ret = t["stats"].get("dist_ret") or 0
    tps_retour = int(dist_ret / VITESSE_MOY_KM_MIN) if dist_ret else 0

    return tps_missions + tps_retour


def affecter_chauffeurs(tournees: list, nb_chauffeurs: int) -> list:
    """
    Affectation multi-chauffeurs avec Bin-Packing First-Fit Decreasing :

    1. Calcule le temps RÉEL de chaque tour (trajets + opérations + retour dépôt)
    2. Trie les tours du plus long au plus court (FFD)
    3. Pour chaque tour, cherche le premier chauffeur qui peut l'absorber
       dans sa journée de 8h (cumul + ce tour ≤ MAX_TRAVAIL_MIN)
    4. Si aucun chauffeur ne peut l'absorber → créer un nouveau chauffeur
       ET avertir que le nombre demandé est insuffisant

    Un chauffeur fait PLUSIEURS tours consécutifs dans sa journée.
    Entre deux tours : retour dépôt, rechargement, redépart.
    """
    if nb_chauffeurs < 1: nb_chauffeurs = 1

    # ── Calcul du temps réel de chaque tour
    for t in tournees:
        t["_tps_reel"] = _tps_reel_tour(t)

    # Diagnostic avant affectation
    total_tps = sum(t["_tps_reel"] for t in tournees)
    tps_min_chauf = math.ceil(total_tps / MAX_TRAVAIL_MIN)
    print(f"  Temps total toutes missions : {total_tps//60}h{total_tps%60:02d}")
    print(f"  Journée par chauffeur       : {MAX_TRAVAIL_MIN//60}h max (05h→13h)")
    print(f"  Minimum réel nécessaire     : {tps_min_chauf} chauffeur(s)")
    print(f"  Chauffeurs demandés         : {nb_chauffeurs}")
    if tps_min_chauf > nb_chauffeurs:
        print(f"")
        print(f"  ⚠️  ATTENTION : {nb_chauffeurs} chauffeur(s) insuffisant(s) pour ces missions.")
        print(f"     Il faut au minimum {tps_min_chauf} chauffeurs pour couvrir {total_tps//60}h")
        print(f"     de travail en journées de {MAX_TRAVAIL_MIN//60}h.")
        print(f"     → {tps_min_chauf - nb_chauffeurs} chauffeur(s) supplémentaire(s) ajouté(s).")
    else:
        print(f"  ✅ {nb_chauffeurs} chauffeur(s) suffisant(s) — optimisation en cours...")

    # ── Tri FFD : tours les plus longs en premier
    tours_tries = sorted(tournees, key=lambda t: t["_tps_reel"], reverse=True)

    # ── État chauffeurs
    chauf = [{"id": i+1, "nom": f"Chauffeur {i+1}",
              "km": 0.0, "tps": 0, "tours": [],
              "planning": []}           # liste des tours dans l'ordre chronologique
             for i in range(nb_chauffeurs)]

    for t in tours_tries:
        tps_t = t["_tps_reel"]
        # Chercher un chauffeur qui peut absorber ce tour
        candidats = [c for c in chauf if c["tps"] + tps_t <= MAX_TRAVAIL_MIN]

        if not candidats:
            new_id = len(chauf) + 1
            print(f"  ➕ Chauffeur {new_id} ajouté "
                  f"(journée 8h insuffisante pour {nb_chauffeurs} chauffeurs)")
            chauf.append({"id": new_id, "nom": f"Chauffeur {new_id}",
                          "km": 0.0, "tps": 0, "tours": [], "planning": []})
            candidats = [chauf[-1]]

        # Affecter au chauffeur le moins chargé (en temps) parmi les candidats
        choisi = min(candidats, key=lambda c: c["tps"])
        choisi["tours"].append(t["tour_id"])
        choisi["km"]     += t["stats"]["dist_km"]
        choisi["tps"]    += tps_t
        choisi["planning"].append({
            "tour_id": t["tour_id"],
            "depart":  fmt_h(HEURE_DEBUT_MIN + choisi["tps"] - tps_t),
            "duree":   tps_t,
        })

        t["chauffeur_id"]  = choisi["id"]
        t["chauffeur_nom"] = choisi["nom"]
        for m in t["livraisons"] + t["recups"]:
            m["_chauffeur_id"]  = choisi["id"]
            m["_chauffeur_nom"] = choisi["nom"]

    # ── Résumé
    print(f"\n  Répartition finale :")
    print(f"  {'Chauffeur':<15} {'Tours':<8} {'Km':<10} {'Temps':<10} {'Charge'}")
    print("  " + "-"*55)
    for c in chauf:
        if not c["tours"]: continue
        h = c["tps"]//60; mn = c["tps"]%60
        charge_pct = round(c["tps"]/MAX_TRAVAIL_MIN*100)
        barre = "█" * (charge_pct // 10) + "░" * (10 - charge_pct // 10)
        print(f"  {c['nom']:<15} {len(c['tours']):<8} "
              f"{round(c['km'],1):<10} {h}h{mn:02d}      "
              f"|{barre}| {charge_pct}%")

    return chauf


# ────────────────────────────────────────────────────────────────
#  RENTABILITÉ — v9 : prix par mission selon zone géographique
# ────────────────────────────────────────────────────────────────
def calcul_rentabilite(tournees, result_df, gcache=None, rc=None):
    """
    Calcule le CA, le coût et la marge de chaque tournée.
    v9 : le prix de chaque mission est désormais déterminé par la zone
    tarifaire (distance routière depuis Lieusaint) et non plus par un
    prix fixe livraison/récup.

    Si gcache/rc ne sont pas fournis, on retombe sur le calcul forfaitaire
    (compatibilité ascendante).
    """
    use_zones = gcache is not None
    if use_zones and rc is None:
        rc = load_cache(ROUTE_CACHE_FILE)
    depot = gcache.get(DEPOT_ADDRESS) if use_zones else None

    rows = []
    for t in tournees:
        s = t["stats"]; dist = s["dist_km"]

        # ── Chiffre d'affaires : grille zones ou forfait
        if use_zones and depot:
            ca = 0.0
            for m in t.get("livraisons", []) + t.get("recups", []):
                addr = m.get("full_adresse")
                coords = gcache.get(addr) if addr else None
                if coords:
                    route = get_route(depot, coords, rc)
                    dist_aller = route["distance_km"] or 0
                else:
                    dist_aller = None
                prix, zone_num, _ = prix_mission_par_zone(dist_aller)
                ca += prix
                # On enregistre la zone/prix sur la mission pour traçabilité
                m["_zone_tarif"]  = zone_num
                m["_prix_mission"] = prix
            ca = round(ca, 2)
        else:
            ca = s["nb_liv"]*PRIX_LIVRAISON_DEF + s["nb_rec"]*PRIX_RECUP_DEF

        # ── Coûts (inchangé)
        carb = round(dist/100*CONSO_L_100KM*PRIX_LITRE_EUR, 2)
        missions = result_df[result_df["tour_id"]==t["tour_id"]]
        tps_h    = round(missions["duration_min"].fillna(0).sum()/60, 2)
        cout_ch  = round(tps_h*COUT_HEURE_CHAUF, 2)
        cout_tot = round(carb+cout_ch, 2)
        marge    = round(ca-cout_tot, 2)

        rows.append({
            "tour_id": t["tour_id"], "zone": t["zone"],
            "chauffeur": t.get("chauffeur_nom","?"),
            "nb_missions": s["nb_liv"]+s["nb_rec"],
            "ca_estime_eur": ca,
            "cout_carb_eur": carb,
            "cout_chauf_eur": cout_ch,
            "cout_total_eur": cout_tot,
            "marge_eur": marge,
            "taux_marge_pct": round(marge/ca*100,1) if ca>0 else 0,
            "retour_charge": s["charge"],
        })
    return pd.DataFrame(rows)

def to_df(tournees):
    rows=[]
    for t in tournees:
        for m in t["livraisons"]+t["recups"]:
            rows.append({
                "tour_id":m["_tour_id"],"zone":m.get("_zone","?"),
                "chauffeur_id":m.get("_chauffeur_id","?"),
                "chauffeur_nom":m.get("_chauffeur_nom","?"),
                "phase":m["_phase"],"heure_arrivee":m["_heure"],
                "pause_min":m.get("_pause",0),
                "type_mission":m.get("type_mission",""),
                "client":m.get("client",""),"machine":m.get("machine",""),
                "ville":m.get("ville",""),"full_adresse":m.get("full_adresse",""),
                "date":m.get("date",""),"distance_km":m.get("_dist"),
                "duration_min":m.get("_dur"),
                "plateau_longueur_m":m.get("_lon"),"plateau_poids_t":m.get("_pds"),
                "retour_charge":t["stats"]["charge"],
            })
    return pd.DataFrame(rows).reset_index(drop=True)


# ────────────────────────────────────────────────────────────────
#  PDF CHAUFFEUR — sans prix, orienté terrain
# ────────────────────────────────────────────────────────────────
def _pdf_styles():
    styles = getSampleStyleSheet()
    s = lambda name,**kw: ParagraphStyle(name,parent=styles["Normal"],**kw)
    return {
        "titre":   s("t",fontSize=16,textColor=colors.HexColor("#1A237E"),
                     fontName="Helvetica-Bold",spaceAfter=4,alignment=TA_CENTER),
        "sous":    s("st",fontSize=9,textColor=colors.gray,
                     spaceAfter=8,alignment=TA_CENTER),
        "entete":  s("eh",fontSize=12,textColor=colors.white,
                     backColor=colors.HexColor("#1565C0"),fontName="Helvetica-Bold",
                     leftIndent=8,spaceBefore=10,spaceAfter=4),
        "entete_r":s("ehr",fontSize=12,textColor=colors.white,
                     backColor=colors.HexColor("#B71C1C"),fontName="Helvetica-Bold",
                     leftIndent=8,spaceBefore=10,spaceAfter=4),
        "normal":  s("n",fontSize=9,spaceAfter=2),
        "small":   s("sm",fontSize=8,textColor=colors.gray,spaceAfter=1),
        "alerte":  s("al",fontSize=9,textColor=colors.HexColor("#B71C1C"),
                     backColor=colors.HexColor("#FFEBEE"),spaceBefore=4,spaceAfter=4),
        "info":    s("inf",fontSize=9,textColor=colors.HexColor("#1B5E20"),
                     backColor=colors.HexColor("#E8F5E9"),spaceBefore=2,spaceAfter=2),
        "bold":    s("b",fontSize=10,fontName="Helvetica-Bold",spaceAfter=3),
    }

def _page_num(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica",8); canvas.setFillColor(colors.gray)
    canvas.drawRightString(A4[0]-1.5*cm,0.7*cm,f"Page {canvas.getPageNumber()}")
    canvas.drawString(1.5*cm,0.7*cm,"USAGE INTERNE — NE PAS DIFFUSER")
    canvas.restoreState()

def export_pdf_chauffeur(tournees, chauffeurs, gcache, output_path="feuille_route_chauffeurs_v8.pdf"):
    """
    PDF chauffeur : 1 section par chauffeur, 1 page par tour.
    Sans aucun prix — uniquement informations terrain.
    """
    doc = SimpleDocTemplate(output_path,pagesize=A4,
                            leftMargin=1.5*cm,rightMargin=1.5*cm,
                            topMargin=1.5*cm,bottomMargin=1.5*cm)
    ST  = _pdf_styles()
    story = []

    for chauf in chauffeurs:
        if not chauf["tours"]: continue
        tours_chauf = [t for t in tournees if t["tour_id"] in chauf["tours"]]

        # ── En-tête chauffeur
        story.append(Paragraph(f"FEUILLE DE ROUTE — {chauf['nom'].upper()}", ST["titre"]))
        story.append(Paragraph(f"{DEPOT_NOM}  |  Départ : {fmt_h(HEURE_DEBUT_MIN)}  |  "
                                f"Fin prévue : {fmt_h(HEURE_FIN_MIN)}", ST["sous"]))

        # Récap du chauffeur
        h=chauf["tps"]//60; mn=chauf["tps"]%60
        recap = [["Tours","Missions","Km total","Durée estimée","Départ","Retour prévu"],
                 [str(len(chauf["tours"])),
                  str(sum(t["stats"]["nb_liv"]+t["stats"]["nb_rec"] for t in tours_chauf)),
                  f"{round(chauf['km'],1)} km",
                  f"{h}h{mn:02d}",
                  fmt_h(HEURE_DEBUT_MIN),
                  fmt_h(HEURE_DEBUT_MIN+chauf["tps"])]]
        tbl=Table(recap,colWidths=[2.5*cm]*6)
        tbl.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#1A237E")),
            ("TEXTCOLOR",(0,0),(-1,0),colors.white),
            ("FONTSIZE",(0,0),(-1,-1),9),("ALIGN",(0,0),(-1,-1),"CENTER"),
            ("GRID",(0,0),(-1,-1),0.3,colors.lightgrey),
            ("BACKGROUND",(0,1),(-1,1),colors.HexColor("#E8EAF6")),
            ("FONTNAME",(0,1),(-1,1),"Helvetica-Bold"),
        ]))
        story.append(tbl); story.append(Spacer(1,0.3*cm))

        # Instructions sécurité
        story.append(Paragraph(
            "⚠ RAPPELS TERRAIN : Vérifier les sangles avant départ | "
            "Respecter les horaires clients | Signaler tout incident au dépôt",
            ST["alerte"]))
        story.append(Spacer(1,0.2*cm))

        for t in tours_chauf:
            s=t["stats"]; tid=t["tour_id"]
            is_liv_tour = s["nb_liv"] > 0
            style_entete = ST["entete"] if is_liv_tour else ST["entete_r"]
            icone = "🚚" if is_liv_tour else "📦"
            charge_label = "RETOUR CHARGÉ" if "CHARG" in str(s["charge"]) else "RETOUR À VIDE"

            story.append(Paragraph(
                f"  {icone} TOUR {tid} — Zone {t['zone']} — "
                f"{s['nb_liv']} livraison(s) + {s['nb_rec']} récupération(s)",
                style_entete))

            # Métriques tour sans prix
            met = [["Distance","Plateau","Retour","Durée estimée"],
                   [f"{s['dist_km']} km",
                    f"{s['taux_lon']}% long. / {s['taux_pds']}% pds",
                    charge_label,
                    fmt_h(sum((m.get("_dur") or 0) for m in t["livraisons"]+t["recups"]))]]
            mt=Table(met,colWidths=[4*cm,4.5*cm,4*cm,3.5*cm])
            mt.setStyle(TableStyle([
                ("FONTSIZE",(0,0),(-1,-1),8),("ALIGN",(0,0),(-1,-1),"CENTER"),
                ("FONTNAME",(0,0),(-1,0),"Helvetica"),
                ("FONTNAME",(0,1),(-1,1),"Helvetica-Bold"),
                ("TEXTCOLOR",(0,0),(-1,0),colors.gray),
                ("BACKGROUND",(0,1),(-1,1),colors.HexColor("#E3F2FD")),
                ("GRID",(0,0),(-1,-1),0.3,colors.lightgrey),
            ]))
            story.append(mt); story.append(Spacer(1,0.2*cm))
            story.append(Paragraph(f"Départ DÉPÔT — {fmt_h(HEURE_DEBUT_MIN)}", ST["small"]))
            story.append(HRFlowable(width="100%",thickness=0.5,color=colors.lightgrey))

            all_m = t["livraisons"]+t["recups"]
            for idx,m in enumerate(all_m):
                phase=m["_phase"]; is_liv=phase=="livraison"
                bg=colors.HexColor("#E3F2FD") if is_liv else colors.HexColor("#FFF3E0")
                txt=colors.HexColor("#0D47A1") if is_liv else colors.HexColor("#E65100")
                heure=m.get("_heure","?")
                fleche="⬇ LIVRER" if is_liv else "⬆ RÉCUPÉRER"
                if m.get("_pause",0):
                    story.append(Paragraph(
                        f"⏸ PAUSE RÉGLEMENTAIRE {TPS_PAUSE_MIN} min",ST["alerte"]))

                row_data=[[
                    Paragraph(f"<b>{idx+1}. {heure}</b>",
                              ParagraphStyle("hh",fontSize=11,textColor=txt,fontName="Helvetica-Bold")),
                    Paragraph(f"<b>{fleche}</b>",
                              ParagraphStyle("ff",fontSize=9,textColor=txt,fontName="Helvetica-Bold")),
                    Paragraph(f"<b>{m.get('client','?')}</b>",
                              ParagraphStyle("cc",fontSize=9,fontName="Helvetica-Bold")),
                    Paragraph(f"{m.get('adresse','?')}<br/>{m.get('ville','?')}",
                              ParagraphStyle("aa",fontSize=8,textColor=colors.gray)),
                    Paragraph(f"Machine :<br/><b>{m.get('machine','?')}</b>",
                              ParagraphStyle("mm",fontSize=8)),
                    Paragraph(f"Plateau :<br/><b>{m.get('_lon','?')}m / {m.get('_pds','?')}T</b>",
                              ParagraphStyle("pp",fontSize=8)),
                ]]
                mt2=Table(row_data,colWidths=[1.5*cm,2.2*cm,3.5*cm,3.8*cm,3.0*cm,2.0*cm])
                mt2.setStyle(TableStyle([
                    ("BACKGROUND",(0,0),(-1,-1),bg),
                    ("GRID",(0,0),(-1,-1),0.3,colors.lightgrey),
                    ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                    ("TOPPADDING",(0,0),(-1,-1),5),
                    ("BOTTOMPADDING",(0,0),(-1,-1),5),
                ]))
                story.append(KeepTogether([mt2,Spacer(1,0.1*cm)]))

            # Heure retour estimée
            last=all_m[-1] if all_m else None
            if last:
                try:
                    lh=last["_heure"]; h2,mn2=int(lh[:2]),int(lh[3:])
                    ret_min=h2*60+mn2+(last.get("_dur") or 0)+int((s.get("dist_ret",30)))
                    ret_str=fmt_h(ret_min)
                except: ret_str="?"
            else: ret_str="?"
            story.append(HRFlowable(width="100%",thickness=0.5,color=colors.lightgrey))
            story.append(Paragraph(
                f"Retour DÉPÔT estimé : {ret_str} — {charge_label} — "
                f"Tél. dépôt : {DEPOT_TEL}",ST["small"]))
            story.append(Spacer(1,0.3*cm))

        story.append(PageBreak())

    doc.build(story,onFirstPage=_page_num,onLaterPages=_page_num)
    print(f"  PDF chauffeurs : {output_path}")


# ────────────────────────────────────────────────────────────────
#  PDF TRANSPORT (responsable) — avec prix
# ────────────────────────────────────────────────────────────────
def export_pdf_transport(tournees, chauffeurs, rent_df,
                         output_path="rapport_transport_v8.pdf"):
    doc = SimpleDocTemplate(output_path,pagesize=A4,
                            leftMargin=1.5*cm,rightMargin=1.5*cm,
                            topMargin=1.5*cm,bottomMargin=1.5*cm)
    ST  = _pdf_styles()
    story = []

    story.append(Paragraph("RAPPORT TRANSPORT", ST["titre"]))
    story.append(Paragraph(f"{DEPOT_NOM} — Optimiseur v8", ST["sous"]))
    story.append(Spacer(1,0.3*cm))

    # Résumé global
    total_dist = sum(t["stats"]["dist_km"] for t in tournees)
    total_ca   = rent_df["ca_estime_eur"].sum()
    total_cout = rent_df["cout_total_eur"].sum()
    total_marge= rent_df["marge_eur"].sum()
    taux_marge = round(total_marge/total_ca*100,1) if total_ca>0 else 0

    glob=[["Tournées","Missions","Km","CA","Coût","Marge","Tx marge","Chauffeurs"],
          [str(len(tournees)),
           str(sum(t["stats"]["nb_liv"]+t["stats"]["nb_rec"] for t in tournees)),
           f"{round(total_dist,0)} km",
           f"{total_ca:.0f} EUR",f"{total_cout:.0f} EUR",
           f"{total_marge:.0f} EUR",f"{taux_marge}%",
           str(len(chauffeurs))]]
    gt=Table(glob,colWidths=[2.2*cm]*8)
    gt.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#1A237E")),
        ("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("FONTSIZE",(0,0),(-1,-1),8),("ALIGN",(0,0),(-1,-1),"CENTER"),
        ("GRID",(0,0),(-1,-1),0.3,colors.lightgrey),
        ("BACKGROUND",(0,1),(-1,1),colors.HexColor("#E8EAF6")),
        ("FONTNAME",(0,1),(-1,1),"Helvetica-Bold"),
    ]))
    story.append(gt); story.append(Spacer(1,0.4*cm))

    # Répartition par chauffeur
    story.append(Paragraph("Répartition chauffeurs", ST["bold"]))
    ch_data=[["Chauffeur","Tours","Km","Durée"]]
    for c in chauffeurs:
        if not c["tours"]: continue
        h=c["tps"]//60; mn=c["tps"]%60
        ch_data.append([c["nom"],str(len(c["tours"])),
                        f"{round(c['km'],1)} km",f"{h}h{mn:02d}"])
    ct=Table(ch_data,colWidths=[5*cm,3*cm,4*cm,4*cm])
    ct.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#283593")),
        ("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("FONTSIZE",(0,0),(-1,-1),9),("ALIGN",(0,0),(-1,-1),"CENTER"),
        ("GRID",(0,0),(-1,-1),0.3,colors.lightgrey),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F5F5F5")]),
    ]))
    story.append(ct); story.append(Spacer(1,0.4*cm))

    # Détail rentabilité par tour
    story.append(Paragraph("Rentabilité par tournée", ST["bold"]))
    rent_hdr=[["Tour","Zone","Chauffeur","Missions","CA","Coût","Marge","Tx%","Retour"]]
    for _,row in rent_df.iterrows():
        ch="CHARGÉ" if "CHARG" in str(row["retour_charge"]) else "vide"
        bg_m=colors.HexColor("#FFEBEE") if row["marge_eur"]<0 else colors.white
        rent_hdr.append([
            str(int(row["tour_id"])),row["zone"],row["chauffeur"],
            str(int(row["nb_missions"])),
            f"{row['ca_estime_eur']:.0f}",f"{row['cout_total_eur']:.0f}",
            f"{row['marge_eur']:.0f}",f"{row['taux_marge_pct']}%",ch
        ])
    rt=Table(rent_hdr,colWidths=[1.2*cm,1.6*cm,3.2*cm,1.8*cm,2*cm,2*cm,2*cm,1.5*cm,2*cm])
    styles_rt=[
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#283593")),
        ("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("FONTSIZE",(0,0),(-1,-1),8),("ALIGN",(0,0),(-1,-1),"CENTER"),
        ("GRID",(0,0),(-1,-1),0.3,colors.lightgrey),
    ]
    for i,(_, row) in enumerate(rent_df.iterrows(),start=1):
        if row["marge_eur"] < 0:
            styles_rt.append(("BACKGROUND",(0,i),(-1,i),colors.HexColor("#FFEBEE")))
    rt.setStyle(TableStyle(styles_rt))
    story.append(rt)

    doc.build(story,onFirstPage=_page_num,onLaterPages=_page_num)
    print(f"  PDF transport  : {output_path}")


# ────────────────────────────────────────────────────────────────
#  ESTIMATEUR COMMERCIAL — v9 : grille tarifaire par zone
# ────────────────────────────────────────────────────────────────
def estimer_prix(adresse_client: str, nb_machines: int,
                 type_mission: str = "livraison",
                 urgence: bool = False,
                 gcache: dict = None, rc: dict = None) -> dict:
    """
    Estime le prix de transport pour un commercial.
    v9 : le tarif est désormais déterminé par la zone géographique
    (distance routière aller depuis Lieusaint) selon la grille
    GRILLE_TARIFS_ZONES. Le prix est identique pour livraison ou récup,
    et ne dépend pas du type de machine.
    """
    if gcache is None: gcache = load_cache(GEOCODE_CACHE_FILE)
    if rc     is None: rc     = load_cache(ROUTE_CACHE_FILE)

    print(f"\n  === ESTIMATEUR COMMERCIAL v9 — TARIF PAR ZONE ===")
    print(f"  Adresse   : {adresse_client}")
    print(f"  Machines  : {nb_machines} x {type_mission}")
    print(f"  Urgence   : {'OUI' if urgence else 'non'}")

    depot = gcache.get(DEPOT_ADDRESS) or geocode(DEPOT_ADDRESS, gcache)
    dest  = gcache.get(adresse_client) or geocode(adresse_client, gcache)

    if not dest:
        print("  ❌ Adresse non géocodable")
        return {"erreur": "Adresse introuvable"}

    # Distance routière aller (sert à déterminer la zone)
    route_aller  = get_route(depot, dest, rc)
    route_retour = get_route(dest, depot, rc)
    dist_aller   = route_aller["distance_km"] or 0
    dist_ar      = dist_aller + (route_retour["distance_km"] or 0)
    tps_min      = (route_aller["duration_min"] or 0) + (route_retour["duration_min"] or 0)

    # → Détermination de la zone et du tarif unitaire
    prix_unit, zone_num, libelle = prix_mission_par_zone(dist_aller)

    # Prix total : tarif zone × nb_machines, éventuellement majoré urgence
    prix_ht_base = prix_unit * nb_machines
    prix_ht      = round(prix_ht_base * (TARIF_URGENCE_MULT if urgence else 1.0), 2)
    prix_ttc     = round(prix_ht * 1.20, 2)
    fourchette   = (round(prix_ht*0.95, 0), round(prix_ht*1.05, 0))

    # Coût interne pour calcul marge
    carb_cout   = round(dist_ar/100*CONSO_L_100KM*PRIX_LITRE_EUR, 2)
    chauf_cout  = round(tps_min/60*COUT_HEURE_CHAUF, 2)
    cout_int    = round(carb_cout+chauf_cout, 2)
    marge       = round(prix_ht-cout_int, 2)
    taux_marge  = round(marge/prix_ht*100,1) if prix_ht>0 else 0

    print(f"\n  Distance aller : {round(dist_aller,1)} km")
    print(f"  Distance A/R   : {round(dist_ar,1)} km")
    print(f"  → Zone tarifaire : {libelle}")
    print(f"  → Tarif unitaire : {prix_unit:.0f} EUR par machine")
    print(f"  Durée estimée  : {tps_min//60}h{tps_min%60:02d}")
    if urgence:
        print(f"  Majoration urg.: x{TARIF_URGENCE_MULT}")
    print(f"  ─────────────────────────────────────")
    print(f"  Prix HT estimé : {prix_ht} EUR ({nb_machines} machine(s))")
    print(f"  Prix TTC       : {prix_ttc} EUR")
    print(f"  Fourchette HT  : {fourchette[0]} – {fourchette[1]} EUR")
    print(f"  Coût interne   : {cout_int} EUR")
    print(f"  Marge brute    : {marge} EUR ({taux_marge}%)")
    print(f"  ============================")

    return {
        "adresse":adresse_client,"nb_machines":nb_machines,
        "type_mission":type_mission,"urgence":urgence,
        "dist_aller_km":round(dist_aller,1),
        "dist_km":round(dist_ar,1),"tps_min":tps_min,
        "zone":zone_num,"zone_libelle":libelle,
        "tarif_unitaire":prix_unit,
        "prix_ht":prix_ht,"prix_ttc":prix_ttc,
        "fourchette_ht":fourchette,"cout_interne":cout_int,
        "marge_eur":marge,"taux_marge_pct":taux_marge,
    }


# ────────────────────────────────────────────────────────────────
#  CARTE FOLIUM v8
# ────────────────────────────────────────────────────────────────
def make_map(result_df, gcache, tournees, chauffeurs):
    depot = gcache[DEPOT_ADDRESS]
    m     = folium.Map(location=[depot["lat"],depot["lng"]], zoom_start=10)
    folium.Marker([depot["lat"],depot["lng"]],
        popup=folium.Popup(f"<b>🏭 DÉPÔT<br>{DEPOT_NOM}</b>",max_width=200),
        icon=folium.Icon(color="black",icon="home",prefix="fa")).add_to(m)

    nb_tours = len(tournees)
    for i,row in result_df.iterrows():
        c=gcache.get(row["full_adresse"])
        if not c: continue
        tid=int(row["tour_id"]); color=TOUR_COLORS.get(tid,"gray")
        phase=row["phase"]; is_liv=phase=="livraison"
        bg=("#1565C0" if is_liv else "#BF360C")
        tl=round((row.get("plateau_longueur_m") or 0)/PLATEAU_LONGUEUR_MAX_M*100)
        tp=round((row.get("plateau_poids_t")    or 0)/PLATEAU_POIDS_MAX_T   *100)
        heure=row.get("heure_arrivee") or row.get("heure_arrivee_estimee") or "?"
        chauf=row.get("chauffeur_nom","?")

        popup_html=(
            f"<div style='font-family:Arial;font-size:12px;min-width:240px'>"
            f"<div style='background:{bg};color:white;padding:5px 8px;"
            f"border-radius:4px 4px 0 0;font-weight:bold'>"
            f"{'🚚' if is_liv else '📦'} Tour {tid}/{nb_tours} — Mission {i+1}</div>"
            f"<div style='padding:6px 8px;border:1px solid #ddd;border-top:none'>"
            f"<b>Chauffeur</b> : {chauf}<br>"
            f"<b>Client</b> : {row.get('client','?')}<br>"
            f"<b>Machine</b> : {row.get('machine','?')}<br>"
            f"<b>Arrivée</b> : <b style='color:{bg}'>{heure}</b><br>"
            f"<b>Distance</b> : {row.get('distance_km','?')} km | "
            f"<b>Durée site</b> : {row.get('duration_min','?')} min<br>"
            f"Plateau : {row.get('plateau_longueur_m','?')}m ({tl}%) | "
            f"{row.get('plateau_poids_t','?')}T ({tp}%)"
            f"</div></div>"
        )
        folium.CircleMarker([c["lat"],c["lng"]],radius=14,color="white",weight=2,
            fill=True,fill_color=color,fill_opacity=0.9,
            popup=folium.Popup(popup_html,max_width=280),
            tooltip=f"{'🚚' if is_liv else '📦'} T{tid} {chauf} — {row.get('client','?')} ({heure})"
        ).add_to(m)
        folium.Marker([c["lat"],c["lng"]],
            icon=folium.DivIcon(
                html=(f'<div style="font-size:9px;font-weight:bold;color:white;'
                      f'text-align:center;line-height:14px;pointer-events:none;">'
                      f'{"↓" if is_liv else "↑"}{i+1}</div>'),
                icon_size=(28,14),icon_anchor=(14,7))).add_to(m)

    for t in tournees:
        tid=t["tour_id"]; color=TOUR_COLORS.get(tid,"gray")
        pts_l=[[depot["lat"],depot["lng"]]]+[
            [gcache[r["full_adresse"]]["lat"],gcache[r["full_adresse"]]["lng"]]
            for r in t["livraisons"] if gcache.get(r["full_adresse"])]
        pts_r=([pts_l[-1]] if len(pts_l)>1 else [[depot["lat"],depot["lng"]]])+[
            [gcache[r["full_adresse"]]["lat"],gcache[r["full_adresse"]]["lng"]]
            for r in t["recups"] if gcache.get(r["full_adresse"])]+[[depot["lat"],depot["lng"]]]
        if t["recups"] and len(pts_r)>2:
            folium.PolyLine(pts_r,color=color,weight=2,opacity=0.55,
                dash_array="8 5",tooltip=f"T{tid} retour récup").add_to(m)
        else:
            pts_l.append([depot["lat"],depot["lng"]])
        if len(pts_l)>1:
            folium.PolyLine(pts_l,color=color,weight=5,opacity=0.9,
                tooltip=f"T{tid} [{t['zone']}] {t.get('chauffeur_nom','?')}").add_to(m)

    # Légende
    lg=""
    for t in tournees:
        s=t["stats"]; tid=t["tour_id"]; color=TOUR_COLORS.get(tid,"gray")
        ch="⬆CHARGÉ" if "CHARG" in str(s["charge"]) else "⬇vide"
        bg="#1B5E20" if "CHARG" in str(s["charge"]) else "#B71C1C"
        lg+=(f'<div style="display:flex;align-items:center;gap:5px;margin-bottom:2px">'
             f'<span style="background:{color};border-radius:50%;min-width:11px;'
             f'height:11px;display:inline-block"></span>'
             f'<span>T{tid}[{t["zone"]}] {t.get("chauffeur_nom","?")} | '
             f'{s["nb_liv"]}↓+{s["nb_rec"]}↑ | {s["dist_km"]}km | {s["taux_lon"]}% |'
             f'<span style="background:{bg};color:white;border-radius:3px;'
             f'padding:0 3px;font-size:9px;margin-left:2px">{ch}</span></span></div>')
    m.get_root().html.add_child(folium.Element(
        f'<div style="position:fixed;bottom:20px;left:20px;z-index:1000;background:white;'
        f'padding:10px 14px;border-radius:10px;border:2px solid #888;font-size:11px;'
        f'line-height:1.6;max-width:380px;box-shadow:2px 2px 8px rgba(0,0,0,0.2)">'
        f'<b>📍 {len(tournees)} tournée(s) | {len(result_df)} missions</b><br>'
        f'<span style="color:#555;font-size:9px">▬ livraison &nbsp; ╌ retour récup | '
        f'↓=livrer ↑=récupérer</span><br>'
        f'<div style="margin-top:5px">{lg}</div></div>'))

    all_lats=[depot["lat"]]+[gcache[r["full_adresse"]]["lat"]
              for r in result_df.to_dict("records") if gcache.get(r.get("full_adresse"))]
    all_lngs=[depot["lng"]]+[gcache[r["full_adresse"]]["lng"]
              for r in result_df.to_dict("records") if gcache.get(r.get("full_adresse"))]
    if all_lats:
        m.fit_bounds([[min(all_lats)-0.05,min(all_lngs)-0.05],
                      [max(all_lats)+0.05,max(all_lngs)+0.05]])
    return m


# ────────────────────────────────────────────────────────────────
#  KPI CONSOLE
# ────────────────────────────────────────────────────────────────
def print_kpi(tournees, result_df, rent_df, chauffeurs):
    dist=sum(t["stats"]["dist_km"] for t in tournees)
    carb=round(dist/100*CONSO_L_100KM,2); cout_c=round(carb*PRIX_LITRE_EUR,2)
    tps_h=round(result_df["duration_min"].fillna(0).sum()/60,1)
    nb=len(tournees)
    charges=sum(1 for t in tournees if "CHARG" in str(t["stats"]["charge"]))
    tlon=round(sum(t["stats"]["taux_lon"] for t in tournees)/nb,1)
    tpds=round(sum(t["stats"]["taux_pds"] for t in tournees)/nb,1)
    ca=rent_df["ca_estime_eur"].sum(); marge=rent_df["marge_eur"].sum()

    print("\n"+"="*70)
    print("  KPI FINAUX v8")
    print("="*70)
    print(f"  Missions          : {len(result_df)} | Tournées : {nb} | Chauffeurs : {len(chauffeurs)}")
    print(f"  Journée           : {fmt_h(HEURE_DEBUT_MIN)} → {fmt_h(HEURE_FIN_MIN)} ({MAX_TRAVAIL_MIN//60}h)")
    print(f"  Retours chargés   : {charges}/{nb} ({round(charges/nb*100)}%)")
    print(f"  Distance          : {round(dist,1)} km | Carburant : {carb}L → {cout_c} EUR")
    print(f"  CA estimé         : {ca:.0f} EUR | Marge : {marge:.0f} EUR "
          f"({round(marge/ca*100,1) if ca>0 else 0}%)")
    print(f"  Plateau moy.      : {tlon}% longueur / {tpds}% poids")
    print()
    print(f"  {'T':>2} {'Zone':>6} {'Chauffeur':>14} {'Liv':>4} {'Rec':>4} "
          f"{'km':>6} {'%lon':>6} {'Retour':>8} {'Marge':>8}")
    print("  "+"-"*72)
    for t in tournees:
        s=t["stats"]; tid=t["tour_id"]
        r=rent_df[rent_df["tour_id"]==tid]
        mg=f"{r['marge_eur'].iloc[0]:.0f}E" if len(r) else "-"
        ch=t.get("chauffeur_nom","?")
        print(f"  {tid:>2} {t['zone']:>6} {ch:>14} {s['nb_liv']:>4} {s['nb_rec']:>4} "
              f"{s['dist_km']:>6} {s['taux_lon']:>6}% {s['charge']:>8} {mg:>8}")
    print("="*70)


# ────────────────────────────────────────────────────────────────
#  PIPELINE PRINCIPAL
# ────────────────────────────────────────────────────────────────
def process_tour(file_name: str, nb_chauffeurs: int = 1) -> tuple:
    print("="*70)
    print(f"  OPTIMISEUR v12 | {nb_chauffeurs} chauffeur(s) | "
          f"{fmt_h(HEURE_DEBUT_MIN)}→{fmt_h(HEURE_FIN_MIN)}")
    print("="*70)

    df = pd.read_csv(file_name)
    df["code_postal"] = df["code_postal"].astype(str).str.zfill(5)
    df["full_adresse"] = df.apply(full_addr, axis=1)
    df["type_mission_norm"] = df["type_mission"].apply(
        lambda x: "recuperation" if str(x).lower().strip() in
                  ("recuperation","récupération","recup","récup") else "livraison")
    print(f"[1/7] {len(df)} missions chargées")

    gcache = load_cache(GEOCODE_CACHE_FILE)
    for addr in [DEPOT_ADDRESS]+df["full_adresse"].dropna().unique().tolist():
        if addr not in gcache:
            print(f"  API: {addr}"); geocode(addr, gcache)
    depot = gcache[DEPOT_ADDRESS]
    rc    = load_cache(ROUTE_CACHE_FILE)
    print(f"[2/7] Géocodage OK | Cache routes : {len(rc)} trajets")

    liv = df[df["type_mission_norm"]=="livraison"].to_dict("records")
    rec = df[df["type_mission_norm"]=="recuperation"].to_dict("records")
    print(f"[3/7] {len(liv)} livraisons | {len(rec)} récupérations")

    # ── PRÉ-ANALYSE v12 ──────────────────────────────────────────
    print(f"[4/7] Pré-analyse des missions...")
    rapport = preanalyse(liv, rec)
    afficher_preanalyse(rapport)
    # Stocker le rapport dans le résultat pour l'interface Streamlit
    _last_rapport_preanalyse = rapport

    print(f"[5/7] Construction tournées (FFD + routing géographique)...")
    if ORTOOLS_AVAILABLE:
        tournees = build_tours_ortools(liv, rec, gcache, rc, depot,
                                       nb_vehicules=len(liv)+len(rec))
    else:
        tournees = build_tours(liv, rec, gcache, rc, depot)

    print(f"\n[6/7] Affectation {nb_chauffeurs} chauffeur(s)...")
    chauffeurs = affecter_chauffeurs(tournees, nb_chauffeurs)

    result_df = to_df(tournees)
    rent_df   = calcul_rentabilite(tournees, result_df, gcache=gcache, rc=rc)
    print_kpi(tournees, result_df, rent_df, chauffeurs)

    print(f"\n[7/7] Exports...")
    result_df.to_csv(file_name.replace(".csv","_optimise_v12.csv"), index=False)
    rent_df.to_csv(file_name.replace(".csv","_rentabilite_v12.csv"), index=False)
    # PDFs
    export_pdf_chauffeur(tournees,chauffeurs,gcache)
    export_pdf_transport(tournees,chauffeurs,rent_df)
    # Carte
    carte = make_map(result_df,gcache,tournees,chauffeurs)
    carte.save("tournee_optimisee_v8.html")
    print("  Carte  : tournee_optimisee_v8.html")

    return result_df, gcache, tournees, rent_df, chauffeurs


# ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    # ── Mode affichage de la grille tarifaire seule
    if "--grille" in sys.argv:
        afficher_grille_tarifs()
        sys.exit(0)

    # ── Mode estimateur commercial — v9 grille zones
    if "--estimer" in sys.argv:
        gcache = load_cache(GEOCODE_CACHE_FILE)
        rc     = load_cache(ROUTE_CACHE_FILE)
        print("=" * 72)
        print("  ESTIMATEUR COMMERCIAL v9 — tarification par zone")
        print("=" * 72)
        afficher_grille_tarifs()
        adresse = input("Adresse client (ex: 10 rue de la Paix, 75001 Paris, france) : ").strip()
        nb      = int(input("Nombre de machines : ") or "1")
        type_m  = input("Type [livraison/recuperation] : ").strip() or "livraison"
        urgence = input("Urgence ? [o/n] : ").strip().lower() == "o"
        estimer_prix(adresse, nb, type_m, urgence, gcache, rc)
        sys.exit(0)

    # ── Mode normal
    nb_chauf = int(input("Nombre de chauffeurs disponibles aujourd'hui [1] : ") or "1")
    result_df,gcache,tournees,rent_df,chauffeurs = process_tour("csv_file.csv", nb_chauf)

    cols=["tour_id","zone","chauffeur_nom","phase","heure_arrivee",
          "client","machine","ville","distance_km","duration_min",
          "plateau_longueur_m","plateau_poids_t","retour_charge"]
    print("\nDétail missions :")
    print(result_df[[c for c in cols if c in result_df.columns]].to_string())
