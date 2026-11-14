import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel
from .Base import BaseRecommender
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix

class TfidfRecommender(BaseRecommender):
    name = "tfidf"

    def __init__(self, max_features=50000, min_df=2):
        self.vectorizer = TfidfVectorizer(stop_words="english", lowercase=True,
                                          max_features=max_features, min_df=min_df)

    def fit(self, news: pd.DataFrame):
        self.news = news
        self.X = self.vectorizer.fit_transform(news["text"])   # matrice articles × mots
        self.index = pd.Series(news.index, index=news["News_id"])  # id → n° de ligne
        return self

    def recommend(self, news_id, k=10):
        i = self.index[news_id]
        scores = linear_kernel(self.X[i], self.X).ravel()  # cosinus (vecteurs déjà normalisés)
        scores[i] = -1                                     # exclure l'article lui-même
        top = scores.argsort()[::-1][:k]
        out = self.news.iloc[top][["News_id", "Category", "Title"]].copy()
        out["score"] = scores[top].round(3)
        return out
    def recommend_for_user(self, profile, seen_ids, k=10):
        scores = self.X @ profile                    # cosinus avec chaque article
        for n in seen_ids:                           # exclure ce qu'il a déjà vu
            if n in self.index:
                scores[self.index[n]] = -1
        top = scores.argsort()[::-1][:k]
        out = self.news.iloc[top][["News_id", "Category", "Title"]].copy()
        out["score"] = scores[top].round(3)
        return out

HALF_LIFE_DAYS = 7

def build_user_profile(events: pd.DataFrame, X: csr_matrix, id_to_idx: dict):
    """events = sortie de load_user_events ; X = matrice TF-IDF ; id_to_idx = {news_id: ligne}"""
    events = events[events["news_id"].isin(id_to_idx)]   # articles connus seulement
    events = events[events["score"] > 0]                  # on ignore les signaux négatifs ici
    if events.empty:
        return None                                       # nouvel utilisateur → cold start

    now = pd.Timestamp.now(tz="UTC")
    age_days = (now - pd.to_datetime(events["last_ts"], utc=True)).dt.total_seconds() / 86400
    decay = 0.5 ** (age_days / HALF_LIFE_DAYS)
    w = (events["score"] * decay).to_numpy()

    rows = [id_to_idx[n] for n in events["news_id"]]
    profile = X[rows].T @ w / w.sum()                     # moyenne pondérée
    return np.asarray(profile).ravel()