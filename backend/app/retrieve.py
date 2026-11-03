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
# Weight of the stage-1 histogram similarity in the final score. Tuned on the eval dev split
# (eval/RESULTS.md): 0.5 beat pure palette reranking (0) on both dev and held-out test.
DEFAULT_ALPHA = 0.5
DEFAULT_METRIC = "de2000"


def _as_arrays(palette: Sequence[Swatch]) -> tuple[np.ndarray, np.ndarray]:
    lab = np.array([s["lab"] for s in palette], dtype=np.float64)
    w = np.array([s["weight"] for s in palette], dtype=np.float64)
    return lab, w / w.sum()


def _ground_distance(lab_p: np.ndarray, lab_q: np.ndarray, metric: str) -> np.ndarray:
    """Pairwise color distance (n, m). "ab" ignores lightness; "de2000_kL2" halves its weight."""
    a, b = lab_p[:, None, :], lab_q[None, :, :]
    if metric == "de2000":
        return deltaE_ciede2000(a, b)
    if metric == "de2000_kL2":
        return deltaE_ciede2000(a, b, kL=2)
    if metric in ("ab", "ab+chroma"):
        return np.linalg.norm(a[..., 1:] - b[..., 1:], axis=2)
    raise ValueError(f"unknown palette metric: {metric}")


def palette_matching(p: Sequence[Swatch], q: Sequence[Swatch],
                     metric: str = DEFAULT_METRIC) -> tuple[float, np.ndarray, np.ndarray]:
    """EMD between two palettes under a ground distance → (distance, flow, cost).

    flow[i, j] is the share of pixels matched from p[i] to q[j]; cost[i, j] is their distance.
    "ab+chroma" adds the difference in overall colorfulness to the distance.
    """
    lab_p, w_p = _as_arrays(p)
    lab_q, w_q = _as_arrays(q)
    n, m = len(w_p), len(w_q)
    cost = _ground_distance(lab_p, lab_q, metric)

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
    distance = float(res.fun)
    if metric == "ab+chroma":
        distance += abs(_mean_chroma(lab_p, w_p) - _mean_chroma(lab_q, w_q))
    return distance, res.x.reshape(n, m), cost


def _mean_chroma(lab: np.ndarray, weights: np.ndarray) -> float:
    return float((weights * np.hypot(lab[:, 1], lab[:, 2])).sum())


def palette_distance(p: Sequence[Swatch], q: Sequence[Swatch], metric: str = DEFAULT_METRIC) -> float:
    """Weighted matching cost between two palettes (0 = identical)."""
    return palette_matching(p, q, metric)[0]


def matched_colors(p: Sequence[Swatch], q: Sequence[Swatch], min_share: float = 0.05) -> list[dict[str, Any]]:
    """The color pairs the EMD actually matched, largest share first (explains *why* two palettes are close)."""
    _, flow, cost = palette_matching(p, q)
    pairs = [{"a": p[i]["hex"], "b": q[j]["hex"], "share": round(float(flow[i, j]), 3),
              "delta_e": round(float(cost[i, j]), 1)}
             for i, j in zip(*np.nonzero(flow >= min_share))]
    return sorted(pairs, key=lambda x: x["share"], reverse=True)


def palette_similarity(distance: float) -> float:
    return math.exp(-distance / DISTANCE_SCALE)


def rerank(query_palette: Sequence[Swatch], candidates: list[dict[str, Any]],
           k: int = 10, alpha: float = DEFAULT_ALPHA) -> list[dict[str, Any]]:
    """Score candidates by palette similarity, blended with stage-1 `hist_similarity` by `alpha`."""
    scored = []
    for c in candidates:
        d = palette_distance(query_palette, c["palette"])
        score = (1 - alpha) * palette_similarity(d) + alpha * c["hist_similarity"]
        scored.append({**c, "palette_distance": round(d, 3), "score": round(score, 4)})
    scored.sort(key=lambda c: c["score"], reverse=True)
    return scored[:k]


STAGE1_SQL = """
select id, source, source_url, title, artist, image_url, palette, similarity
from match_palettes(%s::vector, %s)
"""


def _candidate(r: tuple) -> dict[str, Any]:
    return {"id": r[0], "source": r[1], "source_url": r[2], "title": r[3], "artist": r[4],
            "image_url": r[5], "palette": r[6], "hist_similarity": round(float(r[7]), 4)}


def stage1(conn: psycopg.Connection, hist: np.ndarray, candidates: int = 100) -> list[dict[str, Any]]:
    return [_candidate(r) for r in conn.execute(STAGE1_SQL, (hist, candidates)) if r[6]]


def live_neighbors(conn: psycopg.Connection, artwork_id: int, k: int = 20,
                   candidates: int = 100) -> list[dict[str, Any]]:
    """Top-k reranked neighbors of a painting already in the collection (itself excluded)."""
    row = conn.execute("select palette from artworks where id = %s", (artwork_id,)).fetchone()
    if not row or not row[0]:
        return []
    pool = [_candidate(r) for r in conn.execute(
        "select id, source, source_url, title, artist, image_url, palette, similarity "
        "from match_palettes_by_id(%s, %s)", (artwork_id, candidates)) if r[6]]
    return rerank(row[0], pool, k)


def match_image(conn: psycopg.Connection, image: ImageInput, k: int = 10, candidates: int = 100,
                alpha: float = DEFAULT_ALPHA, config: HistConfig = DEFAULT_CONFIG,
                ) -> tuple[list[Swatch], list[dict[str, Any]]]:
    """Full pipeline for an uploaded image: (query palette, top-k reranked matches)."""
    lab = load_lab(image)
    palette = extract_palette(lab)
    pool = stage1(conn, lab_histogram(lab, config), candidates)
    return palette, rerank(palette, pool, k, alpha)
