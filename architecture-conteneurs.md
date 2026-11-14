# Architecture en conteneurs Docker : plateforme d'actualités NewsLab Recsys

**Version 0.1 (brouillon de conception), 14 novembre 2026.** Complète le [cahier des charges](cahier-des-charges-actualites.md).

> **Statut : conception uniquement.** Rien n'est créé ni lancé. Le fichier Compose ci-dessous est une **ébauche** pour discuter de la structure. Les choix ouverts sont au §9.

---

## 1. Point de départ : ce que fait la plateforme du professeur

Le dépôt de référence (`compose.yaml`) contient **4 services** :

| Service | Construction | Rôle | Exposition |
|---|---|---|---|
| `db` | `postgres:17-alpine` | Base de données, volume `postgres_data`, healthcheck `pg_isready` | Aucune (réseau interne) |
| `api` | `./backend` (Python 3.12-slim, uvicorn port 8000, utilisateur non root) | FastAPI, migrations et calculs dans le même processus ; option `INSTALL_SEMANTIC` qui installe PyTorch | Aucune : passe par `web` |
| `minio` | Compilé depuis les sources, version épinglée | Stockage des MP4/PDF, volume `minio_data` | `127.0.0.1:9010` pour les URL signées |
| `web` | Build Node 22 puis Nginx 1.27 | Sert le React compilé et relaie `/api/` vers `api:8000` | `127.0.0.1:8013` |

Bonnes pratiques à reprendre : secrets obligatoires via `${VAR:?message}`, ports liés à `127.0.0.1`, healthcheck sur la base, image Nginx multi-étapes, utilisateur non root, version des modèles d'embeddings épinglée, cache des modèles dans un volume.

Ce qu'on fait différemment, et pourquoi :
1. **Les calculs sortent de l'API.** Chez le prof, le calcul tourne dans le processus web. Chez nous, le scoring des interactions, la popularité, les profils, les embeddings et l'entraînement collaboratif tournent en continu : ils vont dans un conteneur `worker` séparé, pour que l'API reste rapide.
2. **Une image API légère, une image worker lourde.** PyTorch et sentence-transformers ne sont nécessaires que pour calculer les embeddings. Les vecteurs sont stockés dans pgvector, donc l'API n'a pas besoin de PyTorch.
3. **Des tâches planifiées** (imports d'actualités, recalculs périodiques) : un `scheduler` et une file de tâches.
4. **Migrations dans un conteneur d'une seule exécution**, avant le démarrage de l'API et du worker.

---

## 2. Vue d'ensemble

```
                    Navigateur
                        │  http://localhost:8080
                        ▼
┌──────────────────── réseau "edge" ─────────────────────┐
│  web (Nginx + React compilé)                           │
│     /        → fichiers statiques                      │
│     /api/    → api:8000                                │
└──────────────────────┬─────────────────────────────────┘
                       │
┌──────────────────── réseau "backend" (interne) ────────────────────────┐
│                                                                         │
│  api (FastAPI) ──── lit/écrit ───▶ db (PostgreSQL 17 + pgvector)        │
│     │  enfile des tâches                ▲                               │
│     ▼                                   │                               │
│  redis (file de tâches + cache) ◀── scheduler (tâches périodiques)      │
│     │                                   │                               │
│     ▼                                   │                               │
│  worker (scoring, popularité, profils, embeddings, modèles, imports) ───┘
│     │                                                                   │
│     └──────▶ minio (images, vidéos, PDF, artefacts de modèles)          │
│                                                                         │
│  migrate (une seule exécution)   minio-init (une seule exécution)       │
│  simulator (profil "simulation", à la demande)                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Fiche de chaque conteneur

### 3.1 `web` : front-end
| Élément | Valeur proposée |
|---|---|
| Rôle | Servir l'application React (lecteur et admin) ; reverse proxy `/api/` vers l'API ; en-têtes de sécurité |
| Image | Construite depuis `frontend/` : étape `node:22-alpine` (`npm ci && npm run build`) puis `nginx:1.27-alpine` |
| Ports | `127.0.0.1:${WEB_PORT:-8080}:80` (seul point d'entrée public) |
| Volumes | Aucun en production ; en développement, remplacé par le serveur Vite (§6) |
| Variables | Aucune au lancement (l'URL d'API est relative : `/api`) |
| Dépend de | `api` (sain) |
| Réseaux | `edge` |
| Nginx | `client_max_body_size 200m` (uploads admin), `/api/` → `http://api:8000/`, `try_files` pour le routage React, `sendBeacon` autorisé sur `/api/events/batch`, en-têtes `X-Content-Type-Options`, `Referrer-Policy`, `Content-Security-Policy` |

### 3.2 `api` : backend HTTP
| Élément | Valeur proposée |
|---|---|
| Rôle | Authentification, catalogue, recherche, ingestion des événements, service des recommandations (lecture des listes et vecteurs précalculés + ajustement par session), routes admin, enfilement des tâches lourdes |
| Image | `backend/Dockerfile`, cible **`api`** : `python:3.12-slim`, dépendances légères (FastAPI, SQLAlchemy, psycopg, pgvector, scikit-learn, numpy, boto3, redis/rq), **sans PyTorch** |
| Commande | `uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --workers 2` |
| Ports | Aucun publié ; `8000` sur le réseau interne |
| Volumes | Aucun (sans état) |
| Variables | `DATABASE_URL`, `REDIS_URL`, `S3_ENDPOINT`, `S3_PUBLIC_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET_MEDIA`, `SESSION_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `COOKIE_SECURE`, `EVENTS_MAX_BATCH`, `LOG_LEVEL` |
| Dépend de | `migrate` (terminé avec succès), `db` (sain), `redis` (sain), `minio` (démarré) |
| Réseaux | `edge`, `backend` |
| Healthcheck | `GET /health` (vérifie la base et Redis) |

### 3.3 `worker` : exécution des fonctions du backend
| Élément | Valeur proposée |
|---|---|
| Rôle | Exécuter les tâches : agrégation des vues et calcul des scores d'interaction, popularité par fenêtre et tendances, profils utilisateurs, calcul des embeddings des nouveaux contenus, entraînement des modèles collaboratifs (item-kNN, ALS), co-occurrences de sessions, évaluations hors ligne, imports de contenus, extraction du texte des PDF |
| Image | Même `backend/Dockerfile`, cible **`worker`** : base de la cible `api` + PyTorch CPU, sentence-transformers, `implicit`, pypdf, spaCy |
| Commande | `rq worker --url $REDIS_URL high default low` (ou Celery, voir §9) |
| Ports | Aucun |
| Volumes | `model_cache:/app/model-cache` (modèles Hugging Face), `./data/corpus:/data/corpus:ro` (fichiers du corpus statique) |
| Variables | Celles de l'API + `EMBEDDING_MODEL`, `EMBEDDING_REVISION`, `HF_HOME`, `NEWS_API_KEY` (phase 3), `WORKER_CONCURRENCY` |
| Dépend de | `migrate`, `db`, `redis`, `minio` |
| Réseaux | `backend` (+ sortie internet pour les imports d'API en phase 3) |
| Mise à l'échelle | `docker compose up --scale worker=2` possible, car les tâches sont idempotentes |

Files de priorité proposées :
- `high` : recalcul du profil d'un utilisateur après une interaction forte (like, favori, pas intéressé).
- `default` : scoring incrémental, popularité, embeddings des nouveaux contenus.
- `low` : entraînement des modèles, évaluations, imports massifs.

### 3.4 `scheduler` : tâches périodiques
| Élément | Valeur proposée |
|---|---|
| Rôle | Déposer les tâches périodiques dans Redis ; ne calcule rien lui-même |
| Image | Même image que `api` (légère) |
| Commande | `python -m app.scheduler` (APScheduler ou rq-scheduler) |
| Planning proposé | toutes les 5 min : scoring incrémental et popularité 24 h ; toutes les 15 min : profils et tendances ; toutes les heures : item-kNN, co-occurrences, ALS ; chaque nuit : réindexation complète et purge selon la rétention ; phase 3 : import d'actualités toutes les 30 min |
| Ports, volumes | Aucun |
| Dépend de | `redis`, `migrate` |
| Réseaux | `backend` |

### 3.5 `db` : PostgreSQL + pgvector
| Élément | Valeur proposée |
|---|---|
| Image | `pgvector/pgvector:pg17` (PostgreSQL 17 avec l'extension vecteurs) |
| Ports | Aucun publié (option développement : `127.0.0.1:5433:5432` pour un client SQL) |
| Volumes | `postgres_data:/var/lib/postgresql/data` |
| Variables | `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` (obligatoire) |
| Healthcheck | `pg_isready` |
| Réseaux | `backend` |

### 3.6 `migrate` : migrations (une seule exécution)
| Élément | Valeur proposée |
|---|---|
| Rôle | `alembic upgrade head`, création de l'extension `vector`, création du compte admin initial, puis arrêt |
| Image | Image `api` |
| Dépend de | `db` (sain) |
| Redémarrage | `restart: "no"` ; `api`, `worker` et `scheduler` attendent `service_completed_successfully` |

### 3.7 `redis` : file de tâches et cache
| Élément | Valeur proposée |
|---|---|
| Rôle | File des tâches du worker ; cache des listes de recommandations et compteurs temps réel (vues de la dernière heure pour les tendances) |
| Image | `redis:7.4-alpine` |
| Volumes | `redis_data:/data` (persistance AOF, pour ne pas perdre les tâches en attente) |
| Healthcheck | `redis-cli ping` |
| Réseaux | `backend` |

### 3.8 `minio` : stockage objet
| Élément | Valeur proposée |
|---|---|
| Rôle | Images, vidéos, PDF, miniatures, artefacts des modèles entraînés |
| Image | Image officielle épinglée par date de version (ou compilation depuis les sources comme le prof) |
| Ports | `127.0.0.1:9010:9000` pour les URL signées lues par le navigateur ; console `127.0.0.1:9011:9001` en développement seulement |
| Volumes | `minio_data:/data` |
| Variables | `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` |
| Réseaux | `backend` |

### 3.9 `minio-init` : création des buckets (une seule exécution)
Image `minio/mc` épinglée. Crée les buckets `media` (privé) et `models` (privé), puis s'arrête. Dépend de `minio`.

### 3.10 `simulator` : lecteurs virtuels (à la demande)
| Élément | Valeur proposée |
|---|---|
| Rôle | Lancer des lecteurs virtuels (personas) qui **utilisent le vrai site** via `web` et produisent des événements par le vrai tracker ; comptes marqués `is_synthetic` |
| Image | `simulator/Dockerfile` basé sur l'image officielle Playwright Python épinglée |
| Profil Compose | `simulation` : ne démarre que avec `docker compose --profile simulation run simulator --personas 20 --minutes 30` |
| Variables | `TARGET_URL=http://web`, `SIM_ADMIN_TOKEN` (création des comptes synthétiques), `SIM_SEED` |
| Réseaux | `edge` (il passe par le front-end, comme un vrai navigateur) |

### 3.11 Outils de développement (profil `tools`, facultatifs)
- `adminer` ou `pgadmin` : inspecter la base, port `127.0.0.1:8081`.
- Extension possible plus tard : `prometheus` + `grafana` pour la latence des recommandations et le débit d'événements.

---

## 4. Réseaux

| Réseau | Membres | Pourquoi |
|---|---|---|
| `edge` | `web`, `api`, `simulator` | Seul `web` est publié ; le navigateur ne parle jamais directement à la base ou à Redis |
| `backend` (`internal: true` sauf besoin d'internet) | `api`, `worker`, `scheduler`, `migrate`, `db`, `redis`, `minio`, `minio-init` | Les données restent isolées du réseau public |

Le `worker` a besoin d'internet pour télécharger le modèle d'embeddings au premier lancement et pour les imports d'API en phase 3 : on le rattache aussi à un réseau `egress` non interne, ou on garde `backend` non interne au début (choix au §9).

## 5. Volumes

| Volume | Monté dans | Contenu | Sauvegarde |
|---|---|---|---|
| `postgres_data` | `db` | Comptes, contenus, événements, scores, configurations | `pg_dump` régulier |
| `minio_data` | `minio` | Médias et artefacts de modèles | Copie `mc mirror` |
| `redis_data` | `redis` | Tâches en attente, cache | Non critique |
| `model_cache` | `worker` | Modèles Hugging Face téléchargés | Non critique |
| `./data/corpus` (montage en lecture seule) | `worker` | Fichiers sources du corpus statique (phase 1) | Versionnés à part (ou téléchargés par script) |

## 6. Développement et production

| Aspect | `compose.yaml` (base, proche production) | `compose.override.yaml` (développement, chargé automatiquement) |
|---|---|---|
| Front-end | Nginx + build compilé | Serveur Vite avec rechargement à chaud, code monté en volume |
| API | uvicorn, 2 processus | `uvicorn --reload`, code monté en volume |
| Worker | Image construite | Code monté, redémarrage manuel |
| Base | Pas de port publié | `127.0.0.1:5433` publié |
| Outils | | Profil `tools` disponible |

## 7. Ébauche du Compose (à discuter, non exécutée)

```yaml
name: newslab

x-backend-env: &backend-env
  DATABASE_URL: postgresql+psycopg://${POSTGRES_USER:-newslab}:${POSTGRES_PASSWORD:?Copiez .env.example vers .env}@db:5432/${POSTGRES_DB:-newslab}
  REDIS_URL: redis://redis:6379/0
  S3_ENDPOINT: http://minio:9000
  S3_PUBLIC_ENDPOINT: ${S3_PUBLIC_ENDPOINT:-http://localhost:9010}
  S3_ACCESS_KEY: ${S3_ACCESS_KEY:?Définir S3_ACCESS_KEY}
  S3_SECRET_KEY: ${S3_SECRET_KEY:?Définir S3_SECRET_KEY}
  S3_BUCKET_MEDIA: media
  S3_BUCKET_MODELS: models
  SESSION_SECRET: ${SESSION_SECRET:?Définir SESSION_SECRET}
  LOG_LEVEL: ${LOG_LEVEL:-info}

x-backend-deps: &backend-deps
  migrate: { condition: service_completed_successfully }
  db:      { condition: service_healthy }
  redis:   { condition: service_healthy }
  minio:   { condition: service_started }

services:
  web:
    build: ./frontend
    ports: ["127.0.0.1:${WEB_PORT:-8080}:80"]
    depends_on: { api: { condition: service_healthy } }
    networks: [edge]

  api:
    build: { context: ./backend, target: api }
    command: uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --workers 2
    environment:
      <<: *backend-env
      ADMIN_EMAIL: ${ADMIN_EMAIL:?Définir ADMIN_EMAIL}
      COOKIE_SECURE: ${COOKIE_SECURE:-false}
    depends_on: *backend-deps
    healthcheck:
      test: [CMD, python, -c, "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 10s
      retries: 6
    networks: [edge, backend]

  worker:
    build: { context: ./backend, target: worker }
    command: rq worker --url redis://redis:6379/0 high default low
    environment:
      <<: *backend-env
      EMBEDDING_MODEL: ${EMBEDDING_MODEL:-sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2}
      EMBEDDING_REVISION: ${EMBEDDING_REVISION:?Épingler la révision du modèle}
      HF_HOME: /app/model-cache
      NEWS_API_KEY: ${NEWS_API_KEY:-}
    volumes:
      - model_cache:/app/model-cache
      - ./data/corpus:/data/corpus:ro
    depends_on: *backend-deps
    networks: [backend]

  scheduler:
    build: { context: ./backend, target: api }
    command: python -m app.scheduler
    environment: *backend-env
    depends_on: *backend-deps
    networks: [backend]

  migrate:
    build: { context: ./backend, target: api }
    command: python -m app.migrate        # alembic upgrade head + extension vector + admin initial
    environment:
      <<: *backend-env
      ADMIN_EMAIL: ${ADMIN_EMAIL:?Définir ADMIN_EMAIL}
      ADMIN_PASSWORD: ${ADMIN_PASSWORD:?Définir ADMIN_PASSWORD}
    depends_on: { db: { condition: service_healthy } }
    restart: "no"
    networks: [backend]

  db:
    image: pgvector/pgvector:pg17
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-newslab}
      POSTGRES_USER: ${POSTGRES_USER:-newslab}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Copiez .env.example vers .env}
    volumes: [postgres_data:/var/lib/postgresql/data]
    healthcheck:
      test: [CMD-SHELL, 'pg_isready -U "$${POSTGRES_USER}" -d "$${POSTGRES_DB}"']
      interval: 5s
      retries: 10
    networks: [backend]

  redis:
    image: redis:7.4-alpine
    command: redis-server --appendonly yes
    volumes: [redis_data:/data]
    healthcheck: { test: [CMD, redis-cli, ping], interval: 5s, retries: 10 }
    networks: [backend]

  minio:
    image: minio/minio:<version épinglée>
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${S3_ACCESS_KEY:?Définir S3_ACCESS_KEY}
      MINIO_ROOT_PASSWORD: ${S3_SECRET_KEY:?Définir S3_SECRET_KEY}
    ports: ["127.0.0.1:9010:9000"]
    volumes: [minio_data:/data]
    networks: [backend]

  minio-init:
    image: minio/mc:<version épinglée>
    entrypoint: >
      sh -c "mc alias set local http://minio:9000 $$S3_ACCESS_KEY $$S3_SECRET_KEY &&
             mc mb -p local/media local/models"
    environment:
      S3_ACCESS_KEY: ${S3_ACCESS_KEY}
      S3_SECRET_KEY: ${S3_SECRET_KEY}
    depends_on: [minio]
    restart: "no"
    networks: [backend]

  simulator:
    build: ./simulator
    profiles: [simulation]
    environment:
      TARGET_URL: http://web
      SIM_ADMIN_TOKEN: ${SIM_ADMIN_TOKEN:-}
      SIM_SEED: ${SIM_SEED:-42}
    depends_on: [web]
    networks: [edge]

  adminer:
    image: adminer:<version épinglée>
    profiles: [tools]
    ports: ["127.0.0.1:8081:8080"]
    networks: [backend]

networks:
  edge: {}
  backend: {}          # passer à internal: true quand les sorties internet seront isolées

volumes:
  postgres_data: {}
  minio_data: {}
  redis_data: {}
  model_cache: {}
```

`.env.example` listera : `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `SESSION_SECRET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_PUBLIC_ENDPOINT`, `WEB_PORT`, `EMBEDDING_MODEL`, `EMBEDDING_REVISION`, `NEWS_API_KEY` (vide jusqu'à la phase 3), `SIM_ADMIN_TOKEN`.

### Ordre de démarrage
`db`, `redis`, `minio` → `migrate`, `minio-init` → `api`, `worker`, `scheduler` → `web` → (`simulator` à la demande).

## 8. Organisation du code proposée

```
newslab/
├── compose.yaml
├── compose.override.yaml
├── .env.example
├── frontend/                 # conteneur web
│   ├── Dockerfile  nginx.conf
│   └── src/ (pages lecteur, pages admin, tracker/)
├── backend/                  # images api, worker, scheduler, migrate
│   ├── Dockerfile            # cibles : base → api → worker
│   ├── requirements/ (base.txt, api.txt, worker.txt)
│   ├── app/
│   │   ├── core/             # config, base de données, modèles SQLAlchemy, stockage
│   │   ├── api/              # routes FastAPI (auth, contents, events, recommendations, admin)
│   │   ├── recommenders/     # registre + un module par algorithme (partagé api/worker)
│   │   ├── scoring/          # vues, scores, profils
│   │   ├── importers/        # static_corpus, manual, news_api
│   │   ├── jobs/             # tâches exécutées par le worker
│   │   ├── scheduler.py
│   │   └── migrate.py
│   ├── migrations/
│   └── tests/
├── simulator/                # conteneur simulator (Playwright + personas)
├── data/corpus/              # fichiers du corpus statique (hors Git si volumineux)
└── docs/
```

Le Dockerfile du backend utilise des **cibles multi-étapes** : `base` (Python + dépendances communes), `api` (léger), `worker` (ajoute PyTorch CPU, sentence-transformers, `implicit`, spaCy). Le même code sert aux deux, mais l'image de l'API reste petite et démarre vite.

## 9. Choix ouverts sur l'architecture

| # | Question | Options |
|---|---|---|
| A1 | **File de tâches** | A ★ Redis + RQ : simple, lisible pour un projet pédagogique. B Celery + Redis : plus complet (planification intégrée, réessais) mais plus lourd. C Pas de file : un worker unique avec APScheduler qui exécute tout lui-même (1 conteneur de moins, mais pas de tâches à la demande depuis l'admin). |
| A2 | **Scheduler séparé** | A ★ Conteneur `scheduler` distinct (un seul planificateur même avec plusieurs workers). B Planification dans le worker (impossible de dupliquer le worker sans doublons). |
| A3 | **Embeddings** | A ★ Calculés dans le worker, stockés dans pgvector. B Conteneur `embedder` dédié exposant une petite API (utile si on veut encoder les requêtes de recherche en temps réel). |
| A4 | **Accès aux médias** | A ★ URL signées MinIO exposées sur `127.0.0.1:9010`, comme le prof. B Relais par Nginx sous `/media/` (une seule origine, configuration plus délicate des signatures). |
| A5 | **Simulateur** | A ★ Conteneur Playwright dans le profil `simulation`. B Script lancé hors Docker. |
| A6 | **Isolation réseau** | A ★ `backend` non interne au début, puis réseau `egress` dédié au worker. B Isolation stricte dès le départ. |
| A7 | **Supervision** | A ★ Logs Docker + page admin de santé. B Ajouter Prometheus + Grafana (profil `monitoring`). |

## 10. Lien avec les sources de contenu

Les trois phases d'alimentation du catalogue (voir cahier des charges §3.4) passent par les conteneurs ainsi :

| Phase | Déclenchement | Conteneur qui exécute |
|---|---|---|
| 1. Corpus statique | Admin clique « Importer le corpus » ou commande `docker compose run --rm worker python -m app.importers.static_corpus` | `worker` (lit `/data/corpus`, envoie les médias dans MinIO) |
| 2. Ajout manuel | Formulaire admin (article, vidéo, galerie, document) | `api` (enregistrement + upload MinIO), puis `worker` pour embeddings et extraction PDF |
| 3. API d'actualités | `scheduler` toutes les 30 min, ou bouton admin | `worker` (appel de l'API externe, dédoublonnage, enregistrement) |
