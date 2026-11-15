import torch
from sqlalchemy import text
from sentence_transformers import SentenceTransformer
from Backend.app.DB import engine

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
CHUNK = 2000   # articles écrits en base à la fois

device = "cuda" if torch.cuda.is_available() else "cpu"
model = SentenceTransformer(MODEL, device=device)
print("Appareil :", device)

# 1. Lire seulement les articles SANS vecteur → on peut relancer le script sans tout refaire
with engine.connect() as conn:
    rows = conn.execute(text(
        "SELECT id, title || ' ' || COALESCE(abstract, '') FROM news "
        "WHERE embedding IS NULL ORDER BY id")).all()
print(len(rows), "articles à encoder")

# 2. Encoder par paquets, puis écrire en base
update = text("UPDATE news SET embedding = CAST(:emb AS vector) WHERE id = :id")
for start in range(0, len(rows), CHUNK):
    part = rows[start:start + CHUNK]
    vecs = model.encode([r[1] for r in part], batch_size=128,
                        normalize_embeddings=True, show_progress_bar=False)
    with engine.begin() as conn:
        conn.execute(update, [{"id": r[0], "emb": str(v.tolist())} for r, v in zip(part, vecs)])
    print(f"{start + len(part)}/{len(rows)}")