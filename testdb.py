from sqlalchemy import text
from Backend.app.DB import engine
with engine.connect() as conn:
    print(conn.execute(text("SELECT current_database(), current_user")).all())