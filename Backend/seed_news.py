import numpy as np, pandas as pd
from datetime import datetime, timedelta, timezone
from Backend.app.DB import SessionLocal
from Backend.app.Models import News

df = pd.read_csv("data/news_clean.csv", sep=";", encoding="utf-8-sig")
df.columns = df.columns.str.strip()
print(df.columns.tolist())          # contrôle
df = df.drop_duplicates("News_id").fillna("")

rng = np.random.default_rng(42)                        # graine fixe = mêmes dates à chaque import
now = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
ages = rng.uniform(0, 180 * 24 * 3600, len(df))        # âge en secondes, sur 180 jours

rows = [
    News(id=r.News_id, category=r.Category, subcategory=r.Subcategory,
         title=r.Title, abstract=r.Abstract, url=r.URL,
         published_at=now - timedelta(seconds=float(a)))
    for r, a in zip(df.itertuples(index=False), ages)
]

with SessionLocal() as db:
    db.query(News).delete()          # rend le script rejouable sans doublons
    db.add_all(rows)
    db.commit()
    print("articles importés :", db.query(News).count())