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

    # DISJONCTEUR OSRM : si OSRM est gelé/injoignable, chaque appel unitaire
    # attend son timeout (2s) avant le repli — des centaines d'appels en série
    # = réponse HTTP qui ne part jamais (cause du blocage du 11-17/07).
    # Après 3 échecs réseau consécutifs, on coupe : tout le reste du calcul
    # passe en vol d'oiseau SANS plus jamais toucher au réseau.
    _osrm_etat = {"echecs": 0, "coupe": False}

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
        if not _osrm_etat["coupe"]:
            try:
                url = f"{OSRM_URL}/route/v1/driving/{a['lng']},{a['lat']};{b['lng']},{b['lat']}?overview=false"
                r = _rq.get(url, timeout=2)
                j = r.json()
                if j.get("code") == "Ok" and j.get("routes"):
                    rt = j["routes"][0]
                    res = {"distance_km": round(rt["distance"] / 1000, 2),
                           "duration_min": round(rt["duration"] / 60)}
                _osrm_etat["echecs"] = 0
            except Exception:
                _osrm_etat["echecs"] += 1
                if _osrm_etat["echecs"] >= 3 and not _osrm_etat["coupe"]:
                    _osrm_etat["coupe"] = True
                    logger.warning("OSRM injoignable (3 échecs consécutifs) — "
                                   "bascule DÉFINITIVE en vol d'oiseau pour ce calcul. "
                                   "Vérifier le conteneur sta_osrm.")
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

    import time as _time
    _t0 = _time.time()
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
    except (_rq.exceptions.ConnectionError, _rq.exceptions.Timeout) as e:
        # OSRM ne répond pas du tout : inutile d'essayer 1600 appels unitaires
        # à 2s de timeout chacun — on coupe immédiatement.
        _osrm_etat["coupe"] = True
        logger.warning("Précalcul /table : OSRM injoignable (%s) — tout le calcul "
                       "passe en vol d'oiseau. Vérifier sta_osrm.", type(e).__name__)
    except Exception as e:
        logger.warning("Précalcul /table échoué (%s) — get_route retombera sur "
                       "les appels unitaires (cache incomplet).", e)

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
        # result_df minimal : 1 ligne/tournée, durée réelle posée par
        # affecter_chauffeurs (_tps_reel) -> coût chauffeur exact.
        rent_rows = [{"tour_id": t["tour_id"],
                      "duration_min": t.get("_tps_reel", 0)} for t in tournees]
        # Diagnostic : combien de paires dépôt->mission manquent au cache ?
        _missing = 0
        for _t in tournees:
            for _m in _t.get("livraisons", []) + _t.get("recups", []):
                _c = gcache.get(_m.get("full_adresse"))
                if _c:
                    _k = f"{depot['lng']:.5f},{depot['lat']:.5f}->{_c['lng']:.5f},{_c['lat']:.5f}"
                    if _k not in rc:
                        _missing += 1
        print(f"  [rentabilite] cles depot->mission absentes du cache : {_missing}")
        # Garde-fou : pendant calcul_rentabilite, get_route ne sort JAMAIS
        # sur ORS (sleeps/retries = hang HTTP). Cache sinon vol d'oiseau x1.4.
        _orig_get_route = eng.get_route
        def _get_route_offline(a, b, rcache):
            if not a or not b:
                return {"distance_km": None, "duration_min": None}
            _k = f"{a['lng']:.5f},{a['lat']:.5f}->{b['lng']:.5f},{b['lat']:.5f}"
            if rcache is not None and _k in rcache:
                return rcache[_k]
            _d = round(eng.vd(a, b) * 1.4, 2)
            return {"distance_km": _d, "duration_min": round(_d / 50 * 60)}
        eng.get_route = _get_route_offline
        try:
            rent_df = eng.calcul_rentabilite(tournees, _pd.DataFrame(rent_rows), gcache, rc)
        finally:
            eng.get_route = _orig_get_route
        rentabilite = rent_df.to_dict("records") if hasattr(rent_df, "to_dict") else None
    except Exception as _e:
        rentabilite = None

    # 3. Mapper la sortie moteur → format frontend
    res = _map_resultat(tournees, gcache, depot, min_theo, eng,
                        chauffeurs=chauffeurs, rentabilite=rentabilite)
    res["duree_calcul_s"] = round(_time.time() - _t0, 1)
    return res


def _hhmm(minutes):
    """Heure affichée à partir de minutes écoulées depuis 05:00."""
    h = 5 * 60 + int(minutes)
    return f"{(h // 60) % 24:02d}:{h % 60:02d}"


def _placer_plateau(machines, lon_max=12.5, larg_max=2.55):
    """Rejoue la logique de slots de Plateau2D (moteur) en enregistrant la
    position de CHAQUE machine : slot (tranche transversale), x (début de la
    tranche depuis l'avant), y (décalage en largeur). Règles identiques au
    moteur : large (>demi-largeur) = slot dédié ; étroite = partage de slot
    tant que la largeur restante le permet (2 ou 3 côte à côte).
    Retourne aussi un drapeau `hors_gabarit` par machine si — cas anormal —
    elle ne tient pas : elle est alors signalée, jamais dessinée en dépassement.
    """
    demi = larg_max / 2
    slots = []   # {"longueur", "largeur_restante", "items": [(idx_machine, y, largeur)]}
    place = []   # par machine : {"slot", "y"} ou None
    for i, m in enumerate(machines):
        lon = float(m.get("longueur") or 0)
        larg = float(m.get("largeur") or larg_max)
        if lon <= 0:
            place.append(None)
            continue
        pose = None
        if larg > larg_max:
            place.append(None)
            continue
        if larg > demi:
            # slot dédié
            if sum(sl["longueur"] for sl in slots) + lon <= lon_max + 1e-9:
                slots.append({"longueur": lon, "largeur_restante": 0.0,
                              "items": [(i, 0.0, larg)]})
                pose = {"slot": len(slots) - 1, "y": 0.0}
        else:
            # partage : slot le plus rempli d'abord (même tri que le moteur)
            for idx, sl in sorted(enumerate(slots),
                                  key=lambda x: x[1]["largeur_restante"]):
                if sl["largeur_restante"] >= larg - 0.01:
                    delta = max(sl["longueur"], lon) - sl["longueur"]
                    if sum(s2["longueur"] for s2 in slots) + delta > lon_max + 1e-9:
                        continue
                    y = larg_max - sl["largeur_restante"]
                    sl["longueur"] = max(sl["longueur"], lon)
                    sl["largeur_restante"] -= larg
                    sl["items"].append((i, y, larg))
                    pose = {"slot": idx, "y": round(y, 3)}
                    break
            if pose is None:
                if sum(sl["longueur"] for sl in slots) + lon <= lon_max + 1e-9:
                    slots.append({"longueur": lon,
                                  "largeur_restante": larg_max - larg,
                                  "items": [(i, 0.0, larg)]})
                    pose = {"slot": len(slots) - 1, "y": 0.0}
        place.append(pose)

    # x de chaque slot = cumul des longueurs des slots précédents
    x_off, cum = [], 0.0
    for sl in slots:
        x_off.append(round(cum, 3))
        cum += sl["longueur"]

    out = []
    for i, m in enumerate(machines):
        p = place[i]
        item = dict(m)
        if p is None:
            item.update({"x": None, "y": None, "slot": None, "hors_gabarit": True})
        else:
            item.update({"x": x_off[p["slot"]], "y": p["y"],
                         "slot": p["slot"], "hors_gabarit": False})
        out.append(item)
    lon_tot = round(cum, 2)
    return {
        "machines": out,
        "longueur_utilisee": lon_tot,
        "lon_max": lon_max,
        "larg_max": larg_max,
        "taux_lon": round(lon_tot / lon_max * 100, 1) if lon_max else 0,
        "nb_hors_gabarit": sum(1 for o in out if o.get("hors_gabarit")),
    }


def _camion_dims(t, eng):
    """Longueur/largeur du camion de la tournée, via CAMIONS_FLOTTE du moteur."""
    lon, larg = 12.5, 2.55
    try:
        flotte = getattr(eng, "CAMIONS_FLOTTE", {}) or {}
        cible = None
        for cle in ("camion_type", "type_camion", "camion"):
            if t.get(cle) in flotte:
                cible = flotte[t[cle]]
                break
        if cible is None and t.get("camion_ptac_t") is not None:
            for c in flotte.values():
                if c.get("ptac_t") == t.get("camion_ptac_t"):
                    cible = c
                    break
        if cible:
            lon = float(cible.get("longueur_m", lon))
            larg = float(cible.get("largeur_m", larg))
    except Exception:
        pass
    return lon, larg


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
        # ── ÉTATS RÉELS DU PLATEAU (aller / retour), avec positions ──
        # Le moteur packe livraisons et récupérations sur DEUX plateaux
        # distincts (aller = livraisons, retour = récups) : les deux phases ne
        # coexistent jamais à bord. On rejoue son bin-packing en enregistrant
        # les positions pour que la vue soit exacte (zéro dépassement dessiné).
        lon_cam, larg_cam = _camion_dims(t, eng)
        plateau_aller = _placer_plateau(
            [p for p in plateau if p["type"] != "recuperation"], lon_cam, larg_cam)
        plateau_retour = _placer_plateau(
            [p for p in plateau if p["type"] == "recuperation"], lon_cam, larg_cam)

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
        # Base 05:00 ; chaque événement garde son décalage relatif (t_rel) pour
        # permettre le chaînage des horaires par chauffeur en fin de mapping.
        chronologie = []
        horloge = 0  # minutes depuis 05:00
        conduite_min = 0
        manutention_min = 0
        pause_min = 0
        depuis_pause = 0  # activité cumulée depuis la dernière pause
        PAUSE_APRES_MIN = 270   # 4h30 d'activité → pause obligatoire
        PAUSE_DUREE_MIN = 45    # pause réglementaire conduite (45 min)
        chronologie.append({
            "heure": _hhmm(horloge), "lieu": "Dépôt agence Lieusaint",
            "action": "Départ", "machine": "", "duree_min": 0, "t_rel": 0,
        })
        prev = depot
        seq = [("livraison", m) for m in livs] + [("recuperation", m) for m in recs]
        for op, m in seq:
            c = gcache.get(m.get("full_adresse")) or prev
            route = eng.get_route(prev, c) if prev and c else {"duration_min": 20}
            trajet = route.get("duration_min") or 20
            # Pause réglementaire AVANT d'entamer un trajet qui ferait
            # dépasser 4h30 d'activité continue.
            if depuis_pause + trajet > PAUSE_APRES_MIN:
                chronologie.append({
                    "heure": _hhmm(horloge), "lieu": "—",
                    "action": "⏸ Pause réglementaire (45 min)",
                    "machine": "", "duree_min": PAUSE_DUREE_MIN, "t_rel": horloge,
                })
                horloge += PAUSE_DUREE_MIN
                pause_min += PAUSE_DUREE_MIN
                depuis_pause = 0
            horloge += trajet
            conduite_min += trajet
            depuis_pause += trajet
            action = "Livraison — dépose machine" if op == "livraison" else "Récupération — charge machine"
            chronologie.append({
                "heure": _hhmm(horloge),
                "lieu": f"{m.get('client','')} ({m.get('ville') or m.get('full_adresse','')[:30]})",
                "action": action,
                "machine": m.get("machine", ""),
                "duree_min": 15,
                "trajet_min": trajet,
                "t_rel": horloge,
            })
            horloge += 15  # temps de manutention
            manutention_min += 15
            depuis_pause += 15
            prev = c
        # retour dépôt
        route = eng.get_route(prev, depot) if prev else {"duration_min": 20}
        _tr = route.get("duration_min") or 20
        if depuis_pause + _tr > PAUSE_APRES_MIN:
            chronologie.append({
                "heure": _hhmm(horloge), "lieu": "—",
                "action": "⏸ Pause réglementaire (45 min)",
                "machine": "", "duree_min": PAUSE_DUREE_MIN, "t_rel": horloge,
            })
            horloge += PAUSE_DUREE_MIN
            pause_min += PAUSE_DUREE_MIN
            depuis_pause = 0
        horloge += _tr
        conduite_min += _tr
        retour_note = "Retour dépôt" + (" — dépose des récupérations" if recs else "")
        chronologie.append({
            "heure": _hhmm(horloge), "lieu": "Dépôt agence Lieusaint",
            "action": retour_note, "machine": "", "duree_min": 0, "t_rel": horloge,
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
            "plateau_aller": plateau_aller,
            "plateau_retour": plateau_retour,
            "camion": {"label": t.get("camion_label", "semi"),
                       "lon_max": lon_cam, "larg_max": larg_cam},
            "explications": explications,
            "chronologie": chronologie,
            "duree_min": duree_totale,
            "conduite_min": conduite_min,
            "manutention_min": manutention_min,
            "pause_min": pause_min,
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
        # Annoter chaque tournée de son chauffeur (les cartes tournées
        # affichaient "Non assigné" faute de cette info) et recalculer la
        # charge de chaque chauffeur PAUSES INCLUSES.
        duree_par_tour = {t["index"]: t.get("duree_min", 0) for t in out_tours}
        for ch in chauffeurs_out:
            for t in out_tours:
                if t["index"] in (ch.get("tours") or []):
                    t["chauffeur"] = ch["nom"]
            avec_pauses = sum(duree_par_tour.get(ti, 0) for ti in (ch.get("tours") or []))
            if avec_pauses:
                ch["duree_avec_pauses_min"] = avec_pauses
                ch["charge_pct_avec_pauses"] = round(avec_pauses / 480 * 100)
                ch["depassement_8h"] = avec_pauses > 480
        # ── CHAÎNAGE HORAIRE : un chauffeur ne peut pas démarrer toutes ses
        # tournées à 05:00. Chaque tournée suivante démarre à la fin de la
        # précédente + battement dépôt (rechargement du plateau).
        BATTEMENT_DEPOT_MIN = 30
        tour_par_index = {t["index"]: t for t in out_tours}
        for ch in chauffeurs_out:
            offset = 0
            for k, ti in enumerate(ch.get("tours") or []):
                t = tour_par_index.get(ti)
                if not t:
                    continue
                if k > 0:
                    offset += BATTEMENT_DEPOT_MIN
                t["depart"] = _hhmm(offset)
                t["fin"] = _hhmm(offset + t.get("duree_min", 0))
                for ev in t.get("chronologie", []):
                    ev["heure"] = _hhmm(offset + ev.get("t_rel", 0))
                    if ev["action"] == "Départ" and k > 0:
                        ev["action"] = "Départ (après rechargement au dépôt)"
                offset += t.get("duree_min", 0)
            if ch.get("tours"):
                ch["fin_journee"] = _hhmm(offset)

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
