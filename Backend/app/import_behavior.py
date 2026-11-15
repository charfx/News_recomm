from datetime import datetime, timezone
from Backend.app.DB import engine

PATH = "data/behaviors.tsv"
FMT = "%m/%d/%Y %I:%M:%S %p"          # 11/11/2019 9:05:58 AM

def rows():
    """Lit le fichier ligne par ligne et 'éclate' chaque impression."""
    with open(PATH, encoding="utf-8") as f:
        for line in f:
            imp_id, user, time, _history, impressions = line.rstrip("\n").split("\t")
            ts = datetime.strptime(time, FMT).replace(tzinfo=timezone.utc)
            for pos, item in enumerate(impressions.split(), start=1):
                news_id, clicked = item.rsplit("-", 1)      # "N55689-1" → N55689, 1
                yield (int(imp_id), user, ts, news_id, pos, int(clicked))

raw = engine.raw_connection()          # connexion psycopg « brute » pour COPY
try:
    with raw.cursor() as cur:
        cur.execute("TRUNCATE hist_impressions")      # import rejouable : on repart de zéro
        with cur.copy("COPY hist_impressions (impression_id, user_id, ts, news_id, position, clicked) FROM STDIN") as cp:
            for n, r in enumerate(rows(), start=1):
                cp.write_row(r)
                if n % 1_000_000 == 0:
                    print(f"{n:,} lignes…")
    raw.commit()
    print("Import terminé")
finally:
    raw.close()