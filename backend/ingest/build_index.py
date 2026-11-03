"""Compute palette + histogram for every ingested artwork, then precompute palette edges.

Usage (from backend/):
    python -m ingest.build_index                  # only rows with no hist / no edges yet
    python -m ingest.build_index --all            # recompute features (after changing HistConfig)
    python -m ingest.build_index --rebuild-edges  # recompute all edges (after the corpus grows)
"""

import argparse
import time

from psycopg.types.json import Jsonb

from app.db import connect
from app.features import lab_histogram
from app.graph import EDGES_PER_NODE
from app.palette import extract_palette, load_lab
from app.retrieve import live_neighbors
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


def build_edges(rebuild: bool) -> None:
    """Store each painting's top reranked neighbors so web expansion is a table lookup."""
    missing = "" if rebuild else \
        "and not exists (select 1 from artwork_edges e where e.source_id = a.id and e.kind = 'palette')"
    with connect() as conn:
        ids = [r[0] for r in conn.execute(f"select a.id from artworks a where a.hist is not null and a.excluded is null {missing} order by a.id")]
    print(f"{len(ids)} artworks need palette edges", flush=True)

    start = time.time()
    for i in range(0, len(ids), BATCH):
        batch = ids[i:i + BATCH]
        with connect() as conn:
            rows = [(src, n["id"], n["score"]) for src in batch
                    for n in live_neighbors(conn, src, EDGES_PER_NODE)]
            with conn.transaction(), conn.cursor() as cur:
                cur.execute("delete from artwork_edges where source_id = any(%s) and kind = 'palette'", (batch,))
                cur.executemany("insert into artwork_edges (source_id, target_id, kind, score) "
                                "values (%s, %s, 'palette', %s)", rows)
        print(f"{min(i + BATCH, len(ids))}/{len(ids)} edged ({time.time() - start:.0f}s)", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="recompute rows that already have a hist")
    parser.add_argument("--rebuild-edges", action="store_true", help="recompute every painting's edges")
    args = parser.parse_args()
    build_features(args.all)
    build_edges(args.rebuild_edges)
