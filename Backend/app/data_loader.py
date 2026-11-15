from pathlib import Path
import pandas as pd
from Backend.app.DB import engine

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "news_clean.csv"

def load_news() -> pd.DataFrame:
    """Articles depuis PostgreSQL, avec les noms de colonnes attendus par TF-IDF."""
    sql = """
        SELECT id AS "News_id", category AS "Category",
               title AS "Title", COALESCE(abstract, '') AS "Abstract"
        FROM news
        ORDER BY id
    """
    news = pd.read_sql(sql, engine)
    news["text"] = news["Title"] + " " + news["Abstract"]
    return news

def load_user_events(user_id: int) -> pd.DataFrame:
    """Somme des poids par article pour un utilisateur."""
    sql = """
        SELECT news_id, SUM(weight) AS score, MAX(ts) AS last_ts
        FROM events
        WHERE user_id = %(uid)s
        GROUP BY news_id
    """
    return pd.read_sql(sql, engine, params={"uid": user_id})