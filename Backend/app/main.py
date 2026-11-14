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



app = FastAPI(title="News Recommender API")
REC = TfidfRecommender().fit(load_news().reset_index(drop=True))   # au démarrage
INDEX = REC.index.to_dict()
app.add_middleware(CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500", "http://localhost:5500"],
    allow_methods=["*"], allow_headers=["*"])
def get_db():
    db = SessionLocal()
    try:
        yield db          # donne la session à la route
    finally:
        db.close()        # la ferme toujours, même en cas d'erreur

@app.get("/news")
def list_news(limit: int = 20, offset: int = 0, db: Session = Depends(get_db)):
    rows = (db.query(News).order_by(News.published_at.desc())
              .offset(offset).limit(limit).all())
    return [{"id": n.id, "category": n.category, "title": n.title,
             "abstract": n.abstract, "published_at": n.published_at} for n in rows]


@app.get("/recommendations")
def recommendations(user_id: int, k: int = 10):
    events = load_user_events(user_id)
    profile = build_user_profile(events, REC.X, INDEX)
    if profile is None:                                   # cold start
        return {"strategy": "cold_start", "items": []}
    recos = REC.recommend_for_user(profile, events["news_id"].tolist(), k)
    recos = recos.rename(columns={"News_id": "id", "Category": "category", "Title": "title"})
    return {"strategy": "tfidf", "items": recos.to_dict(orient="records")}

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

class EventIn(BaseModel):
    user_id: int
    session_id: str
    news_id: str
    event_type: str

@app.post("/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=data.email).first()
    if not user:                                   # premier passage → on crée le compte
        user = User(email=data.email, password_hash="-", role="user")
        db.add(user); db.commit()
    s = UserSession(id=str(uuid.uuid4()), user_id=user.id)   # nouvelle session à chaque login
    db.add(s); db.commit()
    return {"user_id": user.id, "session_id": s.id}

@app.post("/events")
def add_event(e: EventIn, db: Session = Depends(get_db)):
    if e.event_type not in WEIGHTS:
        raise HTTPException(400, "Type d'événement inconnu")
    db.add(Event(user_id=e.user_id, session_id=e.session_id, news_id=e.news_id,
                 event_type=e.event_type, weight=WEIGHTS[e.event_type],
                 ts=datetime.now(timezone.utc)))
    db.commit()
    return {"ok": True}