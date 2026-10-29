"""Compute palette + histogram for every ingested artwork and store them.

Usage (from backend/):
    python -m ingest.build_index            # only rows with no hist yet
    python -m ingest.build_index --all      # recompute everything (after changing HistConfig)
"""

import argparse
import time

from psycopg.types.json import Jsonb

from app.db import connect
from app.features import lab_histogram
from app.palette import extract_palette, load_lab
from ingest.aic import image_cache_dir

BATCH = 50


def build_features(recompute_all: bool) -> None:
    cache = image_cache_dir()
    where = "" if recompute_all else "where hist is null"
    with connect() as conn:
        rows = conn.execute(f"select id, image_id from artworks {where} order by id").fetchall()
    print(f"{len(rows)} artworks to index", flush=True)

    done = missing = 0
    start = time.time()
    for i in range(0, len(rows), BATCH):
        updates = []
        for artwork_id, image_id in rows[i:i + BATCH]:
            path = cache / f"{image_id}.jpg"
            if not path.exists():
                missing += 1
                continue
            try:
                lab = load_lab(path)
            except OSError:  # corrupt cache entry; delete so ingest.aic re-downloads it
                path.unlink()
                missing += 1
                continue
            updates.append((Jsonb(extract_palette(lab)), lab_histogram(lab), artwork_id))
        with connect() as conn, conn.cursor() as cur:
            cur.executemany("update artworks set palette = %s, hist = %s where id = %s", updates)
        done += len(updates)
        print(f"{done}/{len(rows)} indexed ({time.time() - start:.0f}s)", flush=True)
    print(f"done: {done} indexed, {missing} missing from image cache (re-run ingest.aic)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="recompute rows that already have a hist")
    build_features(parser.parse_args().all)
