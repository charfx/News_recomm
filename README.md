# Le Quotidien : plateforme d'actualités avec moteur de recommandation

Projet pédagogique, pensé comme un projet professionnel : un site d'actualités (**Le Quotidien**) qui recommande des articles à chaque lecteur à partir de ses propres interactions (clics, « J'aime », partages).

Le projet compare plusieurs familles d'algorithmes :

| Stratégie | Rôle | Technique |
|---|---|---|
| `popularity_ranker` | Démarrage à froid (utilisateur sans historique) | Ranker **LightGBM (LambdaRank)** entraîné sur l'historique d'impressions MIND |
| `tfidf` | Recommandation par le contenu | Vecteurs **TF-IDF** (scikit-learn) + similarité cosinus avec le profil utilisateur |
| `embedding` | Recommandation sémantique | Embeddings **all-MiniLM-L6-v2** (384 dim.) stockés dans **pgvector**, recherche des plus proches voisins (index HNSW) |

> Les documents de conception sont à la racine : [`cahier-des-charges-actualites.md`](cahier-des-charges-actualites.md) (besoins, algorithmes, données, plan) et [`architecture-conteneurs.md`](architecture-conteneurs.md) (architecture cible en conteneurs). Les règles de travail sont dans [`Instruction.md`](Instruction.md).

---

## Sommaire

1. [Architecture](#architecture)
2. [Arborescence](#arborescence)
3. [Données](#données)
4. [Modèle de données](#modèle-de-données)
5. [API](#api)
6. [Algorithmes de recommandation](#algorithmes-de-recommandation)
7. [Installation et lancement](#installation-et-lancement)
8. [Pipeline de données et d'entraînement](#pipeline-de-données-et-dentraînement)
9. [Scripts de test](#scripts-de-test)
10. [Limites connues et pistes](#limites-connues-et-pistes)

---

## Architecture

Trois services orchestrés par Docker Compose :

```
 Navigateur ──► frontend (nginx, :5500) ── HTML/CSS/JS statique
     │
     └── fetch ──► backend (FastAPI + Uvicorn, :8000)
                       │   - TF-IDF en mémoire
                       │   - Ranker de popularité en mémoire
                       ▼
                  db (PostgreSQL 17 + pgvector, :5432)
                       - articles, utilisateurs, sessions, événements
                       - embeddings 384 dim. + index HNSW
                       - historique d'impressions (hist_impressions)
```

| Service | Image / build | Port | Détails |
|---|---|---|---|
| `db` | `pgvector/pgvector:pg17` | 5432 | Volume persistant `pgdata`, healthcheck `pg_isready` |
| `backend` | `Backend/Dockerfile` (Python 3.12-slim) | 8000 | Démarre après que `db` soit *healthy* |
| `frontend` | `Frontend/Dockerfile` (nginx:alpine) | 5500 → 80 | Dossier `Frontend/` monté en lecture seule |

Au démarrage, le backend :
1. charge le modèle LightGBM (`ranker.joblib`), calcule les features de popularité en SQL et garde en mémoire le top 100 des articles ;
2. lit tous les articles depuis PostgreSQL et entraîne le vectoriseur TF-IDF ;
3. prépare le recommandeur par embeddings (les calculs se font ensuite dans PostgreSQL).

---

## Arborescence

```
News_recomm/
├── docker-compose.yml          # db + backend + frontend
├── alembic.ini                 # configuration des migrations (script_location = Backend/alembic)
├── .env.example                # variables d'environnement à copier dans .env
├── cahier-des-charges-actualites.md
├── architecture-conteneurs.md
├── Instruction.md
├── data/                       # (ignoré par git) jeux de données MIND et fichiers dérivés
│   ├── news.tsv / news.xlsx / news_clean.csv
│   ├── behaviors.tsv
│   └── features.parquet        # généré par build_features.py
├── Backend/
│   ├── Dockerfile
│   ├── requirement.txt
│   ├── alembic/                # migrations de schéma
│   │   └── versions/
│   ├── DB_execution/           # scripts ponctuels d'alimentation de la base
│   │   ├── seed_news.py        # import des articles
│   │   └── compute_embedding.py# calcul des embeddings
│   └── app/
│       ├── main.py             # API FastAPI
│       ├── DB.py               # moteur SQLAlchemy + session
│       ├── Models.py           # modèles ORM
│       ├── data_loader.py      # lecture des articles / événements en DataFrame
│       ├── import_behavior.py  # import de behaviors.tsv → hist_impressions
│       ├── build_features.py   # features de popularité → features.parquet
│       ├── train_ranker.py     # entraînement + évaluation du ranker LightGBM
│       ├── ML_ranker_saved/ranker.joblib
│       └── Recommenders/
│           ├── Base.py                   # interface abstraite
│           ├── Tf_IDF.py                 # TF-IDF + profil utilisateur
│           ├── Embedding.py              # embeddings + pgvector
│           ├── Popularity_cold_start.py  # ranker de popularité
│           ├── KNN.py, Popularity.py     # (vides, à venir)
├── Frontend/
│   ├── Dockerfile
│   ├── index.html              # page « Le Quotidien »
│   ├── app.js                  # session, tracking, affichage
│   └── style.css
└── test.py, testdb.py, testidf.py, test_embedding.py   # scripts de vérification
```

---

## Données

Le corpus provient du jeu de données public **MIND** (Microsoft News Dataset), placé dans `data/` (non versionné) :

- **`news.tsv`** → nettoyé en **`news_clean.csv`** (séparateur `;`, colonnes `News_id`, `Category`, `Subcategory`, `Title`, `Abstract`, `URL`) : le catalogue d'articles.
- **`behaviors.tsv`** : historique d'impressions (quels articles ont été affichés à un utilisateur, lesquels ont été cliqués). Il sert **uniquement** à entraîner le ranker de popularité pour le démarrage à froid.

> Règle du projet : les interactions utilisées pour personnaliser les recommandations proviennent **uniquement des écouteurs du site** (table `events`), jamais de logs importés.

Les dates de publication des articles sont simulées (aléatoires sur 180 jours, graine fixe) au moment de l'import.

---

## Modèle de données

Schéma géré par **Alembic** (`Backend/alembic/versions/`) :

| Table | Contenu |
|---|---|
| `users` | `id`, `email` (unique), `password_hash`, `role` (`user`/`admin`), `created_at` |
| `news` | `id` (ex. `N55528`), `category`, `subcategory`, `title`, `abstract`, `url`, `published_at`, `embedding vector(384)` |
| `user_sessions` | `id` (UUID), `user_id`, `started_at`, `ended_at` |
| `events` | `user_id`, `session_id`, `news_id`, `event_type`, `weight`, `ts` (index sur `user_id` et `news_id`) |
| `user_item_scores` | score agrégé utilisateur × article (prévu, pas encore alimenté) |
| `hist_impressions` | historique MIND éclaté : `impression_id`, `user_id`, `ts`, `news_id`, `position`, `clicked` (index sur `ts` et `news_id`) |

Ordre des migrations :

```
7c9caa97c69b  create initial tables
  └─ b963a70c81ea  add news embedding (extension vector + colonne)
       └─ 9a12e814ef60  add hnsw index on news embedding (vector_cosine_ops)
            └─ 14efaefa3476  create hist_impressions
```

---

## API

Base : `http://127.0.0.1:8000` — documentation interactive sur **`/docs`** (Swagger) et `/redoc`.

| Méthode | Route | Description |
|---|---|---|
| `GET` | `/news?limit=20&offset=0` | Derniers articles (tri par `published_at` décroissant) |
| `GET` | `/news/{news_id}` | Détail d'un article (404 si inconnu) |
| `POST` | `/login` | Corps `{"email": "..."}` → crée le compte s'il n'existe pas, ouvre une nouvelle session. Renvoie `{user_id, session_id}` |
| `POST` | `/events` | Corps `{user_id, session_id, news_id, event_type}` → enregistre une interaction |
| `GET` | `/recommendations?user_id=1&k=10&strategy=tfidf` | Recommandations (`strategy` = `tfidf` ou `embedding`). Renvoie `{strategy, items: [{id, category, title, score}]}` |

### Types d'événements et poids

| Événement | `click` | `read` | `scroll75` | `like` | `save` | `share` | `not_interested` | `bounce` |
|---|---|---|---|---|---|---|---|---|
| Poids | 1 | 2 | 1 | 3 | 3 | 4 | −4 | −1 |

`like`, `save`, `share` et `not_interested` sont **uniques** par couple (utilisateur, article) : un doublon renvoie `{"ok": true, "duplicate": true}` sans être réenregistré. Un type inconnu renvoie une erreur 400.

CORS autorisé pour `http://localhost:5500` et `http://127.0.0.1:5500`.

---

## Algorithmes de recommandation

### Profil utilisateur (commun à TF-IDF et embeddings)

1. On somme les poids des événements par article : `score(u, a) = Σ poids`.
2. On ne garde que les articles à score **positif**.
3. Chaque article est pondéré par son score et par une **décroissance temporelle** (demi-vie de 7 jours) :

   `w(a) = score(u, a) × 0.5^(âge_en_jours / 7)`

4. Le profil est la **moyenne pondérée** des vecteurs des articles : `profil = Σ w(a)·v(a) / Σ w(a)`.
5. Les articles déjà vus sont exclus des résultats.

Si l'utilisateur n'a aucune interaction positive → **démarrage à froid** (stratégie `popularity_ranker`), quel que soit l'algorithme choisi.

### TF-IDF (`Recommenders/Tf_IDF.py`)

- Texte = titre + résumé ; `TfidfVectorizer(stop_words="english", max_features=50000, min_df=2)`.
- Matrice articles × mots gardée en mémoire ; score = produit scalaire profil · article (cosinus, vecteurs normalisés L2).
- Fournit aussi `recommend(news_id, k)` : articles similaires à un article donné.

### Embeddings sémantiques (`Recommenders/Embedding.py`)

- Vecteurs de 384 dimensions produits par `sentence-transformers/all-MiniLM-L6-v2` (normalisés), stockés dans `news.embedding`.
- Le profil est normalisé puis la recherche se fait **dans PostgreSQL** avec l'opérateur de distance cosinus `<=>` de pgvector, accélérée par l'index **HNSW**. Score renvoyé = `1 − distance`.

### Popularité / démarrage à froid (`Recommenders/Popularity_cold_start.py`)

Un **LightGBM `LGBMRanker`** (objectif `lambdarank`) apprend à classer les articles d'une liste d'impressions à partir de features de popularité calculées **avant** l'instant de l'affichage (pas de fuite d'information) :

| Feature | Définition |
|---|---|
| `clicks_1h` | Clics sur l'article dans l'heure précédente |
| `clicks_24h` | Clics sur les 24 h précédentes |
| `imps_24h` | Affichages sur les 24 h précédentes |
| `ctr_smooth_24h` | CTR lissé : `(clics + 0.04 × 20) / (affichages + 20)` |
| `age_hours` | Heures depuis la première apparition de l'article |
| `cat_ctr_24h` | CTR lissé de la catégorie sur 24 h |

- Découpage **temporel** : jour 13 = validation, jour 14 = test, le reste = entraînement ; early stopping sur NDCG@10.
- Évaluation sur le test (AUC, MRR, NDCG@10) contre trois références : hasard, plus cliqués 24 h, CTR lissé 24 h.
- En production, les mêmes features sont recalculées en SQL à la fin de l'historique, et le top 100 est gardé en mémoire.

---

## Installation et lancement

### Prérequis

- Docker et Docker Compose
- Python 3.12 (pour les migrations et les scripts d'alimentation lancés en local)
- Les fichiers MIND dans `data/`

### 1. Variables d'environnement

```bash
cp .env.example .env
```

```env
POSTGRES_USER=news
POSTGRES_PASSWORD=news_pwd
POSTGRES_DB=news_reco
DATABASE_URL=postgresql+psycopg://news:news_pwd@localhost:5432/news_reco
```

`DATABASE_URL` (avec `localhost`) sert aux scripts lancés depuis la machine hôte ; dans Docker, le backend utilise `db:5432` (surchargé dans `docker-compose.yml`).

### 2. Démarrer la base

```bash
docker compose up -d db
```

### 3. Environnement Python local

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (Linux/macOS : source .venv/bin/activate)
pip install -r Backend/requirement.txt
pip install sentence-transformers torch   # uniquement pour compute_embedding.py
```

### 4. Créer le schéma

Depuis la racine du projet :

```bash
alembic upgrade head
```

### 5. Alimenter la base et entraîner le ranker

Voir [la section suivante](#pipeline-de-données-et-dentraînement). Tous les scripts se lancent **depuis la racine** en tant que modules (`python -m ...`) car les imports sont de la forme `Backend.app...`.

### 6. Lancer toute l'application

```bash
docker compose up -d --build
```

- Site : <http://localhost:5500>
- API : <http://localhost:8000> — Swagger : <http://localhost:8000/docs>

À la première visite, le site demande un email (connexion simplifiée sans mot de passe), puis :
- la colonne **« À la une »** affiche les derniers articles ;
- la colonne **« Pour vous »** affiche les recommandations (badge « Tendances » en démarrage à froid) ;
- un clic, « J'aime » ou « Partager » envoie un événement, et un bouton propose de rafraîchir les recommandations ;
- le sélecteur **Algorithme** (en haut à droite) bascule entre TF-IDF et embeddings.

Lancement du backend hors Docker (développement) :

```bash
uvicorn Backend.app.main:app --reload --port 8000
```

---

## Pipeline de données et d'entraînement

À exécuter dans l'ordre, depuis la racine, une fois la base migrée :

| # | Commande | Effet |
|---|---|---|
| 1 | `python -m Backend.DB_execution.seed_news` | Importe `data/news_clean.csv` dans `news` (rejouable : vide la table d'abord) |
| 2 | `python -m Backend.DB_execution.compute_embedding` | Calcule les embeddings des articles qui n'en ont pas (GPU si disponible, par paquets de 2000 ; rejouable) |
| 3 | `python -m Backend.app.import_behavior` | Importe `data/behaviors.tsv` dans `hist_impressions` via `COPY` (rejouable : `TRUNCATE` d'abord) |
| 4 | `python -m Backend.app.build_features` | Construit les features de popularité → `data/features.parquet` |
| 5 | `python -m Backend.app.train_ranker` | Entraîne et évalue le ranker LightGBM, puis sauvegarde le modèle |

> ⚠️ `train_ranker.py` sauvegarde dans `Backend/app/models/ranker.joblib`, alors que l'API charge `Backend/app/ML_ranker_saved/ranker.joblib`. Après un réentraînement, copier le fichier vers `ML_ranker_saved/` (ou aligner les deux chemins).

Les étapes 1 à 3 sont nécessaires au démarrage de l'API : le backend lit les articles (TF-IDF) et `hist_impressions` (popularité) au lancement.

---

## Scripts de test

Scripts de vérification manuelle, à lancer depuis la racine (`python -m test`, etc.) :

| Script | Vérifie |
|---|---|
| `testdb.py` | Connexion à PostgreSQL (base et utilisateur courants) |
| `test.py` | Entraînement TF-IDF et articles similaires à `N55528` |
| `testidf.py` | Profil TF-IDF de l'utilisateur 1 (mots dominants) et ses recommandations |
| `test_embedding.py` | Recommandations par embeddings pour l'utilisateur 1 |

---

## Limites connues et pistes

- **Authentification** simplifiée : pas de mot de passe (`password_hash = "-"`), identifiant stocké dans le `localStorage`.
- **TF-IDF en mémoire** : entraîné au démarrage ; un nouvel article n'est pris en compte qu'après redémarrage de l'API.
- **Popularité figée** : le classement est calculé une seule fois au démarrage, à partir de la fin de l'historique MIND.
- `user_item_scores` et `user_sessions.ended_at` ne sont pas encore alimentés ; `KNN.py` et `Popularity.py` sont vides.
- L'image backend n'embarque pas `sentence-transformers`/`torch` : les embeddings sont calculés hors conteneur.
- Dans `Frontend/Dockerfile`, le chemin `/Usr/share/nginx/html` contient une majuscule ; cela fonctionne aujourd'hui grâce au volume monté par Compose, mais le `COPY` ne sert à rien en l'état.
- L'URL de l'API est codée en dur dans `Frontend/app.js` (`http://127.0.0.1:8000`).

**Pistes** (voir le cahier des charges) : filtrage collaboratif (KNN, factorisation), recommandations par session, hybrides, diversité et ré-ordonnancement, interface d'administration pour choisir l'algorithme, évaluation hors ligne sur nos propres événements, conteneurs `worker`/`scheduler`/`redis` de l'architecture cible.
