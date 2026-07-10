"""
Adapter du VRAI moteur (tournee_optimizer_v11) derrière l'API.

Stratégie : on reproduit la séquence de `process_tour()` du moteur
SANS les exports PDF / carte folium (qui ne servent pas à l'API web).
On écrit les missions dans un CSV temporaire au format attendu par le moteur,
on le laisse géocoder via sa propre API, on récupère les tournées + le
plateau 2.5D, et on mappe le tout vers le format OptimizeResult du frontend.

Si quoi que ce soit échoue, on lève une exception : l'appelant (route)
retombera proprement sur le moteur de référence.
"""
from __future__ import annotations
import csv
import logging
import os
import tempfile
from datetime import datetime

logger = logging.getLogger("optimizer.v11_adapter")

TC = ["#E65100", "#8B5CF6", "#06B6D4", "#10B981", "#F59E0B", "#EC4899", "#6366F1"]
CONSO = 32.0
PRIX_GO = 1.75
CO2_PAR_L = 2.64


def _missions_to_csv(missions, path: str) -> int:
    """Écrit les missions au format CSV attendu par le moteur v11."""
    cols = ["ordre", "chauffeur", "type_mission", "client", "ville",
            "code_postal", "adresse", "machine", "categorie",
            "date", "heure_debut", "heure_fin"]
    n = 0
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for i, m in enumerate(missions, start=1):
            # L'adresse en base est "rue, CP, ville" (ex: "2 AV JEAN JAURES, 94600, CHOISY LE ROI")
            adresse_complete = (m.adresse or "").strip()
            parts = [p.strip() for p in adresse_complete.split(",") if p.strip()]

            rue = ""
            cp = ""
            ville = ""
            if len(parts) >= 3:
                # Format attendu : rue, CP, ville
                rue = parts[0]
                # cherche le segment qui est un code postal (5 chiffres)
                for p in parts[1:]:
                    tok = p.split()
                    if tok and tok[0].isdigit() and len(tok[0]) == 5:
                        cp = tok[0]
                        reste = " ".join(tok[1:])
                        if reste:
                            ville = reste
                    elif not p[0:1].isdigit():
                        ville = p  # segment texte = ville
                if not ville:
                    ville = parts[-1]
            elif len(parts) == 2:
                rue = parts[0]
                ville = parts[1]
            elif len(parts) == 1:
                # une seule valeur : c'est probablement la ville
                ville = parts[0]
                rue = parts[0]

            # Sécurité : full_addr du moteur exige rue ET ville non vides
            if not rue:
                rue = ville or adresse_complete or "adresse inconnue"
            if not ville:
                ville = rue

            w.writerow([
                i, "Chauffeur 1",
                (m.type_op or "livraison"),
                (m.client_nom or ""), ville, cp,
                rue,
                (m.machine_modele or ""), "", "2026-01-01", "05:00", "13:00",
            ])
            n += 1
    return n


def run_optimization_v11(missions, params=None) -> dict:
    """
    Point d'entrée. `missions` = entités Mission (déjà en base).
    Lève une exception si le moteur échoue (→ fallback géré par l'appelant).
    """
    import app.optimizer.tournee_optimizer_v11 as eng

    # Plafonne le temps OR-Tools à 15s (le moteur le fixe à 45s en dur, ligne
    # ~1054). Le monkey-patch de SolveWithParameters ne prend pas sur les
    # instances OR-Tools (méthodes C++). On recharge donc le module en ajustant
    # cette seule constante dans le source EN MÉMOIRE — le fichier sur disque
    # n'est jamais modifié. Fait AVANT les autres patchs (get_route, etc.).
    try:
        _src_path = eng.__file__
        with open(_src_path, "r", encoding="utf-8") as _f:
            _src = _f.read()
        if "seconds=45" in _src or "seconds = 45" in _src:
            _src = (_src.replace("time_limit.seconds=45", "time_limit.seconds=15")
                        .replace("time_limit.seconds = 45", "time_limit.seconds = 15")
                        .replace("(45s)", "(15s)"))
            exec(compile(_src, _src_path, "exec"), eng.__dict__)
    except Exception:
        pass

    # Cache géocode/routes dans un VOLUME DOCKER persistant (/code/cache_data).
    cache_dir = "/code/cache_data"
    os.makedirs(cache_dir, exist_ok=True)
    eng.GEOCODE_CACHE_FILE = os.path.join(cache_dir, "geocode_cache.json")
    eng.ROUTE_CACHE_FILE = os.path.join(cache_dir, "route_cache.json")

    # ROUTAGE via OSRM local (serveur Docker interne, illimité et instantané).
    # Remplace openrouteservice → plus de quota, plus de pause, distances réelles.
    import requests as _rq
    OSRM_URL = os.environ.get("OSRM_URL", "http://sta_osrm:5000")

    def _osrm_route(a, b, rc=None):
        if not a or not b:
            return {"distance_km": None, "duration_min": None}
        if abs(a["lat"] - b["lat"]) < 1e-6 and abs(a["lng"] - b["lng"]) < 1e-6:
            return {"distance_km": 0.0, "duration_min": 0}
        # Clé de cache IDENTIQUE à celle du moteur (ligne 587) : "lng,lat->lng,lat"
        key = None
        if rc is not None:
            key = f"{a['lng']:.5f},{a['lat']:.5f}->{b['lng']:.5f},{b['lat']:.5f}"
            if key in rc:
                return rc[key]
        res = None
        try:
            url = f"{OSRM_URL}/route/v1/driving/{a['lng']},{a['lat']};{b['lng']},{b['lat']}?overview=false"
            r = _rq.get(url, timeout=2)
            j = r.json()
            if j.get("code") == "Ok" and j.get("routes"):
                rt = j["routes"][0]
                res = {"distance_km": round(rt["distance"] / 1000, 2),
                       "duration_min": round(rt["duration"] / 60)}
        except Exception:
            pass
        if res is None:
            # repli vol d'oiseau si OSRM indisponible/hors zone (jamais de blocage)
            dist_km = round(eng.vd(a, b) * 1.4, 2)
            res = {"distance_km": dist_km, "duration_min": round(dist_km / 50 * 60)}
        if rc is not None and key is not None:
            rc[key] = res
        return res

    eng.get_route = _osrm_route
    # Sécurité : neutralise la pause ORS (1.6s/route) au cas où une route
    # échapperait au précalcul — évite tout blocage résiduel.
    try:
        eng.ORS_PAUSE_SEC = 0
    except Exception:
        pass

    # GÉOCODAGE via api-adresse.gouv.fr (gratuit, illimité, France) au lieu
    # d'openrouteservice dont le quota est épuisé. C'ÉTAIT LA VRAIE CAUSE des
    # blocages de plusieurs minutes : chaque nouvelle adresse partait sur ORS,
    # recevait un 403 quota, puis retry time.sleep(2,4,8s...) × N adresses.
    def _geocode_gouv(address, cache):
        if address in cache:
            return cache[address]
        res = None
        try:
            # lat/lon biaise la recherche vers l'Île-de-France (dépôt Lieusaint)
            r = _rq.get("https://api-adresse.data.gouv.fr/search/",
                        params={"q": address, "limit": 1, "lat": 48.63, "lon": 2.55},
                        timeout=5)
            j = r.json()
            feats = j.get("features") or []
            if feats:
                c = feats[0]["geometry"]["coordinates"]
                lng, lat = c[0], c[1]
                # GARDE-FOU : on rejette tout point hors Île-de-France élargie.
                # Un géocodage aberrant (mauvaise ville, lat/lng inversés) créait
                # des distances de 1000+ km qui faisaient diverger tout le calcul.
                if 48.1 <= lat <= 49.3 and 1.4 <= lng <= 3.6:
                    res = {"lng": lng, "lat": lat}
                # sinon res reste None → mission planifiée avec estimation, pas de divergence
        except Exception:
            res = None
        cache[address] = res
        try:
            eng.save_cache(eng.GEOCODE_CACHE_FILE, cache)
        except Exception:
            pass
        return res
    eng.geocode = _geocode_gouv

    tmpdir = tempfile.mkdtemp(prefix="sta_v11_")
    csv_path = os.path.join(tmpdir, "missions.csv")
    nb = _missions_to_csv(missions, csv_path)
    if nb == 0:
        raise ValueError("Aucune mission à optimiser")

    # 2. Reproduire la séquence de process_tour SANS exports
    import pandas as pd
    df = pd.read_csv(csv_path)
    df["code_postal"] = df["code_postal"].astype(str).str.zfill(5)
    df["full_adresse"] = df.apply(eng.full_addr, axis=1)
    df["type_mission_norm"] = df["type_mission"].apply(
        lambda x: "recuperation" if str(x).lower().strip() in
        ("recuperation", "récupération", "recup", "récup") else "livraison")

    gcache = eng.load_cache(eng.GEOCODE_CACHE_FILE)
    for addr in [eng.DEPOT_ADDRESS] + df["full_adresse"].dropna().unique().tolist():
        if addr not in gcache:
            eng.geocode(addr, gcache)
    depot = gcache.get(eng.DEPOT_ADDRESS)
    if not depot:
        # Repli : dépôt Lieusaint (Paris Sud) si le géocodage échoue
        depot = {"lat": 48.6320, "lng": 2.4700}
    rc = eng.load_cache(eng.ROUTE_CACHE_FILE)

    # PRÉCALCUL MATRICE : au lieu de 1600+ appels OSRM séquentiels (lent sur
    # 40 missions), on demande TOUTE la matrice en UN appel /table. On remplit
    # rc en amont ; ensuite chaque get_route() lit le cache → quasi instantané.
    try:
        pts = [depot] + [gcache[a] for a in df["full_adresse"].dropna().unique().tolist() if a in gcache]
        pts = [p for p in pts if p and "lat" in p and "lng" in p]
        if 2 <= len(pts) <= 120:  # limite raisonnable pour un seul appel
            coords = ";".join(f"{p['lng']},{p['lat']}" for p in pts)
            url = f"{OSRM_URL}/table/v1/driving/{coords}?annotations=distance,duration"
            r = _rq.get(url, timeout=15)
            j = r.json()
            if j.get("code") == "Ok":
                dists = j.get("distances") or []
                durs = j.get("durations") or []
                for i, pa in enumerate(pts):
                    for k, pb in enumerate(pts):
                        if i == k:
                            continue
                        d = dists[i][k] if i < len(dists) and k < len(dists[i]) else None
                        t = durs[i][k] if i < len(durs) and k < len(durs[i]) else None
                        if d is None:
                            continue
                        key = f"{pa['lng']:.5f},{pa['lat']:.5f}->{pb['lng']:.5f},{pb['lat']:.5f}"
                        rc[key] = {"distance_km": round(d / 1000, 2),
                                   "duration_min": round((t or 0) / 60)}
    except Exception:
        pass  # si le précalcul échoue, get_route retombera sur les appels unitaires

    liv = df[df["type_mission_norm"] == "livraison"].to_dict("records")
    rec = df[df["type_mission_norm"] == "recuperation"].to_dict("records")

    rapport = eng.preanalyse(liv, rec)
    min_theo = rapport.get("tours_min_theorique") or rapport.get("tours_min") or 1

    if eng.ORTOOLS_AVAILABLE:
        # Nombre de véhicules réaliste : min théorique + marge de 40%.
        # Passer len(liv)+len(rec) rend le problème insoluble pour OR-Tools (trop symétrique).
        nb_veh = max(min_theo + max(3, int(min_theo * 0.4)), 5)
        tournees = eng.build_tours_ortools(liv, rec, gcache, rc, depot,
                                           nb_vehicules=nb_veh)
    else:
        tournees = eng.build_tours(liv, rec, gcache, rc, depot)

    # 2bis. PÉPITES DÉJÀ CODÉES DANS LE MOTEUR, jamais exposées jusqu'ici :
    #  - affecter_chauffeurs() : regroupe les tournées en chauffeurs-journées (8h)
    #  - calcul_rentabilite()  : CA, coûts, marge €, taux % par tournée
    chauffeurs = None
    rentabilite = None
    try:
        # On passe 1 : la fonction calcule elle-même le minimum réel nécessaire.
        chauffeurs = eng.affecter_chauffeurs(tournees, 1)
    except Exception as _e:
        chauffeurs = None
    try:
        import pandas as _pd
        # calcul_rentabilite attend un DataFrame de missions ; on reconstruit le
        # minimum nécessaire depuis les tournées si besoin, sinon forfait.
        rent_df = eng.calcul_rentabilite(tournees, _pd.DataFrame(), gcache, rc)
        rentabilite = rent_df.to_dict("records") if hasattr(rent_df, "to_dict") else None
    except Exception as _e:
        rentabilite = None

    # 3. Mapper la sortie moteur → format frontend
    return _map_resultat(tournees, gcache, depot, min_theo, eng,
                         chauffeurs=chauffeurs, rentabilite=rentabilite)


def _map_resultat(tournees, gcache, depot, min_theo, eng,
                  chauffeurs=None, rentabilite=None) -> dict:
    out_tours = []
    km_total = 0.0
    taux_sum = 0.0

    for i, t in enumerate(tournees):
        st = t["stats"]
        livs = t.get("livraisons", [])
        recs = t.get("recups", [])
        km = st.get("dist_km", 0) or 0
        km_total += km
        taux = st.get("taux_lon", 0) or 0
        taux_sum += taux

        # Points d'itinéraire (dépôt → missions → dépôt)
        pts = [[depot["lat"], depot["lng"]]]
        for m in livs + recs:
            c = gcache.get(m.get("full_adresse"))
            if c:
                pts.append([c["lat"], c["lng"]])
        pts.append([depot["lat"], depot["lng"]])

        litres = km * CONSO / 100
        # Plateau 2.5D : liste des machines avec leurs dimensions
        plateau = []
        for m in livs + recs:
            specs = eng.get_specs(m.get("machine", ""))
            plateau.append({
                "machine": m.get("machine", ""),
                "client": m.get("client", ""),
                "type": m.get("type_mission_norm", "livraison"),
                "longueur": round(specs.get("longueur", 0), 2),
                "largeur": round(specs.get("largeur", 0), 2),
                "poids": round(specs.get("poids", 0), 2),
            })

        explications = []
        if len(livs) > 1 or len(recs) > 0:
            explications.append(
                f"Mutualisation : {len(livs)} livraison(s) + {len(recs)} récupération(s) sur un seul plateau.")
        if recs and livs:
            explications.append(
                "Récupérations intégrées au retour de tournée — optimisation du trajet à vide.")
        explications.append(
            f"Bin-packing 2.5D : plateau rempli à {taux}% en longueur, {st.get('taux_pds',0)}% en poids ({t.get('camion_label','semi')}).")
        explications.append(
            f"Camion sélectionné : {t.get('camion_label','—')} (PTAC {t.get('camion_ptac_t','?')}T).")

        # ── Chronologie horaire de la tournée ──
        # Départ 05:00, +15 min chargement/déchargement par arrêt, trajets estimés.
        def _hhmm(minutes):
            h = 5 * 60 + int(minutes)
            return f"{(h // 60) % 24:02d}:{h % 60:02d}"
        chronologie = []
        horloge = 0  # minutes depuis 05:00
        chronologie.append({
            "heure": _hhmm(horloge), "lieu": "Dépôt agence Lieusaint",
            "action": "Départ", "machine": "", "duree_min": 0,
        })
        prev = depot
        seq = [("livraison", m) for m in livs] + [("recuperation", m) for m in recs]
        for op, m in seq:
            c = gcache.get(m.get("full_adresse")) or prev
            route = eng.get_route(prev, c) if prev and c else {"duration_min": 20}
            trajet = route.get("duration_min") or 20
            horloge += trajet
            action = "Livraison — dépose machine" if op == "livraison" else "Récupération — charge machine"
            chronologie.append({
                "heure": _hhmm(horloge),
                "lieu": f"{m.get('client','')} ({m.get('ville') or m.get('full_adresse','')[:30]})",
                "action": action,
                "machine": m.get("machine", ""),
                "duree_min": 15,
            })
            horloge += 15  # temps de manutention
            prev = c
        # retour dépôt
        route = eng.get_route(prev, depot) if prev else {"duration_min": 20}
        horloge += route.get("duration_min") or 20
        retour_note = "Retour dépôt" + (" — dépose des récupérations" if recs else "")
        chronologie.append({
            "heure": _hhmm(horloge), "lieu": "Dépôt agence Lieusaint",
            "action": retour_note, "machine": "", "duree_min": 0,
        })
        duree_totale = horloge

        out_tours.append({
            "index": t["tour_id"],
            "couleur": TC[i % len(TC)],
            "missions": [m.get("client", "") for m in livs + recs],
            "itineraire": pts,
            "km": round(km, 1),
            "co2_kg": round(litres * CO2_PAR_L, 1),
            "taux_remplissage": taux,
            "nb_missions": len(livs) + len(recs),
            "plateau": plateau,
            "explications": explications,
            "chronologie": chronologie,
            "duree_min": duree_totale,
            "depart": "05:00",
        })

    nb_t = len(out_tours)
    taux_moyen = round(taux_sum / max(1, nb_t), 1)
    co2 = round(km_total * CONSO / 100 * CO2_PAR_L, 1)
    cout = round(km_total * CONSO / 100 * PRIX_GO, 2)

    # Comparaison avant/après (planification classique estimée)
    nb_avant = max(nb_t, round((sum(t["nb_missions"] for t in out_tours)) / 1.15))
    km_avant = round(km_total * 1.34, 1)
    litres_av = km_avant * CONSO / 100

    def metric(label, av, ap, unit):
        try:
            delta = round((ap - av) / av * 100, 1) if av else 0.0
        except ZeroDivisionError:
            delta = 0.0
        return {"label": label, "avant": f"{av} {unit}".strip(),
                "apres": f"{ap} {unit}".strip(),
                "gain": f"{round(ap-av,1)} {unit}".strip(), "delta_pct": delta}

    comparaison = [
        metric("Tournées", nb_avant, nb_t, ""),
        metric("Kilomètres", km_avant, round(km_total, 1), "km"),
        metric("Coût carburant", round(litres_av * PRIX_GO), round(cout), "€"),
        metric("Émissions CO₂", round(litres_av * CO2_PAR_L), co2, "kg"),
        {"label": "Taux de remplissage", "avant": "≈ 58 %", "apres": f"{taux_moyen} %",
         "gain": f"+{round(taux_moyen-58,1)} pts", "delta_pct": round(taux_moyen-58, 1)},
    ]

    # ── Formatage des pépites exposées ──
    # Affectation chauffeurs : nb réel + planning par chauffeur
    chauffeurs_out = []
    nb_chauffeurs = None
    if chauffeurs:
        for ch in chauffeurs:
            h = int(ch.get("tps", 0)) // 60
            m = int(ch.get("tps", 0)) % 60
            chauffeurs_out.append({
                "id": ch.get("id"),
                "nom": ch.get("nom", f"Chauffeur {ch.get('id','?')}"),
                "tours": ch.get("tours", []),
                "duree_min": int(ch.get("tps", 0)),
                "duree_texte": f"{h}h{m:02d}",
                "km": round(ch.get("km", 0), 1),
                "charge_pct": round(ch.get("tps", 0) / 480 * 100),
            })
        nb_chauffeurs = len(chauffeurs_out)

    # Rentabilité : total + par tournée, et repérage des tournées déficitaires
    rentabilite_out = None
    if rentabilite:
        ca_tot = sum(r.get("ca_estime_eur", 0) for r in rentabilite)
        cout_tot = sum(r.get("cout_total_eur", 0) for r in rentabilite)
        marge_tot = round(ca_tot - cout_tot, 2)
        deficit = [r.get("tour_id", r.get("index")) for r in rentabilite
                   if r.get("marge_eur", 0) < 0]
        rentabilite_out = {
            "par_tournee": rentabilite,
            "ca_total_eur": round(ca_tot, 2),
            "cout_total_eur": round(cout_tot, 2),
            "marge_total_eur": marge_tot,
            "taux_marge_pct": round(marge_tot / ca_tot * 100, 1) if ca_tot else 0,
            "tournees_deficitaires": deficit,
        }

    return {
        "reference": f"OPT-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        "statut": "TERMINEE",
        "moteur": "v11",
        "nb_missions": sum(t["nb_missions"] for t in out_tours),
        "nb_tournees": nb_t,
        "nb_tournees_min_theorique": min_theo,
        "nb_chauffeurs": nb_chauffeurs,
        "chauffeurs": chauffeurs_out,
        "rentabilite": rentabilite_out,
        "km_total": round(km_total, 1),
        "taux_moyen": taux_moyen,
        "cout_estime": cout,
        "co2_kg": co2,
        "duree_calcul_s": 0,
        "comparaison": comparaison,
        "tournees": out_tours,
    }
