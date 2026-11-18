from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from Backend.app.DB import SessionLocal
from Backend.app.Models import News
from fastapi.middleware.cors import CORSMiddleware
from Backend.app.data_loader import load_news, load_user_events
from Backend.app.Recommenders.Tf_IDF import TfidfRecommender, build_user_profile
import uuid
from datetime import datetime, timezone
from pydantic import BaseModel
from Backend.app.Models import User, UserSession, Event
from typing import Literal
from Backend.app.Recommenders.Embedding import EmbeddingRecommender
from Backend.app.Recommenders.Popularity_cold_start import PopularityRecommender
from Backend.app.auth import get_current_user, require_admin,create_token, hash_password, verify_password
from sqlalchemy import func, distinct
from Backend.app.Models import User, UserSession, Event,AppSetting



app = FastAPI(title="News Recommender API")

POP = PopularityRecommender().fit()

REC = TfidfRecommender().fit(load_news().reset_index(drop=True))   

INDEX = REC.index.to_dict()


EMB = EmbeddingRecommender()   

app.add_middleware(CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500", "http://localhost:5500"],
    allow_methods=["*"], allow_headers=["*"])



def get_db():
    db = SessionLocal()
    try:
        yield db          
    finally:
        db.close()        

@app.get("/news")
def list_news(limit: int = 20, offset: int = 0, db: Session = Depends(get_db)):
    rows = (db.query(News).order_by(News.published_at.desc())
              .offset(offset).limit(limit).all())
    return [{"id": n.id, "category": n.category, "title": n.title,
             "abstract": n.abstract, "published_at": n.published_at} for n in rows]

@app.get("/recommendations")
def recommendations(k: int = 10, db: Session = Depends(get_db),
                    current: dict = Depends(get_current_user)):
    algo = get_active_algorithm(db)                 # choisi par l'admin, pas par le client
    events = load_user_events(current["user_id"])
    seen = events["news_id"].tolist()

    if algo == "embedding":
        profile = EMB.build_user_profile(events)
    else:
        profile = build_user_profile(events, REC.X, INDEX)

    if profile is None:                             # cold start
        recos = POP.recommend(k, exclude=seen)
        return {"algorithm": algo, "strategy": "popularity_ranker",
                "items": recos.to_dict(orient="records")}

    if algo == "embedding":
        recos = EMB.recommend_for_user(profile, seen, k)
    else:
        recos = REC.recommend_for_user(profile, seen, k)
        recos = recos.rename(columns={"News_id": "id", "Category": "category", "Title": "title"})
    return {"algorithm": algo, "strategy": algo, "items": recos.to_dict(orient="records")}


@app.get("/news/{news_id}")
def get_news(news_id: str, db: Session = Depends(get_db)):
    n = db.get(News, news_id)
    if not n:
        raise HTTPException(404, "Article introuvable")
    return {"id": n.id, "category": n.category, "subcategory": n.subcategory,
            "title": n.title, "abstract": n.abstract, "url": n.url,
            "published_at": n.published_at}


WEIGHTS = {"click": 1, "read": 2, "scroll75": 1, "like": 3,
           "save": 3, "share": 4, "not_interested": -4, "bounce": -1}

class LoginIn(BaseModel):
    email: str
    password: str
class RegisterIn(BaseModel):
    email: str
    password: str    

class EventIn(BaseModel):
    news_id: str
    event_type: str


def open_session(user, db):
    s = UserSession(id=str(uuid.uuid4()), user_id=user.id)
    db.add(s); db.commit()
    token = create_token(user.id, user.role, s.id)
    return {"token": token, "role": user.role, "email": user.email}


@app.post("/register")
def register(data: RegisterIn, db: Session = Depends(get_db)):
    email = data.email.strip().lower()
    if len(data.password) < 6:
        raise HTTPException(400, "Mot de passe trop court (6 caractères minimum)")
    user = db.query(User).filter_by(email=email).first()
    if user and user.password_hash != "-":
        raise HTTPException(409, "Ce compte existe déjà")
    if user:                                   # ancien compte de test : on lui donne un mot de passe
        user.password_hash = hash_password(data.password)
    else:
        user = User(email=email, password_hash=hash_password(data.password), role="user")
        db.add(user)
    db.commit()
    return open_session(user, db)


@app.post("/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=data.email.strip().lower()).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Email ou mot de passe incorrect")
    return open_session(user, db)


@app.get("/me")
def me(current: dict = Depends(get_current_user)):
    return current

UNIQUE_EVENTS = {"like", "share", "save", "not_interested"}   # au niveau du module, près de WEIGHTS

@app.post("/events")
def add_event(e: EventIn, db: Session = Depends(get_db),
              current: dict = Depends(get_current_user)):
    user_id, session_id = current["user_id"], current["session_id"]
    if e.event_type not in WEIGHTS:
        raise HTTPException(400, "Type d'événement inconnu")

    if e.event_type in UNIQUE_EVENTS:
        exists = (db.query(Event)
                    .filter_by(user_id=user_id, news_id=e.news_id, event_type=e.event_type)
                    .first())
        if exists:
            return {"ok": True, "duplicate": True}

    db.add(Event(user_id=user_id, session_id=session_id, news_id=e.news_id,
                 event_type=e.event_type, weight=WEIGHTS[e.event_type],
                 ts=datetime.now(timezone.utc)))
    db.commit()
    return {"ok": True}

@app.get("/admin/interactions")
def admin_interactions(max_users: int = 15, max_items: int = 20,
                       db: Session = Depends(get_db),
                       admin: dict = Depends(require_admin)):
    score = func.sum(Event.weight)

    # 1. Chiffres clés
    n_users = db.query(func.count(distinct(Event.user_id))).scalar() or 0
    n_items = db.query(func.count(distinct(Event.news_id))).scalar() or 0
    n_events = db.query(func.count(Event.id)).scalar() or 0
    n_pairs = db.query(Event.user_id, Event.news_id).distinct().count()
    density = n_pairs / (n_users * n_items) if n_users and n_items else 0

    # 2. Répartition par type et par jour
    by_type = (db.query(Event.event_type, func.count(Event.id))
                 .group_by(Event.event_type)
                 .order_by(func.count(Event.id).desc()).all())
    day = func.date(Event.ts)
    by_day = db.query(day, func.count(Event.id)).group_by(day).order_by(day).all()

    # 3. Top articles et catégories (somme des poids)
    top_items = (db.query(News.id, News.title, News.category, score)
                   .join(Event, Event.news_id == News.id)
                   .group_by(News.id).order_by(score.desc()).limit(10).all())
    top_cats = (db.query(News.category, score)
                  .join(Event, Event.news_id == News.id)
                  .group_by(News.category).order_by(score.desc()).all())

    # 4. Matrice : users les plus actifs × articles touchés par le plus d'users
    u_rows = (db.query(User.id, User.email)
                .join(Event, Event.user_id == User.id)
                .group_by(User.id).order_by(func.count(Event.id).desc())
                .limit(max_users).all())
    i_rows = (db.query(News.id, News.title)
                .join(Event, Event.news_id == News.id)
                .group_by(News.id)
                .order_by(func.count(distinct(Event.user_id)).desc(), func.count(Event.id).desc())
                .limit(max_items).all())
    uids = [u.id for u in u_rows]
    iids = [i.id for i in i_rows]
    cells = (db.query(Event.user_id, Event.news_id, score)
               .filter(Event.user_id.in_(uids), Event.news_id.in_(iids))
               .group_by(Event.user_id, Event.news_id).all())
    lookup = {(u, i): float(s) for u, i, s in cells}

    return {
        "kpis": {"users": n_users, "items": n_items, "events": n_events, "density": density},
        "by_type": [{"event_type": t, "count": c} for t, c in by_type],
        "by_day": [{"day": str(d), "count": c} for d, c in by_day],
        "top_items": [{"id": i, "title": t, "category": cat, "score": float(s)}
                      for i, t, cat, s in top_items],
        "top_categories": [{"category": cat, "score": float(s)} for cat, s in top_cats],
        "matrix": {
            "users": [{"id": u.id, "email": u.email} for u in u_rows],
            "items": [{"id": i.id, "title": i.title} for i in i_rows],
            "values": [[lookup.get((u, i), 0.0) for i in iids] for u in uids],
        },
    }

ALGORITHMS = {"tfidf", "embedding"}          # algos réellement implémentés
DEFAULT_ALGO = "tfidf"

def get_active_algorithm(db: Session) -> str:
    row = db.get(AppSetting, "active_algorithm")
    return row.value if row and row.value in ALGORITHMS else DEFAULT_ALGO


class SettingsIn(BaseModel):
    algorithm: str
    params: dict = {}

@app.put("/admin/settings")
def update_settings(s: SettingsIn, db: Session = Depends(get_db),
                    admin: dict = Depends(require_admin)):
    if s.algorithm not in ALGORITHMS:
        raise HTTPException(400, f"Algorithme non implémenté : {s.algorithm}")
    row = db.get(AppSetting, "active_algorithm")
    if row:
        row.value = s.algorithm
    else:
        db.add(AppSetting(key="active_algorithm", value=s.algorithm))
    db.commit()
    return {"ok": True, "algorithm": s.algorithm}