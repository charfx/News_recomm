import numpy as np
import pandas as pd
from sqlalchemy import text
from Backend.app.DB import engine

HALF_LIFE_DAYS = 7

class EmbeddingRecommender:
    name = "embedding"

    def build_user_profile(self, events: pd.DataFrame):
        """events = sortie de load_user_events → vecteur 384 (ou None si cold start)"""
        events = events[events["score"] > 0]
        if events.empty:
            return None
        # 1. Les vecteurs des articles touchés par l'utilisateur
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT id, embedding::real[] FROM news "
                "WHERE id = ANY(:ids) AND embedding IS NOT NULL"),
                {"ids": events["news_id"].tolist()}).all()
        vecs = {r[0]: np.array(r[1]) for r in rows}
        events = events[events["news_id"].isin(vecs)]
        if events.empty:
            return None
        # 2. Poids = score × fraîcheur
        age = (pd.Timestamp.now(tz="UTC") - pd.to_datetime(events["last_ts"], utc=True)).dt.total_seconds() / 86400
        w = events["score"].to_numpy() * 0.5 ** (age.to_numpy() / HALF_LIFE_DAYS)
        # 3. Moyenne pondérée, puis normalisation (longueur 1)
        profile = sum(wi * vecs[n] for wi, n in zip(w, events["news_id"])) / w.sum()
        return profile / np.linalg.norm(profile)

    def recommend_for_user(self, profile, seen_ids, k=10):
        """PostgreSQL cherche les k plus proches du profil, sauf les articles déjà vus."""
        sql = text("""
            SELECT id, category, title,
                   round((1 - (embedding <=> CAST(:p AS vector)))::numeric, 3) AS score
            FROM news
            WHERE embedding IS NOT NULL AND NOT (id = ANY(:seen))
            ORDER BY embedding <=> CAST(:p AS vector)
            LIMIT :k
        """)
        with engine.connect() as conn:
            rows = conn.execute(sql, {"p": str(profile.tolist()),
                                      "seen": list(seen_ids), "k": k}).mappings().all()
        return pd.DataFrame(rows)