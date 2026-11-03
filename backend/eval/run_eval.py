"""Retrieval evaluation on the automatic test set (crops / photo-like copies → source painting).

Usage (from backend/):
    python -m eval.make_queries   # once
    python -m eval.run_eval

Compares stage-1 histogram ranking alone against histogram + palette rerank, sweeping
histogram bins, palette k, stage-1 candidate count and alpha. The best config is chosen
on the dev split by MRR and reported on the held-out test split.
Writes eval/results.csv (every config) and eval/RESULTS.md (summary).
"""

import csv
import json
import math
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

from app.retrieve import DISTANCE_SCALE, palette_distance
from eval.featurize import HIST_CONFIGS, PALETTE_KS, corpus_features, featurize_many
from eval.make_queries import QUERY_DIR, TESTSET

CANDIDATES = (25, 50, 100, 200)
ALPHAS = (0.0, 0.25, 0.5, 0.75)
POOL = max(CANDIDATES)
INITIAL = {"hist": "8x8x8", "k": 6, "candidates": 100, "alpha": 0.0}  # first design: pure palette rerank
DEPLOYED = {"hist": "8x8x8", "k": 6, "candidates": 100, "alpha": 0.5}  # chosen on dev, no migration needed
OUT_DIR = Path(__file__).parent

_corpus_palettes: dict[int, list] = {}


def _init(palettes: dict[int, list]) -> None:
    global _corpus_palettes
    _corpus_palettes = palettes


def _distances(args: tuple[int, list, Sequence[int]]) -> np.ndarray:
    k, query_palette, idx = args
    return np.array([palette_distance(query_palette, _corpus_palettes[k][i]) for i in idx])


def metrics(ranks: list[float]) -> dict[str, float]:
    r = np.array(ranks)
    return {"hit1": float(np.mean(r <= 1)), "hit5": float(np.mean(r <= 5)),
            "hit10": float(np.mean(r <= 10)), "mrr": float(np.mean(1 / r)), "n": len(r)}


def main() -> None:
    testset = json.loads(TESTSET.read_text())
    rows, corpus_feats = corpus_features()
    id_to_idx = {r["id"]: i for i, r in enumerate(rows)}
    truth = [id_to_idx[q["source_id"]] for q in testset]
    print(f"{len(testset)} queries against {len(rows)} paintings; featurizing queries...", flush=True)
    query_feats = featurize_many([QUERY_DIR / q["query"] for q in testset])

    # ranks[config] = rank of the true painting for each query (inf if it fell out of the candidates)
    ranks: dict[tuple, list[float]] = {}
    corpus_palettes = {k: [f["palette"][k] for f in corpus_feats] for k in PALETTE_KS}
    with ProcessPoolExecutor(16, initializer=_init, initargs=(corpus_palettes,)) as pool:
        for hist_name in HIST_CONFIGS:
            H = np.stack([f["hist"][hist_name] for f in corpus_feats])
            H /= np.linalg.norm(H, axis=1, keepdims=True)
            Q = np.stack([f["hist"][hist_name] for f in query_feats])
            Q /= np.linalg.norm(Q, axis=1, keepdims=True)
            sims = Q @ H.T  # exact cosine, (queries, corpus)
            order = np.argsort(-sims, axis=1)
            ranks[("hist-only", hist_name, None, None, None)] = [
                float(np.where(order[i] == t)[0][0] + 1) for i, t in enumerate(truth)]
            pools = order[:, :POOL]
            for k in PALETTE_KS:
                dists = list(pool.map(_distances, [(k, qf["palette"][k], pools[i])
                                                   for i, qf in enumerate(query_feats)], chunksize=4))
                for c in CANDIDATES:
                    for alpha in ALPHAS:
                        out = []
                        for i, t in enumerate(truth):
                            cand = pools[i, :c]
                            score = ((1 - alpha) * np.exp(-dists[i][:c] / DISTANCE_SCALE)
                                     + alpha * sims[i, cand])
                            hit = np.where(cand[np.argsort(-score)] == t)[0]
                            out.append(float(hit[0] + 1) if len(hit) else math.inf)
                        ranks[("rerank", hist_name, k, c, alpha)] = out
            print(f"  {hist_name} done", flush=True)

    results = []
    for (method, hist_name, k, c, alpha), r in ranks.items():
        for split in ("dev", "test"):
            for kind in ("all", "crop", "photo"):
                sel = [x for x, q in zip(r, testset)
                       if q["split"] == split and kind in ("all", q["kind"])]
                results.append({"split": split, "kind": kind, "method": method, "hist": hist_name,
                                "k": k, "candidates": c, "alpha": alpha, **metrics(sel)})
    with open(OUT_DIR / "results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0]))
        w.writeheader()
        w.writerows(results)

    def find(split: str, kind: str, **cfg: Any) -> dict[str, Any]:
        return next(r for r in results if r["split"] == split and r["kind"] == kind
                    and all(r[key] == v for key, v in cfg.items()))

    dev_all = [r for r in results if r["split"] == "dev" and r["kind"] == "all"]
    best_hist = max((r for r in dev_all if r["method"] == "hist-only"), key=lambda r: r["mrr"])
    best_rerank = max((r for r in dev_all if r["method"] == "rerank"), key=lambda r: r["mrr"])
    systems = [
        ("Histogram only (stage 1, 8x8x8)", {"method": "hist-only", "hist": "8x8x8"}),
        ("Histogram + palette rerank, α=0 (initial design)", {"method": "rerank", **INITIAL}),
        ("**Histogram + palette rerank, α=0.5 (deployed)**", {"method": "rerank", **DEPLOYED}),
        (f"Histogram only, best on dev ({best_hist['hist']})", {"method": "hist-only", "hist": best_hist["hist"]}),
        (f"Histogram + rerank, best on dev ({best_rerank['hist']}, k={best_rerank['k']}, "
         f"{best_rerank['candidates']} cand., α={best_rerank['alpha']})",
         {key: best_rerank[key] for key in ("method", "hist", "k", "candidates", "alpha")}),
    ]
    n_test = find("test", "all", **systems[0][1])["n"]
    lines = [
        "# Retrieval evaluation",
        "",
        f"Automatic test set: {len(testset)} queries made from {len(testset) // 2} collection paintings "
        f"(a 40–70% crop and a photo-like copy of each), searched against all {len(rows)} paintings. "
        "Ground truth is the source painting. Configs were tuned on the dev half; numbers below are "
        f"the held-out **test** half ({n_test} queries). Exact cosine search, in memory.",
        "",
        "| System | Hit@1 | Hit@5 | Hit@10 | MRR | Hit@5 crop | Hit@5 photo |",
        "|---|---|---|---|---|---|---|",
    ]
    for label, cfg in systems:
        a, cr, ph = (find("test", kind, **cfg) for kind in ("all", "crop", "photo"))
        lines.append(f"| {label} | {a['hit1']:.0%} | {a['hit5']:.0%} | {a['hit10']:.0%} | {a['mrr']:.3f} "
                     f"| {cr['hit5']:.0%} | {ph['hit5']:.0%} |")
    lines += ["",
              f"With {n_test} test queries, one query is {100 / n_test:.0f} point of Hit@k, so gaps of a few "
              "points are within noise. Every config and split is in `results.csv`.", ""]
    # Keep the human-judged section written by eval.label, if any.
    old = (OUT_DIR / "RESULTS.md").read_text() if (OUT_DIR / "RESULTS.md").exists() else ""
    human = old.partition("\n## Human-judged precision@5")
    (OUT_DIR / "RESULTS.md").write_text("\n".join(lines) + (human[1] + human[2] if human[1] else ""))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
