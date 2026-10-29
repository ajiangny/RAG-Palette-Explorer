"""Two-stage retrieval.

Stage 1: pgvector ANN over LAB histograms (cosine) → `candidates` artworks.
Stage 2: rerank by palette distance — Earth Mover's Distance between the two
weighted palettes with CIEDE2000 as the ground distance — optionally blended
with the stage-1 similarity.
"""

import math
from collections.abc import Sequence
from typing import Any

import numpy as np
import psycopg
from scipy.optimize import linprog
from skimage.color import deltaE_ciede2000

from app.features import DEFAULT_CONFIG, HistConfig, lab_histogram
from app.palette import ImageInput, Swatch, extract_palette, load_lab

# Palette distance → similarity: exp(-d / SCALE). ΔE ≈ 25 between palettes is
# already "clearly different", so this maps d=25 to ~0.37.
DISTANCE_SCALE = 25.0


def _as_arrays(palette: Sequence[Swatch]) -> tuple[np.ndarray, np.ndarray]:
    lab = np.array([s["lab"] for s in palette], dtype=np.float64)
    w = np.array([s["weight"] for s in palette], dtype=np.float64)
    return lab, w / w.sum()


def palette_distance(p: Sequence[Swatch], q: Sequence[Swatch]) -> float:
    """Weighted CIEDE2000 matching cost between two palettes (EMD; 0 = identical)."""
    lab_p, w_p = _as_arrays(p)
    lab_q, w_q = _as_arrays(q)
    n, m = len(w_p), len(w_q)
    cost = deltaE_ciede2000(lab_p[:, None, :], lab_q[None, :, :])  # (n, m)

    # Transport plan f_ij >= 0 with row sums w_p and column sums w_q.
    a_eq = np.zeros((n + m, n * m))
    for i in range(n):
        a_eq[i, i * m:(i + 1) * m] = 1
    for j in range(m):
        a_eq[n + j, j::m] = 1
    res = linprog(cost.ravel(), A_eq=a_eq, b_eq=np.concatenate([w_p, w_q]),
                  bounds=(0, None), method="highs")
    if not res.success:
        raise RuntimeError(f"palette EMD failed: {res.message}")
    return float(res.fun)


def palette_similarity(distance: float) -> float:
    return math.exp(-distance / DISTANCE_SCALE)


def rerank(query_palette: Sequence[Swatch], candidates: list[dict[str, Any]],
           k: int = 10, alpha: float = 0.0) -> list[dict[str, Any]]:
    """Score candidates by palette similarity, blended with stage-1 `hist_similarity` by `alpha`."""
    scored = []
    for c in candidates:
        d = palette_distance(query_palette, c["palette"])
        score = (1 - alpha) * palette_similarity(d) + alpha * c["hist_similarity"]
        scored.append({**c, "palette_distance": round(d, 3), "score": round(score, 4)})
    scored.sort(key=lambda c: c["score"], reverse=True)
    return scored[:k]


STAGE1_SQL = """
select id, aic_id, title, artist, image_url, palette, similarity
from match_palettes(%s::vector, %s)
"""


def stage1(conn: psycopg.Connection, hist: np.ndarray, candidates: int = 100,
           exclude_id: int | None = None) -> list[dict[str, Any]]:
    rows = conn.execute(STAGE1_SQL, (hist, candidates + (exclude_id is not None))).fetchall()
    return [
        {"id": r[0], "aic_id": r[1], "title": r[2], "artist": r[3], "image_url": r[4],
         "palette": r[5], "hist_similarity": round(float(r[6]), 4)}
        for r in rows if r[0] != exclude_id and r[5]
    ][:candidates]


def match_image(conn: psycopg.Connection, image: ImageInput, k: int = 10, candidates: int = 100,
                alpha: float = 0.0, config: HistConfig = DEFAULT_CONFIG,
                ) -> tuple[list[Swatch], list[dict[str, Any]]]:
    """Full pipeline for an uploaded image: (query palette, top-k reranked matches)."""
    lab = load_lab(image)
    palette = extract_palette(lab)
    pool = stage1(conn, lab_histogram(lab, config), candidates)
    return palette, rerank(palette, pool, k, alpha)
