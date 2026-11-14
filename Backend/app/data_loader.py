from pathlib import Path
import pandas as pd
from Backend.app.DB import engine

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "news_clean.csv"

def load_news(path: Path = DATA_PATH) -> pd.DataFrame:
    df = pd.read_csv(path, sep=";", encoding="utf-8-sig")  # utf-8-sig retire le BOM
    df.columns = df.columns.str.strip()
    df = df.drop_duplicates(subset="News_id")              # un article = une ligne
    for col in ["Title", "Abstract", "Category", "Subcategory"]:
        df[col] = df[col].fillna("").astype(str).str.strip()
    df["text"] = (df["Title"] + " " + df["Abstract"] + " "
                  + df["Category"] + " " + df["Subcategory"])
    df = df[df["text"].str.strip() != ""].reset_index(drop=True)
    return df

def load_user_events(user_id: int) -> pd.DataFrame:
    """Somme des poids par article pour un utilisateur."""
    sql = """
        SELECT news_id, SUM(weight) AS score, MAX(ts) AS last_ts
        FROM events
        WHERE user_id = %(uid)s
        GROUP BY news_id
    """
    return pd.read_sql(sql, engine, params={"uid": user_id})