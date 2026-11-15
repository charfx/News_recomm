import pandas as pd
from Backend.app.DB import engine

PRIOR_CTR, PRIOR_N = 0.04, 20        # lissage : on « prête » 20 affichages à 4 % à chaque article

# 1. Lire l'historique + la catégorie de chaque article
print("Lecture…")
df = pd.read_sql("""
    SELECT h.impression_id, h.ts, h.news_id, COALESCE(n.category, 'unknown') AS category, h.clicked
    FROM hist_impressions h LEFT JOIN news n ON n.id = h.news_id
""", engine)
df["hour"] = df["ts"].dt.floor("h")                       # 14:37 → 14:00

def per_hour(keys):
    """Clics et affichages par (clé, heure)."""
    return (df.groupby(keys + ["hour"])
              .agg(clicks=("clicked", "sum"), imps=("clicked", "size"))
              .reset_index().sort_values(keys + ["hour"]))

def window(g, keys, w):
    """Somme sur la fenêtre w AVANT l'heure courante (closed='left' = heure courante exclue)."""
    r = (g.set_index("hour").groupby(keys)[["clicks", "imps"]]
           .rolling(w, closed="left").sum().fillna(0).reset_index())
    return r.rename(columns={"clicks": f"clicks_{w}", "imps": f"imps_{w}"})

# 2. Features par article
print("Features article…")
gn = per_hour(["news_id"])
gn["first_seen"] = gn.groupby("news_id")["hour"].transform("min")
fn = (gn[["news_id", "hour", "first_seen"]]
        .merge(window(gn, ["news_id"], "1h"), on=["news_id", "hour"])
        .merge(window(gn, ["news_id"], "24h"), on=["news_id", "hour"]))

# 3. Features par catégorie
print("Features catégorie…")
gc = per_hour(["category"])
fc = window(gc, ["category"], "24h")
fc["cat_ctr_24h"] = (fc["clicks_24h"] + PRIOR_CTR * PRIOR_N) / (fc["imps_24h"] + PRIOR_N)

# 4. Tout rattacher à chaque ligne affichée
df = df.merge(fn, on=["news_id", "hour"]).merge(fc[["category", "hour", "cat_ctr_24h"]], on=["category", "hour"])
df["ctr_smooth_24h"] = (df["clicks_24h"] + PRIOR_CTR * PRIOR_N) / (df["imps_24h"] + PRIOR_N)
df["age_hours"] = (df["hour"] - df["first_seen"]).dt.total_seconds() / 3600

# 5. Découpage par TEMPS
day = df["ts"].dt.day
df["split"] = "train"
df.loc[day == 13, "split"] = "val"
df.loc[day == 14, "split"] = "test"

cols = ["impression_id", "news_id", "split", "clicks_1h", "clicks_24h", "imps_24h",
        "ctr_smooth_24h", "age_hours", "cat_ctr_24h", "clicked"]
df[cols].to_parquet("data/features.parquet", index=False)
print(df.groupby("split")["clicked"].agg(["size", "mean"]))
print(df[cols[3:]].describe().round(3).to_string())