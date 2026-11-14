# Cahier des charges : plateforme d'actualités multimédia avec moteur de recommandation

**Version 0.1 (brouillon de conception), 14 novembre 2026. Auteur : Saad, avec l'aide de Claude.**
Nom de travail du projet : **NewsLab Recsys**.

> **Statut : document de conception à discuter.** Rien n'est lancé : pas de code, pas de dépôt. Les valeurs chiffrées (pondérations, seuils, durées, volumes) sont des **propositions de départ**. Les choix encore ouverts sont regroupés en options au §18 pour qu'on les tranche ensemble avant le démarrage.

---

## 0. Résumé

On construit une plateforme d'actualités inspirée des grands quotidiens en ligne (type Wall Street Journal) : une page d'accueil « À la une », des rubriques, et quatre formats de contenu : **articles**, **vidéos**, **galeries d'images** et **documents texte (PDF)**.

Chaque lecteur reçoit d'abord une sélection par défaut (éditoriale, récente, puis populaire). Ensuite, **chacune de ses interactions est captée par notre propre front-end**, horodatée, rattachée à sa session et à son compte, puis transformée en score qui alimente les algorithmes. L'administrateur choisit quel algorithme est actif, le règle, l'essaie et compare les résultats.

Le projet suit l'approche de la plateforme e-learning de référence du professeur (dépôt `charfx/Sysrecomandation`) : même stack, même séparation utilisateur/administrateur, même principe de pages d'algorithmes avec explication, code et essai. Ce dépôt sert uniquement d'inspiration ; la plateforme d'actualités est un **nouveau projet**.

### Règle fondatrice sur les données

| Autorisé | Interdit |
|---|---|
| Jeux de données externes pour le **contenu** : textes, titres, résumés, catégories, entités, images, vidéos, documents | Importer des **journaux d'interactions** déjà prêts : clics MIND (`behaviors.tsv`), temps de lecture Adressa, sessions Globo, notes, etc. |
| Événements produits par **nos** écouteurs (`addEventListener`, `IntersectionObserver`, API du lecteur vidéo, PDF.js…) | Toute popularité, tendance ou similarité collaborative qui ne viendrait pas de nos propres événements |
| Sessions simulées **passant par notre vrai pipeline de collecte**, marquées `synthetic` | Mélanger silencieusement des données simulées avec les données réelles |

Conséquence : l'extraction et la quantification des interactions sont **le cœur pédagogique du projet**, pas un import.

---

## 1. Objectifs

### 1.1 Objectifs pédagogiques
1. Comprendre de bout en bout la chaîne d'un système de recommandation : collecte, nettoyage, quantification, modélisation, classement, évaluation.
2. Implémenter et comparer plusieurs familles d'algorithmes sur les **mêmes données**.
3. Mesurer l'apport des signaux riches (temps de lecture, défilement, progression vidéo) par rapport aux clics seuls.
4. Expérimenter le démarrage à froid (nouvel utilisateur, nouvel article) propre à l'actualité, où les contenus vieillissent vite.

### 1.2 Objectifs professionnels
1. Architecture propre, testée, conteneurisée, reproductible (`docker compose up`).
2. Contrat d'événements versionné, ingestion idempotente, traçabilité de chaque recommandation (quel modèle, quelle version, quel rang).
3. Respect des licences des contenus et du RGPD pour les interactions.
4. Interface d'administration utilisable par un non-développeur.

### 1.3 Hors périmètre (V1)
Paiements et abonnements, commentaires publics, application mobile native, transcodage vidéo adaptatif (HLS), apprentissage en ligne temps réel, publication de contenus par des tiers.

---

## 2. Acteurs et parcours

### 2.1 Rôles
| Rôle | Droits |
|---|---|
| **Visiteur anonyme** | Lire la page d'accueil et les contenus. Ses interactions sont rattachées à un identifiant anonyme et une session, et fusionnées à son compte s'il se connecte. |
| **Lecteur** (utilisateur connecté) | Tout ce que fait le visiteur, plus profil (rubriques préférées, langue), favoris, « j'aime / pas intéressé », suivi de sujets, historique personnel, recommandations « Pour vous ». |
| **Administrateur** | Gestion du catalogue, choix et réglage des algorithmes, essais, tableaux de bord, évaluations, générateur de sessions simulées, exports pseudonymisés. |

### 2.2 Parcours lecteur
1. Arrivée sur l'accueil : bandeau « À la une » (éditorial), « Les plus lus » (popularité), « Tendances » (vitesse), « Pour vous » (algorithme actif).
2. Ouverture d'un article : lecture, défilement, galerie d'images, vidéo intégrée, document joint.
3. En bas de page : « Dans la même veine » (contenu similaire) et « Les lecteurs ont aussi lu » (collaboratif).
4. Retour à l'accueil : « Pour vous » a été recalculé avec la nouvelle interaction.
5. Connexion : l'historique anonyme est rattaché au compte.

### 2.3 Parcours administrateur
1. Connexion, accès à **Administration**.
2. **Algorithmes** : choisir l'algorithme actif par emplacement, régler ses paramètres, voir son explication, sa formule et son code, l'essayer « en tant que » tel utilisateur.
3. **Interactions** : volume d'événements, couverture, temps de lecture, distribution des scores.
4. **Évaluation** : lancer une évaluation hors ligne, comparer les modèles, consulter l'historique des runs.
5. **Catalogue** : importer, modifier, archiver des contenus ; mettre un contenu « à la une ».
6. **Simulation** : générer des sessions synthétiques pour tester le pipeline.

---

## 3. Contenus : sources et licences

### 3.1 Types de contenu
| Type | Rendu | Métadonnées clés |
|---|---|---|
| `article` | Page article : titre, chapô, corps, image principale | titre, résumé, corps, rubrique, sous-rubrique, tags, entités, auteur, langue, date de publication, nombre de mots |
| `video` | Lecteur HTML5 instrumenté | titre, description, durée exacte, miniature, rubrique, tags, transcription éventuelle |
| `gallery` | Diaporama d'images avec légendes | titre, légendes, nombre d'images, rubrique |
| `document` | Visionneuse PDF (PDF.js) + téléchargement | titre, résumé, nombre de pages, texte extrait, rubrique |

Un article peut **contenir** des médias (image, vidéo, document). Les médias peuvent aussi exister comme contenus autonomes recommandables. La table `content_links` relie les deux.

### 3.2 Sources proposées
| Source | Ce qu'on prend | Ce qu'on ne prend pas | Licence et précautions |
|---|---|---|---|
| **MIND** (Microsoft News Dataset) : fichier `news.tsv` | Titres, résumés, catégories, sous-catégories, entités Wikidata (~160 000 actualités, en anglais) pour donner du volume au catalogue | `behaviors.tsv` (impressions et clics) : **jamais importé** | Microsoft Research License, usage de recherche non commercial. Le corps complet n'est pas fourni : on n'aspire pas les URL d'origine. |
| **Wikinews** (FR et EN) | Articles complets avec date, catégories, parfois images | Rien d'autre | CC BY 2.5 : attribution obligatoire, stockée par contenu. Idéal pour avoir des corps d'articles réels et du français. |
| **The Guardian Open Platform** (optionnel) | Titres, chapôs, rubriques, et corps selon la clé obtenue | Toute statistique d'audience | Clé développeur gratuite, usage non commercial, mentions obligatoires. |
| **Flux RSS de médias** (optionnel, pour la fraîcheur) | Titre, résumé, lien, date | Le texte intégral (droit d'auteur) | On affiche l'extrait et un lien vers la source. |
| **Pexels / Pixabay** | Images et vidéos courtes d'illustration par thème | Les compteurs de vues ou de likes de ces sites | Licences Pexels/Pixabay : usage gratuit, pas de redistribution en tant que banque d'images. Mention de l'auteur conseillée. |
| **Wikimedia Commons** | Images et vidéos d'actualité | | Licences variables (CC BY, CC BY-SA, domaine public) : stocker la licence exacte de chaque fichier. |
| **Documents publics** (rapports Banque mondiale, OCDE en accès libre, data.gouv / Etalab, NASA) | PDF de rapports et notes, texte extrait pour TF-IDF/embeddings | | CC BY 4.0, Licence Ouverte Etalab ou domaine public selon la source. |

### 3.3 Règles de constitution du corpus
- Chaque contenu porte : `source`, `source_url`, `license`, `attribution`, `imported_at`. L'interface affiche l'attribution.
- Corpus de démonstration cible (V1) : **≈ 2 000 articles** (dont ≥ 300 en français via Wikinews), **≈ 150 vidéos**, **≈ 150 galeries**, **≈ 100 documents**, répartis sur 8 à 10 rubriques communes (Économie, Marchés, Tech, Monde, Politique, Science, Santé, Sport, Culture, Opinion).
- Une table de correspondance unifie les catégories des différentes sources vers nos rubriques.
- Les dates de publication sont conservées. Pour simuler un flux vivant, un **mode « horloge de publication »** peut décaler les dates relatives, ou publier progressivement les contenus (par exemple 50 par jour) afin que les algorithmes de fraîcheur et de tendance aient du sens.
- Les durées vidéo sont mesurées exactement à l'import (ffprobe), car l'ingestion rejette les positions incohérentes.
- Un script d'import par source (`importers/mind.py`, `importers/wikinews.py`, `importers/pexels.py`…) produit un format commun, idempotent (clé = source + identifiant source).

### 3.4 Alimentation du catalogue en trois phases (décidé)
| Phase | Quand | Comment | `source` enregistrée |
|---|---|---|---|
| **1. Corpus statique** | Dès le départ, pour développer et tester | Fichiers préparés (MIND `news.tsv`, Wikinews, médias Pexels/Commons, PDF publics) importés par le worker. Le corpus est figé et versionné, ce qui rend les tests et les évaluations reproductibles. | `mind`, `wikinews`, `pexels`… |
| **2. Ajout manuel par l'admin** | Une fois le pipeline validé | Formulaire « Ajouter un contenu » : article (titre, chapô, corps, rubrique, tags), vidéo, galerie ou document, avec upload dans MinIO. Permet de tester le démarrage à froid d'un nouvel article en direct pendant une démo. | `manual` |
| **3. API d'actualités planifiée** | Après les tests et l'évaluation sur le corpus statique | Import automatique toutes les 30 min depuis une API (Guardian Open Platform, flux RSS, autre API à choisir), dédoublonnage par `source` + `source_id`, licence vérifiée. Le catalogue devient vivant et la fraîcheur prend tout son sens. | `guardian`, `rss:<flux>`… |

Chaque contenu garde, quelle que soit la phase :
- `source` et `source_id` (identifiant chez la source, ou UUID pour un ajout manuel) ;
- `source_url` (vide pour un ajout manuel) ;
- `published_at` : date de publication d'origine (choisie par l'admin pour un ajout manuel) ;
- `imported_at` : date à laquelle le contenu est entré dans **notre** base ;
- `ingestion_run_id` : le lot d'import qui l'a créé, ou `created_by` pour un ajout manuel ;
- `license` et `attribution`.

La distinction `published_at` / `imported_at` est importante : la fraîcheur utilise `published_at`, alors que l'évaluation hors ligne utilise `imported_at` pour savoir si un contenu était disponible avant la date de coupure.

Une table `ingestion_runs` (id, source, démarré le, terminé le, contenus créés / mis à jour / rejetés, erreurs, lancé par) trace chaque import.

---

## 4. Architecture

### 4.1 Stack (alignée sur la plateforme de référence)
| Couche | Choix |
|---|---|
| Front-end | React + TypeScript + Vite ; lecteur vidéo HTML5 ; PDF.js pour les documents ; module `tracker` maison |
| API | FastAPI, Pydantic, SQLAlchemy 2, Alembic |
| Base | PostgreSQL 17 + extension **pgvector** pour les embeddings |
| Fichiers | MinIO (compatible S3), URL signées temporaires |
| Calculs | Python, pandas, scikit-learn, sentence-transformers, `implicit` (ALS/BPR) ; tâches planifiées (APScheduler ou un conteneur `worker`) |
| Cache (optionnel) | Redis pour les listes précalculées et les compteurs de popularité |
| Conteneurs | Docker Compose : `frontend`, `api`, `worker`, `db`, `minio` |
| Qualité | pytest, Vitest, ruff, ESLint, GitHub Actions (lint, tests, build) |

Le découpage en conteneurs (web, api, worker, scheduler, db, redis, minio, migrate, simulator) avec rôle, image, ports, volumes, variables et ébauche de Compose est détaillé dans [architecture-conteneurs.md](architecture-conteneurs.md).

### 4.2 Flux
```
Navigateur ──(événements par lots)──▶ API /events/batch ──▶ PostgreSQL: interaction_events
     ▲                                                          │
     │                                                 worker (toutes les N min)
     │                                                          ▼
     │                                      interaction_scores, popularity_snapshots,
     │                                      user_profiles, modèles entraînés
     │                                                          │
     └──── GET /recommendations?slot=home_for_you ◀── service de recommandation
                                                   (lit la config admin active)
```

Deux temps :
- **Temps réel léger** : à chaque requête de recommandation, on lit les derniers événements de la session (algorithmes par session, exclusion du déjà-lu, mise à jour incrémentale du profil).
- **Temps différé** : un worker recalcule toutes les 5 à 15 minutes les scores agrégés, la popularité par fenêtre, les profils, et réentraîne les modèles lourds (collaboratif) une fois par heure ou à la demande de l'admin.

---

## 5. Identification : session, anonyme, compte

| Identifiant | Origine | Durée | Usage |
|---|---|---|---|
| `anonymous_id` | UUID généré au premier passage, cookie first-party | 13 mois max (RGPD) | Relier les visites d'un visiteur non connecté |
| `session_id` | UUID créé côté client, renouvelé après **30 min d'inactivité** ou à minuit | Une visite | Algorithmes par session, analyse de parcours |
| `user_id` | **Déduit côté serveur** depuis le cookie d'authentification | Permanent | Profil et recommandations personnelles |
| `view_id` | UUID par ouverture de contenu (un onglet = une vue) | Une consultation | Regrouper les événements d'une même lecture |

Règles :
- Le serveur **n'accepte jamais** un `user_id` envoyé par le navigateur ; il le lit dans la session authentifiée.
- À la connexion, une ligne `identity_links(anonymous_id, user_id, linked_at)` rattache l'historique anonyme au compte. Les calculs utilisent un `subject_id` = `user_id` si connu, sinon `anonymous_id`.
- Authentification par cookie HttpOnly, Secure en production, protection CSRF des requêtes en écriture, mots de passe hachés (argon2).

---

## 6. Collecte des interactions (tracking)

C'est la partie la plus importante du projet : **nous** décidons quoi observer, comment, et ce que cela signifie.

### 6.1 Principes
1. Un module unique `src/tracker/` expose `track(type, payload)`. Les composants n'envoient jamais de requêtes eux-mêmes.
2. Les événements sont mis en file locale, envoyés par lots toutes les 10 secondes ou à 20 événements, et à la fermeture de page via `navigator.sendBeacon` / `fetch(..., {keepalive: true})`.
3. Chaque événement a un `event_id` UUID : l'API déduplique, donc les réessais sont sans risque.
4. La collecte ne bloque jamais l'affichage ni la lecture.
5. Un événement client est une **observation**, pas une preuve. On documente ce que chaque signal ne prouve pas (une page ouverte ne prouve pas la lecture, un onglet visible ne prouve pas l'attention).

### 6.2 Enveloppe commune
```json
{
  "schema_version": 1,
  "event_id": "8f1c…",
  "anonymous_id": "a2e4…",
  "session_id": "5d31…",
  "view_id": "c07b…",
  "sequence": 14,
  "event_type": "scroll_depth",
  "content_id": "art-01523",
  "occurred_at": "2026-11-14T10:21:07.412Z",
  "page": "article",
  "context": { "slot": "home_for_you", "request_id": "rq-…", "rank": 3 },
  "payload": { "depth": 75 }
}
```
Le serveur ajoute `user_id`, `received_at`, `user_agent_family`, `is_synthetic` (vrai seulement pour les comptes de simulation).

### 6.3 Catalogue des événements et écouteurs
| Domaine | Événement | Écouteur / technique | Données |
|---|---|---|---|
| Navigation | `page_view` | Changement de route React | page, référent interne |
| | `session_start` / `session_end` | Création de session, `pagehide` | |
| | `search` | Soumission du formulaire | requête, nombre de résultats |
| | `filter_category` | Clic sur une rubrique | rubrique |
| Recommandations | `rec_impression` | **`IntersectionObserver`** : carte visible à ≥ 50 % pendant ≥ 1 s | request_id, slot, rang, content_id |
| | `rec_click` | `click` sur une carte | request_id, slot, rang |
| | `rec_hide` | Bouton « Pas intéressé » | motif facultatif |
| Article | `article_open` | Montage de la page | source (reco, recherche, accueil, lien direct) |
| | `scroll_depth` | `scroll` + calcul du % du corps visible, paliers 25/50/75/100 | palier |
| | `read_heartbeat` | Toutes les 5 s si l'onglet est visible (`visibilitychange`) **et** activité récente (`scroll`, `mousemove`, `keydown`, `touchstart` dans les 30 dernières secondes) | secondes actives depuis le dernier battement |
| | `article_complete` | Paliers 100 % atteints et temps actif ≥ 40 % du temps de lecture attendu | temps actif total |
| | `text_copy` | `copy` sur le corps | longueur (pas le texte) |
| | `link_out` | `click` sur un lien externe | domaine |
| Vidéo | `video_play`, `video_playing`, `video_pause` | Événements `play`, `playing`, `pause` du `<video>` | position |
| | `video_seek` | `seeking` / `seeked` | from, to |
| | `video_heartbeat` | Toutes les 10 s pendant la lecture | intervalle réellement joué |
| | `video_ratechange`, `video_volumechange`, `video_fullscreen` | Événements natifs, `fullscreenchange` | ancienne/nouvelle valeur |
| | `video_ended` | `ended` | |
| | `video_waiting` | `waiting` (mise en mémoire tampon, à exclure du temps de visionnage) | |
| Galerie | `gallery_open`, `gallery_image_view` | Ouverture du diaporama, changement d'image, visible ≥ 1 s | index, nombre total |
| | `gallery_zoom` | Clic sur agrandir | index |
| Document | `doc_open` | Ouverture de la visionneuse | nombre de pages |
| | `doc_page_view` | Événement `pagechanging` de PDF.js, page visible ≥ 2 s | numéro de page |
| | `doc_download` | Clic sur télécharger | |
| Explicite | `like`, `unlike`, `dislike` | Boutons | |
| | `bookmark_add`, `bookmark_remove` | Bouton favori | |
| | `share` | Bouton partager (copie de lien, Web Share API) | canal |
| | `follow_topic`, `unfollow_topic` | Bouton « Suivre ce sujet » | rubrique ou entité |

### 6.4 Validation côté API
- Types autorisés, schéma Pydantic par type, dates ISO, valeurs finies et non négatives.
- Positions vidéo ≤ durée + 2 s ; pages de document ≤ nombre de pages ; profondeur ∈ {25, 50, 75, 100}.
- Limites : 100 événements et 256 Ko par lot ; plafond de fréquence par session (anti-robot).
- Réponse : `{accepted, duplicates, rejected:[{event_id, reason}]}`.

### 6.5 Agrégats par vue (calculés par le worker)
Pour chaque `view_id`, on construit une ligne `content_views` :
- `active_seconds` : somme des battements de lecture (plafonnés).
- `expected_seconds` : nombre de mots / 230 mots par minute pour un article ; durée pour une vidéo ; pages × 30 s pour un document ; images × 4 s pour une galerie.
- `read_ratio = min(active_seconds / expected_seconds, 1.5)`.
- `max_scroll_depth`, `video_coverage` (union des intervalles joués / durée), `video_rewatch_seconds`, `doc_pages_ratio`, `gallery_images_ratio`.
- `bounce` : vrai si `active_seconds < 10` et `max_scroll_depth ≤ 25`.
- Indicateurs explicites de la vue : like, bookmark, share, hide.

---

## 7. Quantification : score d'interaction

### 7.1 Score d'une vue
Le score implicite combine l'**engagement** (combien) et les **actions explicites** (ce que l'utilisateur dit). Pondérations **versionnées** dans une table `scoring_configs`, modifiables par l'admin, et chaque calcul garde la version utilisée.

| Signal | Points (v1, proposition) |
|---|---|
| Ouverture (`article_open`, `video_play`, `doc_open`, `gallery_open`) | +1 |
| Engagement : `read_ratio` (article), `video_coverage` (vidéo), `doc_pages_ratio`, `gallery_images_ratio` | + 3 × ratio (plafonné à 3) |
| Complétion (article complet, vidéo ≥ 90 %, document ≥ 80 % des pages) | +1 |
| Défilement ≥ 75 % (article) | +0,5 |
| Revisionnage volontaire d'un passage vidéo | +0,5 (plafonné, pour ne pas surpondérer) |
| Téléchargement de document | +1 |
| Like | +2 |
| Favori | +2,5 |
| Partage | +3 |
| Suivi du sujet | appliqué au profil de rubrique, pas à l'item |
| Rebond (< 10 s, défilement ≤ 25 %) | −1 |
| Dislike | −3 |
| « Pas intéressé » | −4, et exclusion définitive de l'item |
| Impression vue sans clic | −0,1 par impression, plafonné à −0,5 (signal négatif faible) |

`score_vue = clamp(somme, −5, 10)`.

### 7.2 Score utilisateur × contenu
`score(u, i) = max sur les vues de score_vue` (ou somme plafonnée pour les relectures), puis **décroissance temporelle** pour les profils :

`poids(u, i, t) = score(u, i) × 0,5^(âge_jours / demi_vie)` avec une demi-vie de **7 jours** pour l'actualité (paramètre admin).

### 7.3 Profils dérivés
- **Profil de rubriques** : distribution des scores par rubrique + rubriques déclarées et suivies (bonus initial).
- **Profil de formats** : préférence article / vidéo / galerie / document.
- **Profil vectoriel** : moyenne pondérée des vecteurs TF-IDF ou embeddings des contenus consultés (Rocchio) : `p_u = Σ poids(u,i) · v_i − β · Σ |poids négatifs| · v_j`.
- **Profil d'entités** : entités (personnes, entreprises, pays) les plus présentes dans les contenus bien notés (grâce aux entités MIND et à une extraction spaCy pour les autres sources).

### 7.4 Expérience pédagogique clé
Comparer trois versions du score sur les mêmes algorithmes : **clics seuls**, **clics + temps de lecture/couverture**, **score complet avec explicite**. C'est la question de recherche du projet, dans la continuité de celle du professeur (« les signaux vidéo améliorent-ils les recommandations ? »).

---

## 8. Démarrage à froid

Comme on n'importe aucun log, la plateforme démarre **sans aucune interaction**. Stratégie en couches :

1. **Classement éditorial** : l'admin marque des contenus « À la une » avec une priorité. C'est ce que voit tout nouveau visiteur en premier, comme dans un vrai journal.
2. **Fraîcheur** : `score = exp(−âge_heures / τ)`, τ réglable (par défaut 24 h).
3. **Popularité lissée** dès les premières interactions (moyenne bayésienne, voir 9.1) pour éviter qu'un seul clic propulse un article en tête.
4. **Préférences déclarées** à l'inscription (choix de 3 rubriques minimum) : permet le contenu par profil dès la première visite.
5. **Exploration** : 10 à 20 % des emplacements réservés à des contenus nouveaux ou peu exposés (ε-greedy), pour que les nouveaux articles reçoivent des impressions.
6. **Sessions simulées** (pour le développement et la démonstration uniquement) :
   - Des « lecteurs virtuels » avec des personas (fan de tech, investisseur, sportif…) pilotent **le vrai front-end** avec Playwright : ils voient les recommandations, cliquent, défilent, regardent des vidéos selon des règles probabilistes liées à leur persona.
   - Leurs événements passent par le **même tracker et la même API**, ce qui teste aussi la chaîne complète.
   - Ils sont créés sur des comptes `is_synthetic = true` ; tous les tableaux de bord, calculs et évaluations ont un filtre « inclure / exclure les données simulées », exclu par défaut en évaluation finale.
   - Ce ne sont pas des logs importés : ce sont des interactions générées par notre propre pipeline, clairement étiquetées.

Chaque réponse de recommandation indique l'algorithme demandé, l'algorithme effectivement utilisé et le **motif du repli** (« profil vide », « moins de 5 interactions », « modèle non entraîné »).

---

## 9. Algorithmes que l'administrateur peut choisir

Interface commune (comme chez le professeur) :
```python
class Recommender(Protocol):
    key: str; family: str; version: str
    def fit(self, data: TrainingData, params: dict) -> None: ...
    def recommend(self, subject: Subject, k: int, context: Context) -> list[ScoredItem]: ...
    def explain(self, subject, item) -> str: ...   # « Parce que vous avez lu … »
```
Un **registre** liste les algorithmes par famille. Chaque fiche admin contient : explication, étapes, formule, paramètres, limites, cas de démarrage à froid, code source en lecture seule, essai en direct.

Règles communes appliquées après tout algorithme (désactivables pour l'étude) : exclure le déjà-lu et le « pas intéressé », exclure les contenus archivés, filtre de fraîcheur maximum (ex. 30 jours pour « Pour vous »), au plus N contenus de la même rubrique d'affilée.

### 9.1 Références et classements non personnalisés
| Clé | Principe | Formule / détails |
|---|---|---|
| `random` | Référence aléatoire, graine enregistrée | Sert de plancher en évaluation |
| `editorial` | Ordre fixé par l'admin | priorité puis date |
| `recent` | Plus récent d'abord | `exp(−âge/τ)` |
| `popular` | Popularité par fenêtre (24 h, 7 j, 30 j) | `pop(i) = Σ_vues score_vue · 0,5^(âge/h)` puis lissage bayésien : `(n·moy + m·C)/(n + m)` |
| `trending` | Ce qui accélère | `z = (vues_dernière_heure − moyenne_24h) / écart_type_24h`, ou ratio fenêtre courte / fenêtre longue |
| `popular_in_category` | Popularité dans les rubriques préférées de l'utilisateur | Semi-personnalisé, bon repli |

### 9.2 Basés sur le contenu
| Clé | Principe |
|---|---|
| `tfidf` | Vecteurs TF-IDF (titre ×2, chapô, corps, tags, rubrique), cosinus avec le profil vectoriel de l'utilisateur |
| `embeddings` | Embeddings multilingues (`paraphrase-multilingual-MiniLM-L12-v2` ou `multilingual-e5-small`), stockés dans pgvector, recherche des plus proches voisins |
| `entities` | Similarité sur les entités (Jaccard pondéré ou embeddings d'entités) : « vous suivez Tesla et Nvidia » |
| `profile_preferences` | Rubriques et formats préférés (déclarés + appris), avec fraîcheur |
| `similar_items` | Pour la page article : voisins du contenu courant (TF-IDF ou embeddings) |
| `multimodal` (extension) | Embeddings CLIP pour les images et miniatures vidéo, fusionnés aux embeddings texte |

### 9.3 Basés sur l'historique
| Clé | Principe |
|---|---|
| `history_weighted` | Profil Rocchio avec poids d'interaction et décroissance temporelle (§7.3), puis cosinus. C'est le « basé sur l'historique » demandé. |
| `last_read` | Voisins des 3 derniers contenus bien notés (simple, très lisible) |

### 9.4 Collaboratifs (nécessitent assez d'interactions)
| Clé | Principe |
|---|---|
| `item_knn` | Similarité cosinus entre colonnes de la matrice utilisateur × contenu (scores implicites) : « les lecteurs qui ont lu X ont aussi lu Y » |
| `user_knn` | k plus proches utilisateurs, agrégation de leurs scores |
| `als` | Factorisation matricielle implicite (Alternating Least Squares, bibliothèque `implicit`), confiance `c = 1 + α·score` |
| `bpr` (extension) | Bayesian Personalized Ranking, apprend un ordre plutôt qu'une note |

Limite à expliquer : un article publié il y a une heure n'a aucune interaction, le collaboratif ne peut pas le recommander. D'où l'intérêt des hybrides.

### 9.5 Par session (séquentiels)
| Clé | Principe |
|---|---|
| `session_cooccurrence` | Paires (A → B) consultées successivement dans une même session, pondérées par la proximité ; on recommande ce qui suit souvent les derniers contenus de la session courante |
| `session_knn` (SKNN) | Sessions passées les plus proches de la session courante |
| `gru4rec` (extension) | Réseau récurrent sur séquences de sessions, si le volume le permet |

Fonctionne aussi pour les visiteurs anonymes : c'est l'algorithme idéal pour démontrer l'usage du `session_id`.

### 9.6 Hybrides
| Clé | Principe |
|---|---|
| `hybrid_weighted` | `score = w1·contenu + w2·collaboratif + w3·popularité + w4·fraîcheur`, scores normalisés, poids réglables par l'admin |
| `hybrid_switching` | Choix selon le contexte : < 5 interactions → profil/popularité ; ≥ 5 → historique ; ≥ 30 et modèle entraîné → collaboratif |
| `hybrid_cascade` | Le collaboratif génère 200 candidats, le contenu les réordonne |

### 9.7 Ré-ordonnancement et diversité
| Clé | Principe |
|---|---|
| `mmr` | Maximal Marginal Relevance : `argmax λ·pertinence(i) − (1−λ)·max_j sim(i, j)` ; λ réglable. Applicable en surcouche à n'importe quel algorithme. |
| `format_mix` | Garantit un mélange de formats (ex. au moins 1 vidéo sur 6 cartes) |
| `freshness_boost` | Multiplie le score par un facteur de fraîcheur |

### 9.8 Exploration (extension)
`epsilon_greedy` et `thompson_sampling` sur les emplacements : bandits pour équilibrer exploitation et découverte, en utilisant les impressions et clics.

### 9.9 Emplacements configurables
| Emplacement (`slot`) | Défaut proposé |
|---|---|
| `home_top` « À la une » | `editorial` |
| `home_most_read` « Les plus lus » | `popular` (24 h) |
| `home_trending` « Tendances » | `trending` |
| `home_for_you` « Pour vous » | `hybrid_switching` + `mmr` |
| `article_similar` « Dans la même veine » | `similar_items` (embeddings) |
| `article_also_read` « Les lecteurs ont aussi lu » | `item_knn`, repli `similar_items` |
| `video_next` « À suivre » | `session_cooccurrence`, repli `similar_items` |

---

## 10. Fonctionnalités d'administration

1. **Configuration des algorithmes** : pour chaque emplacement, algorithme actif, paramètres (K, λ MMR, demi-vie, fenêtre de popularité, poids hybrides), surcouche de diversité. Chaque changement est journalisé (`algorithm_config_history` : qui, quand, avant, après).
2. **Fiches algorithmes** : explication, formule, étapes, limites, code en lecture seule (comme la plateforme de référence).
3. **Essai** : « recommander pour l'utilisateur X » ou « pour un profil simulé », avec le détail du score de chaque item et l'explication.
4. **Comparaison côte à côte** : deux algorithmes, même utilisateur, recouvrement des listes.
5. **Test A/B** (extension) : répartition stable des utilisateurs entre deux configurations, suivi du taux de clic et du temps de lecture.
6. **Pondérations du score** : édition de `scoring_configs`, nouvelle version à chaque modification, recalcul à la demande.
7. **Tableau de bord des interactions** : événements par type et par jour, sessions, temps de lecture moyen, couverture vidéo, entonnoir impression → clic → lecture complète, contenus les plus engageants, filtre réel / simulé.
8. **Explorateur d'événements** : consulter les événements bruts d'une session (pseudonymisés), très utile pour la soutenance.
9. **Évaluation** : lancer un run hors ligne, voir les métriques par algorithme, historique des runs.
10. **Catalogue** : import par source, édition, archivage, mise à la une, licence et attribution.
11. **Simulation** : lancer N lecteurs virtuels, choisir les personas, suivre la génération.
12. **Données** : export pseudonymisé, suppression des données d'un utilisateur, politique de rétention.

---

## 11. Modèle de données

| Table | Colonnes principales |
|---|---|
| `users` | id, email, password_hash, role (`reader`/`admin`), is_synthetic, created_at |
| `user_preferences` | user_id, categories déclarées, langue, formats préférés |
| `identity_links` | anonymous_id, user_id, linked_at |
| `sessions` | session_id, anonymous_id, user_id?, started_at, last_seen_at, device_family |
| `contents` | id, type, title, summary, body, category, subcategory, tags[], language, author, published_at, imported_at, word_count, duration_s, page_count, image_count, storage_key, thumbnail_key, source, source_id, source_url, ingestion_run_id, created_by, license, attribution, editorial_priority, status ; unicité (source, source_id) |
| `ingestion_runs` | id, source, started_at, finished_at, created, updated, rejected, errors (jsonb), triggered_by |
| `content_links` | parent_id, child_id, role (image principale, vidéo intégrée, document joint) |
| `content_entities` | content_id, entity_id, label, type, confidence |
| `content_embeddings` | content_id, model, vector (pgvector), computed_at |
| `interaction_events` | event_id (PK, dédup), schema_version, anonymous_id, session_id, user_id?, view_id, sequence, event_type, content_id?, occurred_at, received_at, context (jsonb), payload (jsonb), is_synthetic |
| `content_views` | view_id, subject_id, content_id, session_id, started_at, active_seconds, expected_seconds, read_ratio, max_scroll, video_coverage, pages_ratio, bounce, flags explicites, score, scoring_version |
| `interaction_scores` | subject_id, content_id, score, last_interaction_at, scoring_version |
| `user_profiles` | subject_id, category_weights (jsonb), format_weights, entity_weights, vector_tfidf?, vector_embed, updated_at |
| `feedback` | user_id, content_id, like/dislike, bookmark, hidden, updated_at |
| `popularity_snapshots` | content_id, window, score, n_views, computed_at |
| `scoring_configs` | version, weights (jsonb), half_life_days, created_by, created_at |
| `algorithm_configs` | slot, algorithm_key, params (jsonb), rerankers[], active, updated_by, updated_at |
| `algorithm_config_history` | slot, before, after, changed_by, changed_at |
| `model_versions` | algorithm_key, version, trained_at, data_cutoff, params, artefact_key, metrics |
| `recommendation_requests` | request_id, subject_id, session_id, slot, algorithm_requested, algorithm_used, fallback_reason, model_version, params, latency_ms, created_at |
| `recommendation_items` | request_id, rank, content_id, score, explanation |
| `experiments`, `experiment_assignments` | A/B : id, configs, subject_id, variant |
| `evaluation_runs` | id, algorithms, split, cutoff, metrics (jsonb), include_synthetic, created_at |

Index : `interaction_events(user_id, occurred_at)`, `(content_id, occurred_at)`, `(session_id, sequence)` ; `content_views(subject_id)` ; index HNSW pgvector sur `content_embeddings.vector`.

---

## 12. API

| Méthode et route | Usage |
|---|---|
| `POST /auth/register`, `POST /auth/login`, `POST /auth/logout` | Comptes ; la connexion lie l'`anonymous_id` |
| `GET /me`, `PATCH /me/preferences` | Profil |
| `GET /me/history`, `GET /me/profile-explained` | Historique et « pourquoi je vois ça » |
| `GET /contents`, `GET /contents/{id}` | Catalogue filtré (rubrique, type, langue), détail |
| `GET /contents/{id}/media-url` | URL signée MinIO |
| `GET /search?q=` | Recherche plein texte (PostgreSQL `tsvector`) |
| `POST /events/batch` | Ingestion des événements |
| `PUT /contents/{id}/feedback` | Like, favori, pas intéressé |
| `GET /recommendations?slot=…&k=…&context_content_id=…` | Liste avec `request_id`, algorithme utilisé, version, repli, explications |
| `GET/PUT /admin/algorithms/configs` | Configuration par emplacement |
| `GET /admin/algorithms`, `GET /admin/algorithms/{key}` | Fiches et code |
| `POST /admin/algorithms/{key}/preview` | Essai |
| `POST /admin/models/{key}/train` | Réentraînement à la demande |
| `GET/POST /admin/scoring-configs` | Pondérations |
| `GET /admin/analytics/...` | Tableaux de bord |
| `GET /admin/events?session_id=` | Explorateur d'événements |
| `POST /admin/evaluations`, `GET /admin/evaluations/{id}` | Évaluation hors ligne |
| `POST /admin/simulations` | Lancer des lecteurs virtuels |
| `POST /admin/imports/{source}`, CRUD `/admin/contents` | Catalogue |
| `GET /admin/exports` | Export pseudonymisé |

Le lecteur ne choisit pas l'algorithme : c'est le serveur qui lit `algorithm_configs`. Seule la route d'essai admin accepte un algorithme arbitraire.

---

## 13. Évaluation

### 13.1 Hors ligne (sur nos propres événements)
- **Découpage temporel** : tout ce qui précède la date de coupure sert à l'entraînement, la suite au test. Aucune caractéristique (popularité, profils) ne doit utiliser de données postérieures à la coupure.
- **Vérité terrain** définie à l'avance : une vue avec `score_vue ≥ 3` (lecture substantielle ou action explicite positive).
- **Métriques de précision** : Precision@K, Recall@K, NDCG@K, MRR, HitRate@K.
- **Métriques au-delà de la précision** : couverture du catalogue, diversité intra-liste (1 − similarité moyenne), nouveauté (−log popularité), fraîcheur moyenne des recommandations, répartition par format.
- Toujours comparer à `random` et `popular`.
- Rapporter les résultats **avec et sans données simulées**, et avec les trois versions du score (§7.4).

### 13.2 En ligne
- Taux de clic = `rec_click / rec_impression` par emplacement et algorithme (attribution par `request_id`).
- Temps de lecture actif après clic, taux de complétion, taux de « pas intéressé ».
- A/B avec affectation stable. Avec peu d'utilisateurs, résultats descriptifs, sans prétendre à une significativité statistique.

### 13.3 Performance
Latence p95 de `GET /recommendations` < 300 ms (hors premier chargement des modèles), ingestion d'un lot < 100 ms.

---

## 14. Exigences non fonctionnelles

- **Sécurité** : contrôle des rôles côté API, cookies HttpOnly, CSRF, mots de passe argon2, URL signées à courte durée, limites de taille et de fréquence, aucun secret dans le dépôt (`.env`).
- **RGPD** : bandeau d'information et consentement pour la mesure d'audience personnalisée ; sans consentement, on ne garde que des agrégats de session. Séparer identité et identifiant analytique. Rétention proposée : événements bruts 90 jours, agrégats ensuite. Droit d'accès (« mon historique ») et de suppression.
- **Reproductibilité** : graines aléatoires, versions des modèles et des pondérations, date de coupure enregistrées dans chaque run.
- **Accessibilité** : navigation clavier, contrastes, sous-titres quand disponibles.
- **Qualité** : tests unitaires des algorithmes (cas connus), tests de l'ingestion (doublons, rejets), tests du calcul de couverture vidéo et de temps de lecture, tests front du tracker, CI.

---

## 15. Plan de réalisation (proposition, démarre après validation de la conception)

Durée indicative : **8 semaines**, à ajuster à l'équipe. Chaque étape se termine par une démonstration.

| Étape | Contenu | Livrable vérifiable |
|---|---|---|
| **1. Fondations** (S1) | Dépôt, Docker Compose, FastAPI, PostgreSQL + pgvector, MinIO, React, auth lecteur/admin, CI | Connexion des deux rôles, routes protégées |
| **2. Catalogue** (S2) | Modèle `contents`, importeurs Wikinews + MIND (`news.tsv` seulement) + Pexels + documents, rubriques unifiées, licences | ≈ 2 000 contenus affichés, pages article/vidéo/galerie/document |
| **3. Tracking** (S3) | Module tracker, tous les écouteurs du §6.3, `POST /events/batch`, dédup, explorateur d'événements | Une lecture produit les bons événements, visibles dans l'admin |
| **4. Quantification** (S4) | Worker, `content_views`, scores, profils, popularité par fenêtre, `scoring_configs` | Tableau de bord des interactions, score explicable par vue |
| **5. Premiers algorithmes** (S5) | Registre, `editorial`, `recent`, `popular`, `trending`, `tfidf`, `embeddings`, `history_weighted`, `profile_preferences`, emplacements configurables, journalisation des recommandations | L'admin change l'algorithme de « Pour vous » et la page change |
| **6. Simulation et algorithmes avancés** (S6) | Lecteurs virtuels Playwright, `item_knn`, `als`, `session_cooccurrence`, hybrides, MMR | Collaboratif fonctionnel sur données simulées étiquetées |
| **7. Évaluation** (S7) | Runs hors ligne, métriques, comparaison des trois scores, CTR en ligne, A/B | Rapport comparatif généré depuis l'admin |
| **8. Finition** (S8) | RGPD, tests, documentation, fiches pédagogiques des algorithmes, préparation de la soutenance | Démo complète et rapport |

### Ordre de priorité si le temps manque
1. Indispensable : étapes 1 à 5 avec `popular`, `tfidf`, `history_weighted`, un hybride simple et le choix admin.
2. Important : collaboratif, session, MMR, évaluation hors ligne.
3. Extensions : A/B, bandits, multimodal CLIP, GRU4Rec, BPR.

---

## 16. Risques et parades

| Risque | Parade |
|---|---|
| Pas assez d'interactions réelles pour le collaboratif | Recruter quelques testeurs (camarades), sessions simulées étiquetées, hybride `switching` |
| Biais des sessions simulées (les personas reproduisent nos hypothèses) | Toujours les exclure de l'évaluation finale, ou les rapporter séparément |
| Licences mal respectées | Champs licence/attribution obligatoires à l'import, affichage systématique |
| Temps de lecture faussé par un onglet ouvert en arrière-plan | Battements seulement si l'onglet est visible et qu'il y a eu une activité récente, plafond par vue |
| Embeddings lents ou lourds | Calcul en batch par le worker, stockage pgvector, modèle « small » |
| Popularité qui se renforce elle-même (boucle de rétroaction) | Exploration, MMR, fraîcheur, lissage bayésien |
| Fuite de données dans l'évaluation | Découpage temporel strict, caractéristiques calculées avant la coupure |

---

## 17. Différences avec la plateforme de référence du professeur

| Aspect | Plateforme e-learning (référence) | Plateforme d'actualités (ce projet) |
|---|---|---|
| Contenus | Vidéos MP4 et PDF de cours | Articles, vidéos, galeries, documents, avec liens entre eux |
| Durée de vie | Longue (un cours reste pertinent) | Courte : fraîcheur et tendances indispensables |
| Signaux | Surtout vidéo (couverture, reprise) | Lecture d'article (défilement, temps actif), vidéo, galerie, document, partage |
| Visiteurs | Comptes uniquement | Anonymes + comptes, fusion à la connexion |
| Choix d'algorithme | Par paramètre de requête | Par l'admin, **par emplacement**, journalisé |
| Familles | Contenu surtout, collaboratif et hybrides vides | Toutes les familles, plus session et tendances |

On reprend de la référence : la stack, l'interface `recommend`, le registre par familles, les fiches admin avec code et essai, l'enveloppe d'événement versionnée et la déduplication par `event_id`.

---

## 18. Choix ouverts à trancher avant le démarrage

Pour chaque point, l'option marquée ★ est ma recommandation, à discuter.

| # | Question | Options |
|---|---|---|
| 1 | **Langue du corpus** | A ★ Bilingue : MIND (anglais) pour le volume + Wikinews FR pour le français. B Tout en français (Wikinews FR + RSS + documents publics), corpus plus petit. C Tout en anglais (MIND + Guardian), le plus simple. |
| 2 | **Sources d'articles** | ✅ Décidé : corpus statique d'abord, puis ajout manuel par l'admin, puis API d'actualités planifiée (§3.4). Reste à choisir l'API de la phase 3 : Guardian, flux RSS ou autre. |
| 3 | **Taille du corpus V1** | A ★ ≈ 2 000 contenus tous formats. B ≈ 500 contenus (plus rapide, collaboratif plus facile à observer). C ≥ 10 000 (réaliste mais plus lourd). |
| 4 | **Simulation de flux** | A ★ Publication progressive des contenus (« horloge de publication »). B Dates d'origine conservées. |
| 5 | **Démarrage à froid** | A ★ Éditorial + fraîcheur + préférences déclarées + exploration, puis popularité. B Uniquement fraîcheur puis popularité. |
| 6 | **Sessions simulées** | A ★ Lecteurs virtuels Playwright passant par le vrai tracker, étiquetés `synthetic`. B Aucune simulation, seulement des testeurs réels. C Les deux, testeurs réels prioritaires en évaluation. |
| 7 | **Visiteurs anonymes** | A ★ Oui, avec fusion à la connexion. B Comptes obligatoires (plus simple, comme la référence). |
| 8 | **Choix d'algorithme par l'admin** | A ★ Par emplacement (accueil, page article, vidéo suivante). B Un seul algorithme global pour « Pour vous ». |
| 9 | **Pondérations du score** | A ★ Table versionnée modifiable par l'admin. B Constantes dans le code, documentées. |
| 10 | **Calcul des recommandations** | A ★ Hybride : worker toutes les 5 à 15 min + ajustement temps réel sur la session. B Tout en temps réel à la requête. C Tout en batch. |
| 11 | **Stockage des embeddings** | A ★ PostgreSQL + pgvector. B Fichiers numpy chargés en mémoire (comme une V0). |
| 12 | **Périmètre algorithmique minimal** | A ★ popular, trending, tfidf, embeddings, history_weighted, item_knn, session_cooccurrence, hybride, MMR. B Version réduite : popular, tfidf, history_weighted, hybride. |
| 13 | **Durée et équipe** | À préciser pour ajuster le plan indicatif de 8 semaines. |
| 14 | **Testeurs réels** | Peut-on faire utiliser la plateforme par la promo une ou deux semaines ? Ce sont les données les plus intéressantes. |
| 15 | **Nom** de la plateforme | À choisir. |
