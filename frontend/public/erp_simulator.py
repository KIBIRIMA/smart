#!/usr/bin/env python3
"""
SIMULATEUR ERP — Smart Transport AI
=====================================
Joue le rôle d'un ERP externe (type logiciel de gestion des locations Accès)
qui synchronise ses missions vers Smart Transport AI, puis déclenche
l'optimisation et mesure les résultats.

HONNÊTE : n'utilise QUE les endpoints réels existants de l'API
(/auth/login, /missions/import, /optimizer/run). Aucun endpoint fantôme.

Usage (depuis le VPS ou toute machine qui voit l'API) :
    python3 erp_simulator.py --csv 03_donnees_test/charge_100_missions.csv
    python3 erp_simulator.py --csv test_500_missions.csv --vagues 5
    python3 erp_simulator.py --csv charge_400_missions.csv --vagues 4 --pause 3

Options :
    --csv     : fichier de missions à pousser (format import standard)
    --vagues  : découpe l'envoi en N vagues (simule des synchros ERP successives)
    --pause   : secondes entre vagues (défaut 2)
    --api     : URL de l'API (défaut http://localhost:8000/api/v1)
    --no-opt  : injecte seulement, sans lancer l'optimisation
"""
import argparse, csv, io, json, sys, time
import urllib.request, urllib.parse

API = "http://localhost:8000/api/v1"
LOGIN = ("heinrich.weber@acces-industrie.fr", "exploit123")


def http(method, url, data=None, token=None, is_json=True, files=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if files:
        # multipart simple pour l'upload CSV
        boundary = "----ERPSIM"
        body = []
        fname, content = files
        body.append(f"--{boundary}".encode())
        body.append(f'Content-Disposition: form-data; name="file"; filename="{fname}"'.encode())
        body.append(b"Content-Type: text/csv")
        body.append(b"")
        body.append(content.encode("utf-8"))
        body.append(f"--{boundary}--".encode())
        data = b"\r\n".join(body)
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif data is not None and is_json:
        data = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    elif data is not None:
        data = urllib.parse.urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--vagues", type=int, default=1)
    ap.add_argument("--pause", type=float, default=2.0)
    ap.add_argument("--api", default=API)
    ap.add_argument("--no-opt", action="store_true")
    args = ap.parse_args()

    print("=" * 62)
    print("  SIMULATEUR ERP → Smart Transport AI")
    print("=" * 62)

    # 1. Authentification (comme un connecteur ERP avec compte de service)
    print("\n[ERP] Authentification…")
    tok = http("POST", f"{args.api}/auth/login",
               {"username": LOGIN[0], "password": LOGIN[1]}, is_json=False)
    token = tok["access_token"]
    print("      ✅ connecté (compte de service)")

    # 2. Lecture du 'carnet de commandes' de l'ERP
    rows = list(csv.reader(open(args.csv, encoding="utf-8")))
    header, missions = rows[0], rows[1:]
    n = len(missions)
    par_vague = max(1, n // args.vagues)
    print(f"\n[ERP] Carnet : {n} missions → envoi en {args.vagues} vague(s) de ~{par_vague}")

    # 3. Synchronisation par vagues (simule les syncs ERP successives)
    t_total = time.time()
    for v in range(args.vagues):
        lot = missions[v * par_vague:(v + 1) * par_vague] if v < args.vagues - 1 \
              else missions[v * par_vague:]
        if not lot:
            continue
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(header)
        w.writerows(lot)
        t0 = time.time()
        # 1re vague : remplace les missions A_PLANIFIER ; suivantes : ajoute
        remplacer = "true" if v == 0 else "false"
        res = http("POST", f"{args.api}/import/missions?remplacer={remplacer}",
                   token=token, files=(f"erp_sync_{v+1}.csv", buf.getvalue()))
        dt = time.time() - t0
        ok = res.get("importees", res.get("imported", "?"))
        print(f"      vague {v+1}/{args.vagues} : {len(lot)} missions poussées "
              f"({ok} importées) en {dt:.1f}s")
        if v < args.vagues - 1:
            time.sleep(args.pause)

    if args.no_opt:
        print("\n[ERP] Injection terminée (pas d'optimisation demandée).")
        return

    # 4. Déclenchement de l'optimisation (comme un trigger ERP)
    print("\n[ERP] Déclenchement de l'optimisation…")
    t0 = time.time()
    r = http("POST", f"{args.api}/optimizer/run", {"moteur": "v11", "fusion": True},
             token=token)
    dt = time.time() - t0

    # 5. Rapport de mesure
    print("\n" + "=" * 62)
    print("  RAPPORT — réaction du logiciel au flux ERP")
    print("=" * 62)
    print(f"  Missions traitées   : {r['nb_missions']}")
    print(f"  Temps optimisation  : {dt:.1f} s")
    print(f"  Tournées générées   : {r['nb_tournees']} "
          f"(min théorique {r.get('nb_tournees_min_theorique','?')})")
    if r.get("nb_chauffeurs"):
        print(f"  Chauffeurs-journées : {r['nb_chauffeurs']}")
    print(f"  Kilomètres          : {r['km_total']} km")
    print(f"  Remplissage moyen   : {r['taux_moyen']} %")
    rent = r.get("rentabilite")
    if rent:
        print(f"  Marge estimée       : {rent['marge_total_eur']} € "
              f"({rent['taux_marge_pct']} %)")
        if rent.get("tournees_deficitaires"):
            print(f"  ⚠ Déficitaires      : {rent['tournees_deficitaires']}")
    print(f"\n  Temps total (sync + calcul) : {time.time()-t_total:.1f} s")
    print("=" * 62)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ ERREUR : {e}")
        sys.exit(1)
