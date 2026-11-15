import numpy as np, pandas as pd, joblib, lightgbm as lgb
from pathlib import Path
from sklearn.metrics import roc_auc_score

FEATS = ["clicks_1h", "clicks_24h", "imps_24h", "ctr_smooth_24h", "age_hours", "cat_ctr_24h"]

df = pd.read_parquet("data/features.parquet").sort_values("impression_id", kind="stable")
tr, va, te = (df[df["split"] == s] for s in ("train", "val", "test"))
groups = lambda d: d.groupby("impression_id", sort=False).size().to_numpy()   # taille de chaque liste

# 1. Entraînement sur train, arrêt automatique quand la validation ne progresse plus
model = lgb.LGBMRanker(objective="lambdarank", n_estimators=500, learning_rate=0.05,
                       num_leaves=31, min_child_samples=100)
model.fit(tr[FEATS], tr["clicked"], group=groups(tr),
          eval_set=[(va[FEATS], va["clicked"])], eval_group=[groups(va)], eval_at=[10],
          callbacks=[lgb.early_stopping(30), lgb.log_evaluation(50)])

# 2. Métriques de classement, calculées liste par liste
def metrics(d, score):
    d = d.assign(s=np.asarray(score))
    auc = roc_auc_score(d["clicked"], d["s"])
    d = d[d.groupby("impression_id")["clicked"].transform("max") == 1]        # listes avec ≥ 1 clic
    d = d.sort_values(["impression_id", "s"], ascending=[True, False])
    d["rank"] = d.groupby("impression_id").cumcount() + 1
    mrr = (1 / d[d["clicked"] == 1].groupby("impression_id")["rank"].min()).mean()
    gain = d["clicked"] / np.log2(d["rank"] + 1)
    dcg = gain.where(d["rank"] <= 10, 0).groupby(d["impression_id"]).sum()
    n = d.groupby("impression_id")["clicked"].sum().clip(upper=10)
    idcg = n.map(lambda k: (1 / np.log2(np.arange(2, k + 2))).sum())
    return {"AUC": auc, "MRR": mrr, "NDCG@10": (dcg / idcg).mean()}

# 3. Examen final sur TEST : le modèle contre des méthodes simples
rng = np.random.default_rng(0)
res = pd.DataFrame({
    "Hasard":              metrics(te, rng.random(len(te))),
    "Plus cliqués 24h":    metrics(te, te["clicks_24h"]),
    "CTR lissé 24h":       metrics(te, te["ctr_smooth_24h"]),
    "Ranker LightGBM":     metrics(te, model.predict(te[FEATS])),
}).T.round(4)
print(res.to_string())
print(pd.Series(model.feature_importances_, index=FEATS).sort_values(ascending=False))

# 4. Sauvegarde : le modèle ET la liste des features (même ordre en production)
Path("Backend/app/ML_ranker_saved").mkdir(parents=True, exist_ok=True)
joblib.dump({"model": model, "features": FEATS}, "Backend/app/ML_ranker_saved/ranker.joblib")
print("Sauvé : Backend/app/ML_ranker_saved/ranker.joblib")