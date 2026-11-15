import joblib, pandas as pd
from sqlalchemy import text
from Backend.app.DB import engine

PRIOR_CTR, PRIOR_N = 0.04, 20
MODEL_PATH = "Backend/app/ML_ranker_saved/ranker.joblib"

# Les MÊMES features qu'à l'entraînement, calculées à T = fin du dataset
FEATURES_SQL = """
WITH ref AS (SELECT date_trunc('hour', MAX(ts)) + interval '1 hour' AS t FROM hist_impressions),
art AS (
  SELECT h.news_id, ref.t,
         SUM(h.clicked) FILTER (WHERE h.ts >= ref.t - interval '1 hour')   AS clicks_1h,
         SUM(h.clicked) FILTER (WHERE h.ts >= ref.t - interval '24 hours') AS clicks_24h,
         COUNT(*)       FILTER (WHERE h.ts >= ref.t - interval '24 hours') AS imps_24h,
         MIN(date_trunc('hour', h.ts))                                     AS first_seen
  FROM hist_impressions h, ref
  GROUP BY h.news_id, ref.t
  HAVING COUNT(*) FILTER (WHERE h.ts >= ref.t - interval '24 hours') > 0
)
SELECT a.*, n.category, n.title
FROM art a JOIN news n ON n.id = a.news_id
"""

class PopularityRecommender:
    name = "popularity_ranker"

    def fit(self, top_n=100):
        """Au démarrage : features → ranker → liste classée, gardée en mémoire."""
        bundle = joblib.load(MODEL_PATH)
        model, feats = bundle["model"], bundle["features"]
        df = pd.read_sql(FEATURES_SQL, engine)
        df[["clicks_1h", "clicks_24h"]] = df[["clicks_1h", "clicks_24h"]].fillna(0)
        df["ctr_smooth_24h"] = (df["clicks_24h"] + PRIOR_CTR * PRIOR_N) / (df["imps_24h"] + PRIOR_N)
        df["age_hours"] = (df["t"] - df["first_seen"]).dt.total_seconds() / 3600
        cat = df.groupby("category")[["clicks_24h", "imps_24h"]].sum()
        cat_ctr = (cat["clicks_24h"] + PRIOR_CTR * PRIOR_N) / (cat["imps_24h"] + PRIOR_N)
        df["cat_ctr_24h"] = df["category"].map(cat_ctr)
        df["score"] = model.predict(df[feats])
        self.ranked = (df.sort_values("score", ascending=False).head(top_n)
                         .rename(columns={"news_id": "id"})[["id", "category", "title", "score"]]
                         .round({"score": 3}))
        return self

    def recommend(self, k=10, exclude=()):
        return self.ranked[~self.ranked["id"].isin(set(exclude))].head(k)