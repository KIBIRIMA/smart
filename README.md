# 🚛 Smart Transport AI

Plateforme d'optimisation logistique pour **Accès Industrie** — tournées de nacelles
et chariots télescopiques, chargement plateau 2D, multi-agences.

Architecture SaaS découplée : **Next.js** (frontend) + **FastAPI** (backend) +
**PostgreSQL** + **Redis** + **Nginx**, orchestrée par Docker Compose.

---

## 🏗️ Architecture

```
                  ┌─────────────┐
   navigateur ───▶│    Nginx    │  reverse proxy + HTTPS
                  └──────┬──────┘
            ┌────────────┴────────────┐
            ▼                         ▼
   ┌─────────────────┐      ┌──────────────────┐
   │  Next.js (3000) │      │ FastAPI (8000)   │
   │  app router     │◀────▶│ JWT · 5 rôles    │
   └─────────────────┘      └────────┬─────────┘
                            ┌─────────┴──────────┐
                            ▼                    ▼
                   ┌────────────────┐   ┌──────────────┐
                   │ PostgreSQL     │   │ Redis        │
                   └────────────────┘   └──────────────┘
                            ▲
                   ┌────────┴─────────┐
                   │  Moteur v12      │  ← adapter (zone protégée)
                   │  OR-Tools VRP    │
                   │  Bin-Packing 2D  │
                   └──────────────────┘
```

Le moteur `tournee_optimizer_v12.py` n'est **jamais modifié** : il est appelé
tel quel via `backend/app/optimizer/adapter.py`, qui ajoute les explications
métier et la comparaison avant/après.

---

## 🚀 Démarrage rapide

```bash
git clone <repo> smart-transport-ai
cd smart-transport-ai

cp .env.example .env
# Éditez .env : SECRET_KEY (openssl rand -hex 32), mots de passe

docker compose up -d --build
```

Au premier démarrage, le backend crée le schéma et insère le jeu de
démonstration automatiquement (voir `backend/app/db/seed.py`).

| Service        | URL                          |
|----------------|------------------------------|
| Application    | http://localhost (via nginx) |
| API + Swagger  | http://localhost/docs        |
| Santé          | http://localhost/health      |

### Comptes de démonstration

| Rôle          | Email                                | Mot de passe |
|---------------|--------------------------------------|--------------|
| Administrateur| admin@acces-industrie.fr             | admin123     |
| DSI           | dsi@acces-industrie.fr               | dsi123       |
| Exploitant    | heinrich.weber@acces-industrie.fr    | exploit123   |
| Chef d'agence | chef.ps@acces-industrie.fr           | chef123      |
| Lecture seule | lecture@acces-industrie.fr           | lecture123   |

---

## 🔧 Intégrer le vrai moteur d'optimisation

Déposez vos fichiers réels dans `backend/app/optimizer/` :

```
tournee_optimizer_v12.py   ← moteur principal
tournee_optimizer_v11.py   ← fallbacks
...
machines.json              ← catalogue complet
```

Le chargeur (`engine_loader.py`) les détecte automatiquement et bascule
de l'implémentation de référence vers votre moteur. **Aucune modification
du code moteur n'est requise** — voir `backend/app/optimizer/README.md`.

---

## 🌐 Déploiement VPS LWS (production)

```bash
# 1. Sur le VPS, cloner + configurer
git clone <repo> && cd smart-transport-ai
cp .env.example .env && nano .env   # secrets + domaine

# 2. Lancer
./scripts/deploy.sh

# 3. Activer HTTPS (Let's Encrypt)
./scripts/init-letsencrypt.sh votre-domaine.fr admin@votre-domaine.fr
```

Pensez à pointer le DNS du domaine vers l'IP du VPS et à ouvrir les ports 80/443.

Sauvegarde base : `./scripts/backup-db.sh`

---

## 📦 Stack technique

| Couche      | Technologies                                            |
|-------------|---------------------------------------------------------|
| Frontend    | Next.js 14 (app router), React 18, SWR, Leaflet         |
| Backend     | FastAPI, SQLAlchemy async, Pydantic, python-jose (JWT)  |
| Données     | PostgreSQL 16, Redis 7                                   |
| Optimisation| OR-Tools (VRP), Bin-Packing 2D FFD, fuzzy matching      |
| Infra       | Docker Compose, Nginx, Let's Encrypt                    |

---

## 🗺️ Modules sur la feuille de route

Intégration ERP/TMS (ORTEC, SAP) · VGP & conformité · maintenance prédictive ·
BI multi-agences · IA prédictive de demande · application mobile chauffeur.

---

© Smart Transport AI — éditeur indépendant. Conçu pour le groupe Accès Industrie.
