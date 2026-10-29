import os

import psycopg
from dotenv import load_dotenv
from pgvector.psycopg import register_vector

load_dotenv()


def connect() -> psycopg.Connection:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set; copy .env.example to .env and fill it in")
    conn = psycopg.connect(url, autocommit=True)
    register_vector(conn)
    return conn


if __name__ == "__main__":
    # Smoke test: `python -m app.db` from backend/
    with connect() as conn:
        row = conn.execute(
            "select extversion from pg_extension where extname = 'vector'"
        ).fetchone()
        print("pgvector version:", row[0] if row else "NOT INSTALLED")
        count_row = conn.execute("select count(*) from artworks").fetchone()
        assert count_row is not None  # count(*) always returns one row
        print("artworks rows:", count_row[0])
