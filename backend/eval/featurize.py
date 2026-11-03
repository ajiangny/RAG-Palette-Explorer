"""Offline features for evaluation: each image under every candidate config, in one pass.

Evaluation runs in memory with exact cosine search instead of going through pgvector,
so bin layouts other than the deployed vector(512) can be compared without a migration.
"""

import hashlib
import pickle
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from app.db import connect
from app.features import HistConfig, lab_histogram
from app.palette import extract_palette, load_lab
from ingest.aic import BACKEND_DIR, image_cache_dir

HIST_CONFIGS: dict[str, HistConfig] = {
    "6x6x6": HistConfig(bins=(6, 6, 6)),
    "8x8x8": HistConfig(bins=(8, 8, 8)),  # deployed
    "8x8x8-raw": HistConfig(bins=(8, 8, 8), hellinger=False),
    "4x8x8": HistConfig(bins=(4, 8, 8)),
    "12x12x12": HistConfig(bins=(12, 12, 12)),
}
PALETTE_KS = (4, 6, 8)  # 6 is deployed
CACHE_DIR = BACKEND_DIR / "data" / "eval_cache"


def featurize(path: Path) -> dict[str, Any]:
    lab = load_lab(path)
    return {
        "hist": {name: lab_histogram(lab, cfg) for name, cfg in HIST_CONFIGS.items()},
        "palette": {k: extract_palette(lab, k=k) for k in PALETTE_KS},
    }


def featurize_many(paths: list[Path], workers: int = 16) -> list[dict[str, Any]]:
    with ProcessPoolExecutor(workers) as pool:
        return list(pool.map(featurize, paths, chunksize=8))


def corpus() -> list[dict[str, Any]]:
    """Every indexed artwork, in id order."""
    with connect() as conn:
        rows = conn.execute("select id, image_id, title, artist from artworks "
                            "where hist is not null order by id").fetchall()
    return [{"id": r[0], "image_id": r[1], "title": r[2], "artist": r[3]} for r in rows]


def corpus_features() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(corpus rows, features) — cached on disk, keyed by the corpus ids and config names."""
    rows = corpus()
    spec = repr(([r["id"] for r in rows], HIST_CONFIGS, PALETTE_KS)).encode()
    path = CACHE_DIR / f"corpus_{hashlib.sha1(spec).hexdigest()[:12]}.pkl"
    if path.exists():
        return rows, pickle.loads(path.read_bytes())
    print(f"featurizing {len(rows)} corpus images (one-time)...", flush=True)
    cache = image_cache_dir()
    feats = featurize_many([cache / f"{r['image_id']}.jpg" for r in rows])
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pickle.dumps(feats))
    return rows, feats
