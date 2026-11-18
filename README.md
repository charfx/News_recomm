# Le Quotidien : plateforme d'actualités avec moteur de recommandation

Projet pédagogique, pensé comme un projet professionnel : un site d'actualités (**Le Quotidien**) qui recommande des articles à chaque lecteur à partir de ses propres interactions (clics, « J'aime », partages).

Le site distingue deux rôles :

- **Lecteur** (`user`) : crée un compte, lit les articles, interagit avec eux et reçoit la colonne « Pour vous ».
- **Administrateur** (`admin`) : authentifié, il **contrôle l'algorithme de recommandation** utilisé pour tous les lecteurs et dispose d'un espace d'administration avec deux parties, **Interactions** et **Algorithmes**, depuis lesquelles il gère l'ensemble du moteur.

Algorithmes disponibles aujourd'hui :

| Stratégie | Rôle | Technique |
|---|---|---|
| `popularity_ranker` | Démarrage à froid (utilisateur sans historique) | Ranker **LightGBM (LambdaRank)** entraîné sur l'historique d'impressions MIND |
| `tfidf` | Recommandation par le contenu | Vecteurs **TF-IDF** (scikit-learn) + similarité cosinus avec le profil utilisateur |
| `embedding` | Recommandation sémantique | Embeddings **all-MiniLM-L6-v2** (384 dim.) stockés dans **pgvector**, recherche des plus proches voisins |

> Les documents de conception sont à la racine : [`cahier-des-charges-actualites.md`](cahier-des-charges-actualites.md) (besoins, algorithmes, données, plan) et [`architecture-conteneurs.md`](architecture-conteneurs.md) (architecture cible en conteneurs). Les règles de travail sont dans [`Instruction.md`](Instruction.md).

---

## Sommaire

1. [Évolution du projet](#évolution-du-projet)
2. [Architecture](#architecture)
3. [Arborescence](#arborescence)
4. [Données](#données)
5. [Modèle de données](#modèle-de-données)
6. [Authentification et rôles](#authentification-et-rôles)
7. [Espace administrateur](#espace-administrateur)
8. [API](#api)
9. [Algorithmes de recommandation](#algorithmes-de-recommandation)
10. [Installation et lancement](#installation-et-lancement)
11. [Pipeline de données et d'entraînement](#pipeline-de-données-et-dentraînement)
12. [Scripts de test](#scripts-de-test)
13. [Limites connues](#limites-connues)
14. [Perspectives](#perspectives)

---

## Évolution du projet

| Étape | Contenu |
|---|---|
| **1. Socle** | Modèle de données (SQLAlchemy + Alembic), import du catalogue MIND dans PostgreSQL, première API FastAPI (`/news`). |
| **2. Dockerisation + TF-IDF** | Trois services fonctionnels (frontend nginx, backend FastAPI, PostgreSQL + pgvector) orchestrés par Docker Compose. Premier recommandeur par le contenu : **TF-IDF** avec profil utilisateur pondéré et décroissance temporelle. Suivi des interactions du site (table `events`, poids par type d'événement). |
| **3. Popularité, démarrage à froid, embeddings** | Import de `behaviors.tsv` dans `hist_impressions`, construction de features de popularité sans fuite temporelle, entraînement et évaluation d'un **ranker LightGBM (LambdaRank)** pour les nouveaux utilisateurs. Ajout des **embeddings sémantiques** (all-MiniLM-L6-v2) stockés dans pgvector. |
| **4. Authentification et administration** (état actuel) | Vraie **authentification** : inscription / connexion par email + mot de passe (hash **bcrypt**), jeton **JWT** (8 h) portant le rôle et la session. Rôle **admin** créé par script (`create_admin.py`). **L'algorithme n'est plus choisi par le client** : il est fixé par l'admin et stocké en base (`app_settings`), puis appliqué à tous les lecteurs. Espace d'administration avec les pages **Interactions** (statistiques et matrice utilisateurs × articles) et **Algorithmes** (description, formules, code, paramètres et activation de chaque algorithme). |

---

## Architecture

Trois services orchestrés par Docker Compose :

```
 Navigateur ──► frontend (nginx, :5500) ── HTML/CSS/JS statique
     │            login.html · index.html · algorithms.html · interactions.html
     │
     └── fetch + Authorization: Bearer <JWT> ──► backend (FastAPI + Uvicorn, :8000)
                       │   - authentification (bcrypt + JWT), contrôle du rôle admin
                       │   - TF-IDF en mémoire
                       │   - ranker de popularité en mémoire
                       ▼
                  db (PostgreSQL 17 + pgvector, :5432)
                       - articles, utilisateurs, sessions, événements
                       - réglages de l'application (algorithme actif)
                       - embeddings 384 dim.
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
│   ├── create_admin.py         # crée ou promeut un compte administrateur
│   ├── alembic/                # migrations de schéma
│   │   └── versions/
│   ├── DB_execution/           # scripts ponctuels d'alimentation de la base
│   │   ├── seed_news.py        # import des articles
│   │   └── compute_embedding.py# calcul des embeddings
│   └── app/
│       ├── main.py             # API FastAPI (public, lecteur, admin)
│       ├── auth.py             # bcrypt, JWT, dépendances get_current_user / require_admin
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
│   ├── common.js               # API, authFetch (jeton), requireAdmin, en-tête, toasts
│   ├── login.html / login.css / login.js      # connexion et inscription
│   ├── index.html / app.js     # page « Le Quotidien » (À la une + Pour vous)
│   ├── interactions.html / interactions.js    # admin : interactions des lecteurs
│   ├── algorithms.html / algorithms.js        # admin : algorithmes de recommandation
│   ├── mock-interactions.json, mock-algorithms.json  # données de démonstration (repli)
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
| `users` | `id`, `email` (unique), `password_hash` (bcrypt), `role` (`user`/`admin`), `created_at` |
| `news` | `id` (ex. `N55528`), `category`, `subcategory`, `title`, `abstract`, `url`, `published_at`, `embedding vector(384)` |
| `user_sessions` | `id` (UUID), `user_id`, `started_at`, `ended_at` — une session est ouverte à chaque connexion |
| `events` | `user_id`, `session_id`, `news_id`, `event_type`, `weight`, `ts` (index sur `user_id` et `news_id`) |
| `user_item_scores` | score agrégé utilisateur × article (prévu, pas encore alimenté) |
| `app_settings` | `key`, `value` — réglages globaux, dont `active_algorithm` choisi par l'admin |
| `hist_impressions` | historique MIND éclaté : `impression_id`, `user_id`, `ts`, `news_id`, `position`, `clicked`. Créée et indexée par `import_behavior.py` (hors modèles ORM) |

Ordre des migrations :

```
7c9caa97c69b  create initial tables
  └─ b963a70c81ea  add news embedding (extension vector + colonne)
       └─ 9a12e814ef60  add hnsw index on news embedding (vector_cosine_ops)
            └─ 14efaefa3476  create hist_impressions
                 └─ ebc5c46065f0  app_settings
```

---

## Authentification et rôles

- **Inscription** (`POST /register`) et **connexion** (`POST /login`) par email + mot de passe (6 caractères minimum). Le mot de passe est stocké haché avec **bcrypt**.
- Chaque connexion ouvre une ligne dans `user_sessions` et renvoie un **jeton JWT** (HS256, valable 8 h) contenant `user_id`, `role` et `session_id`. Le secret est lu dans la variable `JWT_SECRET`.
- Le frontend garde le jeton dans le `localStorage` et l'envoie dans l'en-tête `Authorization: Bearer …` (`authFetch` dans `common.js`). Un 401 renvoie automatiquement vers `login.html`.
- Les routes lecteur (`/me`, `/events`, `/recommendations`) exigent un jeton valide ; l'identité vient **du jeton**, jamais du corps de la requête.
- Les routes `/admin/*` exigent le rôle **admin** (`require_admin`, sinon 403). Masquer les menus côté navigateur n'est qu'un confort : la protection réelle est côté serveur.
- Un compte administrateur se crée (ou un compte existant est promu) avec :

  ```bash
  python -m Backend.create_admin admin@exemple.fr   # le mot de passe est demandé au clavier
  ```

---

## Espace administrateur

Une fois connecté, l'admin voit une barre de navigation **Articles · Algorithmes · Interactions** ainsi qu'un sélecteur d'algorithme sur la page d'accueil. C'est lui seul qui **contrôle l'algorithme de recommandation** : son choix est enregistré dans `app_settings` et s'applique immédiatement à la colonne « Pour vous » de **tous** les lecteurs.

### Partie « Interactions » (`interactions.html`)

Vue d'ensemble de ce que font les lecteurs, alimentée par `GET /admin/interactions` (graphiques dessinés en HTML/SVG, sans librairie) :

- **chiffres clés** : nombre d'utilisateurs, d'articles touchés, d'événements, et densité de la matrice utilisateurs × articles ;
- répartition **par type d'événement** et **par jour** ;
- **top 10 des articles** et **top catégories** (somme des poids) ;
- **matrice utilisateurs × articles** (utilisateurs les plus actifs × articles touchés par le plus de lecteurs), colorée selon le score : bleu = positif, rouge = négatif.

### Partie « Algorithmes » (`algorithms.html`)

Catalogue des algorithmes rangés par famille (popularité, contenu, collaboratif, hybride). Chaque carte présente :

- le principe, les étapes, la **formule** et les **limites** ;
- les **paramètres** réglables (curseurs avec min / défaut / max) ;
- une **visionneuse du code source** de l'algorithme ;
- un bouton **Activer** qui envoie `PUT /admin/settings` et fait de cet algorithme celui de tout le site.

Seuls les algorithmes réellement implémentés (`tfidf`, `embedding`) peuvent être activés ; les autres apparaissent « Non disponible ».

> Si une route d'administration n'existe pas encore côté serveur (404), la page se rabat sur un fichier JSON local (`mock-*.json`) et affiche le bandeau « Données de démonstration ». C'est actuellement le cas de `GET /admin/algorithms`.

---

## API

Base : `http://127.0.0.1:8000` — documentation interactive sur **`/docs`** (Swagger) et `/redoc`.

| Accès | Méthode | Route | Description |
|---|---|---|---|
| Public | `GET` | `/news?limit=20&offset=0` | Derniers articles (tri par `published_at` décroissant) |
| Public | `GET` | `/news/{news_id}` | Détail d'un article (404 si inconnu) |
| Public | `POST` | `/register` | `{email, password}` → crée le compte (409 s'il existe déjà) et renvoie `{token, role, email}` |
| Public | `POST` | `/login` | `{email, password}` → ouvre une session et renvoie `{token, role, email}` (401 si identifiants faux) |
| Connecté | `GET` | `/me` | `{user_id, role, session_id}` lus dans le jeton |
| Connecté | `POST` | `/events` | `{news_id, event_type}` → enregistre une interaction pour l'utilisateur et la session du jeton |
| Connecté | `GET` | `/recommendations?k=10` | Recommandations avec l'algorithme actif choisi par l'admin. Renvoie `{algorithm, strategy, items: [{id, category, title, score}]}` |
| Admin | `GET` | `/admin/interactions?max_users=15&max_items=20` | Statistiques et matrice utilisateurs × articles |
| Admin | `PUT` | `/admin/settings` | `{algorithm, params}` → change l'algorithme actif (400 si non implémenté) |

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

Si l'utilisateur n'a aucune interaction positive → **démarrage à froid** (stratégie `popularity_ranker`), quel que soit l'algorithme activé par l'admin. La réponse indique alors `algorithm` (celui de l'admin) et `strategy: "popularity_ranker"` (celui réellement utilisé).

### TF-IDF (`Recommenders/Tf_IDF.py`)

- Texte = titre + résumé ; `TfidfVectorizer(stop_words="english", max_features=50000, min_df=2)`.
- Matrice articles × mots gardée en mémoire ; score = produit scalaire profil · article (cosinus, vecteurs normalisés L2).
- Fournit aussi `recommend(news_id, k)` : articles similaires à un article donné.

### Embeddings sémantiques (`Recommenders/Embedding.py`)

- Vecteurs de 384 dimensions produits par `sentence-transformers/all-MiniLM-L6-v2` (normalisés), stockés dans `news.embedding`.
- Le profil est normalisé puis la recherche se fait **dans PostgreSQL** avec l'opérateur de distance cosinus `<=>` de pgvector. Score renvoyé = `1 − distance`.

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
JWT_SECRET=change-moi-par-une-longue-phrase-secrete
```

- `DATABASE_URL` (avec `localhost`) sert aux scripts lancés depuis la machine hôte ; dans Docker, le backend utilise `db:5432` (surchargé dans `docker-compose.yml`).
- `JWT_SECRET` est **obligatoire** : l'API refuse de démarrer sans lui. Remplacez la valeur d'exemple par une longue chaîne aléatoire.

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

### 5. Alimenter la base, entraîner le ranker, créer l'admin

Voir [la section suivante](#pipeline-de-données-et-dentraînement). Tous les scripts se lancent **depuis la racine** en tant que modules (`python -m ...`) car les imports sont de la forme `Backend.app...`.

### 6. Lancer toute l'application

```bash
docker compose up -d --build
```

- Site : <http://localhost:5500> (redirige vers `login.html` sans jeton)
- API : <http://localhost:8000> — Swagger : <http://localhost:8000/docs>

Côté **lecteur** :
- création de compte ou connexion sur `login.html` ;
- la colonne **« À la une »** affiche les derniers articles ;
- la colonne **« Pour vous »** affiche les recommandations (badge « Tendances » en démarrage à froid) ;
- un clic, « J'aime » ou « Partager » envoie un événement, et un bouton propose de rafraîchir les recommandations.

Côté **admin** (compte créé avec `create_admin.py`) :
- sélecteur **Algorithme** en haut de la page d'accueil, appliqué à tous les lecteurs ;
- pages **Algorithmes** et **Interactions** (voir [Espace administrateur](#espace-administrateur)).

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
| 3 | `python -m Backend.app.import_behavior` | Crée `hist_impressions` si besoin, importe `data/behaviors.tsv` via `COPY` (rejouable : `TRUNCATE` d'abord) puis crée les index |
| 4 | `python -m Backend.app.build_features` | Construit les features de popularité → `data/features.parquet` |
| 5 | `python -m Backend.app.train_ranker` | Entraîne et évalue le ranker LightGBM, puis le sauvegarde dans `Backend/app/ML_ranker_saved/ranker.joblib` |
| 6 | `python -m Backend.create_admin <email>` | Crée le compte administrateur (ou promeut un compte existant) |

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

## Limites connues

- **Migration `ebc5c46065f0`** : générée automatiquement, elle supprime aussi `hist_impressions` et l'index HNSW sur `news.embedding` (tables/index absents des modèles ORM). `import_behavior.py` recrée `hist_impressions`, mais l'index HNSW doit être recréé à la main ou ces lignes retirées de la migration.
- **Paramètres des algorithmes** : la page Algorithmes envoie les paramètres, mais seul le nom de l'algorithme est enregistré ; `GET /admin/algorithms` n'existe pas encore (repli sur `mock-algorithms.json`).
- **TF-IDF en mémoire** : entraîné au démarrage ; un nouvel article n'est pris en compte qu'après redémarrage de l'API. Même chose pour le classement de popularité, figé à la fin de l'historique MIND.
- L'image backend n'embarque pas `sentence-transformers`/`torch` : les embeddings sont calculés hors conteneur.
- Dans `Frontend/Dockerfile`, le chemin `/Usr/share/nginx/html` contient une majuscule ; cela fonctionne grâce au volume monté par Compose, mais le `COPY` ne sert à rien en l'état.
- L'URL de l'API est codée en dur dans `Frontend/common.js` et `Frontend/login.js`.

---

## Perspectives

Les prochaines étapes du moteur de recommandation, qui viendront s'ajouter au catalogue de la page **Algorithmes** et seront activables par l'admin :

1. **Embeddings + MMR (Maximal Marginal Relevance)** : ré-ordonner les candidats issus des embeddings pour équilibrer pertinence et diversité, afin d'éviter une colonne « Pour vous » remplie d'articles quasi identiques :

   `MMR(a) = λ · sim(a, profil) − (1 − λ) · max_{b ∈ sélection} sim(a, b)`

2. **Filtrage collaboratif par voisinage (KNN)** : s'appuyer sur la matrice utilisateurs × articles (celle visible dans la page Interactions) pour recommander ce qu'ont aimé les lecteurs les plus proches (« les lecteurs qui vous ressemblent ont aimé… »).
3. **Hybride** : combiner les scores du contenu (TF-IDF / embeddings), du collaboratif et de la popularité pour cumuler leurs forces et couvrir à la fois les nouveaux et les anciens lecteurs.
