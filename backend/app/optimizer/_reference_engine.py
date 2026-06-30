"""
Moteur de RÉFÉRENCE — interface identique à tournee_optimizer_v12.py.

Sert uniquement à faire tourner l'API de bout en bout tant que le vrai moteur
n'est pas déposé. Implémente : géo-clustering glouton + bin-packing 2D FFD +
estimation km/CO₂. Dès que tournee_optimizer_v12.py est présent, ce fichier
n'est plus utilisé (voir engine_loader).

Contrat attendu d'un moteur :
    optimize(missions: list[dict], vehicules: list[dict], depot: dict,
             params: dict) -> dict
    avec en sortie {"tournees": [...], "meta": {...}}
"""
from __future__ import annotations
import math
from itertools import count

PLATEAU_L = 13.6   # m
PLATEAU_W = 2.48   # m
CHARGE_KG = 26000.0
CONSO = 32.0       # l/100km
CO2_PAR_L = 2.64   # kg CO₂ / litre gazole
PRIX_GO = 1.75     # €/litre


def _haversine(a, b):
    R = 6371.0
    la1, lo1, la2, lo2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    dla, dlo = la2 - la1, lo2 - lo1
    h = math.sin(dla / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(dlo / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def _route_km(depot, stops):
    """Distance dépôt → stops (ordre nearest-neighbour) → dépôt, ×1.3 (routier)."""
    if not stops:
        return 0.0
    remaining = stops[:]
    cur = (depot["lat"], depot["lng"])
    total = 0.0
    while remaining:
        nxt = min(remaining, key=lambda s: _haversine(cur, (s["lat"], s["lng"])))
        total += _haversine(cur, (nxt["lat"], nxt["lng"]))
        cur = (nxt["lat"], nxt["lng"])
        remaining.remove(nxt)
    total += _haversine(cur, (depot["lat"], depot["lng"]))
    return round(total * 1.3, 1)


def _surface(m):
    return m.get("longueur_m", 6.0) * m.get("largeur_m", 2.2)


def optimize(missions, vehicules, depot, params=None):
    params = params or {}
    fusion = params.get("fusion", True)
    plateau_surface = PLATEAU_L * PLATEAU_W

    # FFD : machines les plus contraignantes (grande surface) d'abord
    items = sorted(missions, key=lambda m: _surface(m.get("machine", {})), reverse=True)

    tours: list[dict] = []
    ids = count(1)

    for m in items:
        s = _surface(m.get("machine", {}))
        w = m.get("machine", {}).get("poids_kg", 4000)
        placed = False
        for t in tours:
            if (t["_surface"] + s <= plateau_surface * 0.95 and
                    t["_poids"] + w <= CHARGE_KG):
                t["missions"].append(m)
                t["_surface"] += s
                t["_poids"] += w
                placed = True
                break
        if not placed:
            tours.append({"id": next(ids), "missions": [m], "_surface": s, "_poids": w})

    # Post-processing fusion des tournées très sous-remplies
    if fusion:
        tours.sort(key=lambda t: t["_surface"])
        i = 0
        while i < len(tours):
            ti = tours[i]
            if ti["_surface"] / plateau_surface < 0.5:
                for tj in tours:
                    if tj is ti:
                        continue
                    if (tj["_surface"] + ti["_surface"] <= plateau_surface * 0.95 and
                            tj["_poids"] + ti["_poids"] <= CHARGE_KG):
                        tj["missions"].extend(ti["missions"])
                        tj["_surface"] += ti["_surface"]
                        tj["_poids"] += ti["_poids"]
                        tours.remove(ti)
                        i -= 1
                        break
            i += 1

    # Construction de la sortie + métriques
    out_tours = []
    for idx, t in enumerate(tours, start=1):
        stops = [{"lat": m["lat"], "lng": m["lng"]} for m in t["missions"] if m.get("lat")]
        km = _route_km(depot, stops)
        taux = round(min(100.0, t["_surface"] / plateau_surface * 100), 1)
        litres = km * CONSO / 100
        out_tours.append({
            "index": idx,
            "missions": [m["id"] for m in t["missions"]],
            "stops": [[depot["lat"], depot["lng"]]] + [[s["lat"], s["lng"]] for s in stops] + [[depot["lat"], depot["lng"]]],
            "km": km,
            "co2_kg": round(litres * CO2_PAR_L, 1),
            "cout": round(litres * PRIX_GO, 2),
            "taux_remplissage": taux,
            "poids_kg": round(t["_poids"], 0),
        })

    km_total = round(sum(t["km"] for t in out_tours), 1)
    taux_moyen = round(sum(t["taux_remplissage"] for t in out_tours) / max(1, len(out_tours)), 1)
    co2 = round(sum(t["co2_kg"] for t in out_tours), 1)
    cout = round(sum(t["cout"] for t in out_tours), 2)

    return {
        "tournees": out_tours,
        "meta": {
            "nb_tournees": len(out_tours),
            "km_total": km_total,
            "taux_moyen": taux_moyen,
            "co2_kg": co2,
            "cout_estime": cout,
        },
    }


def minimum_theorique(missions):
    """Borne basse : nb de plateaux nécessaires vu la surface cumulée des machines."""
    plateau_surface = PLATEAU_L * PLATEAU_W * 0.95
    total = sum(_surface(m.get("machine", {})) for m in missions)
    return max(1, math.ceil(total / plateau_surface))
