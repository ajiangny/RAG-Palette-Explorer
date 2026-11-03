"""Human-judged precision@5 on outside images (photos, designs, screenshots).

Usage (from backend/):
    # 1. put ~30 images in backend/data/eval_human/
    python -m eval.label build        # → eval/labeling.html (open it in a browser)
    # 2. mark each result as a good / poor palette match, click "Download labels"
    python -m eval.label score ~/Downloads/human_labels.json

The top 5 of every system are pooled and shuffled per query, so the labeler can't tell
which system found which painting. P@5 of a system = share of its top 5 labeled "good".
Labels accumulate in eval/human_labels.json: after the collection or a system changes,
`build` shows only paintings that have not been judged yet, and `score` merges them in.

Held-out test of a frozen challenger (see eval/TEST_PROTOCOL.md), with its own images and labels:
    # put ~30 new images in backend/data/eval_human_test/
    python -m eval.label build-test   # → eval/labeling_test.html; label it in one sitting
    python -m eval.label score-test ~/Downloads/human_labels_test.json
"""

import argparse
import base64
import hashlib
import html
import json
import random
from pathlib import Path
from typing import Any

import numpy as np

from app.retrieve import DISTANCE_SCALE, palette_distance
from eval.featurize import corpus_features, featurize_many
from eval.run_eval import DEPLOYED, INITIAL
from ingest.aic import BACKEND_DIR, image_cache_dir

HUMAN_DIR = BACKEND_DIR / "data" / "eval_human"
EVAL_DIR = Path(__file__).parent
POOL_FILE = EVAL_DIR / "human_pool.json"
BASELINE_POOL = EVAL_DIR / "human_pool_aic_only.json"
LABELS = EVAL_DIR / "human_labels.json"
PAGE = EVAL_DIR / "labeling.html"
RESULTS = EVAL_DIR / "RESULTS.md"
TEST_DIR = BACKEND_DIR / "data" / "eval_human_test"
TEST_POOL = EVAL_DIR / "human_pool_test.json"
TEST_LABELS = EVAL_DIR / "human_labels_test.json"
TEST_PAGE = EVAL_DIR / "labeling_test.html"
TEST_RESULTS = EVAL_DIR / "RESULTS_human_test.md"
TOP = 5
DEPLOYED_NAME = "Histogram + palette rerank, α=0.5 (deployed)"
SYSTEMS = {
    "Histogram only (stage 1, 8x8x8)": None,
    "Histogram + palette rerank, α=0 (initial design)": INITIAL,
    DEPLOYED_NAME: DEPLOYED,
    "Finalist: CIEDE2000 with kL=2, α=0.5": {**DEPLOYED, "metric": "de2000_kL2"},
    "Finalist: hue/chroma EMD, α=0.5": {**DEPLOYED, "metric": "ab"},
    "Finalist: hue/chroma EMD + chroma penalty, α=0.5": {**DEPLOYED, "metric": "ab+chroma"},
}


CHALLENGER_NAME = "Finalist: hue/chroma EMD, α=0.5"
TEST_SYSTEMS = {DEPLOYED_NAME: SYSTEMS[DEPLOYED_NAME], CHALLENGER_NAME: SYSTEMS[CHALLENGER_NAME]}


def top_ids(qf: dict[str, Any], H: np.ndarray, corpus_feats: list, ids: list[int], cfg: dict | None) -> list[int]:
    hq = qf["hist"]["8x8x8"] / np.linalg.norm(qf["hist"]["8x8x8"])
    sims = H @ hq
    order = np.argsort(-sims)
    if cfg is None:
        return [ids[i] for i in order[:TOP]]
    cand = order[:cfg["candidates"]]
    k, alpha = cfg["k"], cfg["alpha"]
    metric = cfg.get("metric", "de2000")
    d = np.array([palette_distance(qf["palette"][k], corpus_feats[i]["palette"][k], metric) for i in cand])
    score = (1 - alpha) * np.exp(-d / DISTANCE_SCALE) + alpha * sims[cand]
    return [ids[i] for i in cand[np.argsort(-score)][:TOP]]


def list_images(image_dir: Path) -> list[Path]:
    return sorted(p for p in image_dir.glob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"})


def build(image_dir: Path, systems: dict[str, dict | None] = SYSTEMS, pool_file: Path = POOL_FILE,
          labels_file: Path = LABELS, page: Path = PAGE, download_name: str = "human_labels.json") -> None:
    images = list_images(image_dir)
    if not images:
        raise SystemExit(f"no images in {image_dir}; add ~30 photos/designs first")
    rows, corpus_feats = corpus_features()
    ids = [r["id"] for r in rows]
    by_id = {r["id"]: r for r in rows}
    H = np.stack([f["hist"]["8x8x8"] for f in corpus_feats])
    H /= np.linalg.norm(H, axis=1, keepdims=True)
    query_feats = featurize_many(images)

    rng = random.Random(0)
    pool = []
    for path, qf in zip(images, query_feats):
        results = {name: top_ids(qf, H, corpus_feats, ids, cfg) for name, cfg in systems.items()}
        pooled = sorted({i for r in results.values() for i in r})
        rng.shuffle(pooled)
        pool.append({"query": path.name, "results": results, "pooled": pooled,
                     "palette": [s["hex"] for s in qf["palette"][6]]})
    pool_file.write_text(json.dumps(pool, indent=1, ensure_ascii=False) + "\n")
    judged = json.loads(labels_file.read_text()) if labels_file.exists() else {}
    for q in pool:
        q["new"] = [i for i in q["pooled"] if str(i) not in judged.get(q["query"], {})]

    # Embed the cached copies: the page must not depend on museum servers being reachable,
    # since a painting that fails to load would get mislabeled as a poor match.
    def thumbnail(i: int) -> str:
        path = image_cache_dir() / f"{by_id[i]['image_id']}.jpg"
        return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode()

    blocks = []
    for q, path in zip(pool, images):
        if not q["new"]:
            continue
        data = base64.b64encode(path.read_bytes()).decode()
        mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        swatches = "".join(f'<span style="background:{h}"></span>' for h in q["palette"])
        cards = "".join(
            f'<label class="card"><img src="{thumbnail(i)}">'
            f'<input type="checkbox" data-q="{html.escape(q["query"])}" data-id="{i}"> good match'
            f'<small>{html.escape(by_id[i]["title"][:50])}</small></label>'
            for i in q["new"])
        blocks.append(f'<section><div class="query"><img src="data:{mime};base64,{data}">'
                      f'<div class="sw">{swatches}</div><b>{html.escape(q["query"])}</b></div>'
                      f'<div class="cards">{cards}</div></section>')
    page.write_text(f"""<!doctype html><meta charset="utf-8"><title>Palette match labeling</title>
<style>
body{{font-family:system-ui,sans-serif;margin:0;padding:1rem 1.5rem 5rem;background:#181614;color:#eee}}
section{{display:flex;gap:1.5rem;padding:1.25rem 0;border-bottom:1px solid #333}}
.query{{width:220px;flex-shrink:0}} .query img{{width:100%;border-radius:6px}}
.sw{{display:flex;height:16px;margin:.4rem 0}} .sw span{{flex:1}}
.cards{{display:flex;flex-wrap:wrap;gap:.75rem}}
.card{{width:150px;display:flex;flex-direction:column;gap:.25rem;font-size:.85rem;cursor:pointer}}
.card img{{width:150px;height:150px;object-fit:cover;border-radius:6px;border:3px solid transparent}}
.card:has(input:checked) img{{border-color:#e8c66a}} small{{color:#999}}
#bar{{position:fixed;bottom:0;left:0;right:0;padding:.75rem 1.5rem;background:#222;display:flex;gap:1rem;align-items:center}}
button{{font:inherit;padding:.4rem 1rem;background:#e8c66a;border:0;border-radius:6px;cursor:pointer}}
</style>
<h1>Is each painting a good palette match for the image on the left?</h1>
<p>Judge color only (hues, proportions, light/dark), not subject. Check the good matches; leave poor ones unchecked.</p>
{''.join(blocks)}
<div id="bar"><button onclick="save()">Download labels</button><span id="n"></span></div>
<script>
const boxes=[...document.querySelectorAll('input[type=checkbox]')];
const count=()=>document.getElementById('n').textContent=boxes.filter(b=>b.checked).length+' marked good of '+boxes.length;
boxes.forEach(b=>b.addEventListener('change',count));count();
function save(){{
  const labels={{}};
  for(const b of boxes){{(labels[b.dataset.q]??={{}})[b.dataset.id]=b.checked}}
  const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob([JSON.stringify(labels,null,1)],{{type:'application/json'}}));
  a.download='{download_name}';a.click();
}}
</script>
""")
    n_new = sum(len(q["new"]) for q in pool)
    n_judged = sum(len(q["pooled"]) for q in pool) - n_new
    print(f"{len(pool)} queries: {n_new} paintings to label ({n_judged} already judged) → {page}")


def score(labels_path: Path) -> None:
    labels = json.loads(LABELS.read_text()) if LABELS.exists() else {}
    for query, judged in json.loads(labels_path.read_text()).items():
        labels.setdefault(query, {}).update(judged)
    pool = json.loads(POOL_FILE.read_text())
    missing = [(q["query"], i) for q in pool for i in q["pooled"] if str(i) not in labels.get(q["query"], {})]
    if missing:
        raise SystemExit(f"{len(missing)} pooled paintings have no label yet, e.g. {missing[:3]}; "
                         "re-run `build` and label them")
    lines = ["", "## Human-judged precision@5", "",
             f"{len(pool)} outside images (photos, designs). The top {TOP} of every system were pooled and "
             "shuffled, then labeled as good / poor palette matches without showing which system found which.", "",
             "| System | P@5 |", "|---|---|"]
    per_query = {name: np.array([np.mean([labels[q["query"]][str(i)] for i in q["results"][name]]) for q in pool])
                 for name in SYSTEMS}
    for name, p in per_query.items():
        lines.append(f"| {name} | {p.mean():.0%} |")

    # Paired bootstrap over queries: is each system really different from histogram-only?
    rng = np.random.default_rng(0)
    base_name, *others = SYSTEMS
    lines += ["", f"Difference from *{base_name}* (paired bootstrap over images, 95% CI):", ""]
    for name in others:
        d = per_query[name] - per_query[base_name]
        boots = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(10_000)]
        lo, hi = np.percentile(boots, [2.5, 97.5])
        lines.append(f"- {name}: {d.mean() * 100:+.1f} points ({lo * 100:+.1f} to {hi * 100:+.1f}); "
                     f"better on {int((d > 0).sum())}, worse on {int((d < 0).sum())}, tied on {int((d == 0).sum())} images")
    goods = np.array([sum(labels[q["query"]].values()) for q in pool])
    oracle = np.mean(np.minimum(goods, TOP) / TOP)
    lines += ["", f"Good matches per image among the ~{np.mean([len(q['pooled']) for q in pool]):.0f} pooled paintings: "
              f"median {np.median(goods):.0f} (min {goods.min()}, max {goods.max()}). A perfect reordering of the "
              f"pooled set would score {oracle:.0%} P@5, which is the headroom available to better ranking.", ""]
    # Same images, same labels, smaller collection: what did adding a museum change?
    if BASELINE_POOL.exists():
        before_pool = {q["query"]: q for q in json.loads(BASELINE_POOL.read_text())}
        deployed = DEPLOYED_NAME
        before = np.array([np.mean([labels[q["query"]][str(i)] for i in before_pool[q["query"]]["results"][deployed]])
                           for q in pool])
        d = per_query[deployed] - before
        boots = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(10_000)]
        lo, hi = np.percentile(boots, [2.5, 97.5])
        lines += [f"Adding the Cleveland collection, deployed system: {before.mean():.0%} → {per_query[deployed].mean():.0%} P@5, "
                  f"{d.mean() * 100:+.1f} points ({lo * 100:+.1f} to {hi * 100:+.1f}, paired bootstrap); "
                  f"better on {int((d > 0).sum())}, worse on {int((d < 0).sum())}, tied on {int((d == 0).sum())} images. "
                  "Paintings new to the pool were labeled in a second session, knowing they were new, so "
                  "labeler drift could account for some of this.", ""]
    if TEST_RESULTS.exists():
        lines += ["The finalists above were selected on these same images, so their lift is not a validated result. "
                  "The held-out test of the chosen finalist is in `RESULTS_human_test.md`.", ""]
    text = RESULTS.read_text().split("\n## Human-judged precision@5")[0].rstrip("\n") + "\n"
    RESULTS.write_text(text + "\n".join(lines))
    LABELS.write_text(json.dumps(labels, indent=1) + "\n")
    print("\n".join(lines))


def build_test() -> None:
    def digest(p: Path) -> str:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    reused = {digest(p) for p in list_images(HUMAN_DIR)} & {digest(p) for p in list_images(TEST_DIR)}
    if reused:
        raise SystemExit(f"{len(reused)} test image(s) are byte-identical to dev images; replace them")
    build(TEST_DIR, TEST_SYSTEMS, TEST_POOL, TEST_LABELS, TEST_PAGE, "human_labels_test.json")


def score_test(labels_path: Path) -> None:
    labels = json.loads(labels_path.read_text())
    pool = json.loads(TEST_POOL.read_text())
    missing = [(q["query"], i) for q in pool for i in q["pooled"] if str(i) not in labels.get(q["query"], {})]
    if missing:
        raise SystemExit(f"{len(missing)} pooled paintings have no label, e.g. {missing[:3]}")
    per_query = {name: np.array([np.mean([labels[q["query"]][str(i)] for i in q["results"][name]]) for q in pool])
                 for name in TEST_SYSTEMS}
    d = per_query[CHALLENGER_NAME] - per_query[DEPLOYED_NAME]
    rng = np.random.default_rng(0)
    boots = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(10_000)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    lines = ["# Held-out human test", "",
             f"{len(pool)} new images, labeled in one sitting with both systems' top {TOP} pooled and shuffled. "
             "Challenger and decision rule were committed first (`TEST_PROTOCOL.md`).", "",
             "| System | P@5 |", "|---|---|",
             *(f"| {name} | {p.mean():.0%} |" for name, p in per_query.items()), "",
             f"Difference: {d.mean() * 100:+.1f} points (95% CI {lo * 100:+.1f} to {hi * 100:+.1f}, paired bootstrap); "
             f"better on {int((d > 0).sum())}, worse on {int((d < 0).sum())}, tied on {int((d == 0).sum())} images.", "",
             f"Decision rule: {'met' if lo > 0 else 'NOT met'} (lower bound of the CI must be above 0).", ""]
    TEST_RESULTS.write_text("\n".join(lines))
    TEST_LABELS.write_text(json.dumps(labels, indent=1) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--images", type=Path, default=HUMAN_DIR)
    s = sub.add_parser("score")
    s.add_argument("labels", type=Path)
    sub.add_parser("build-test")
    t = sub.add_parser("score-test")
    t.add_argument("labels", type=Path)
    args = parser.parse_args()
    if args.cmd == "build":
        build(args.images)
    elif args.cmd == "score":
        score(args.labels)
    elif args.cmd == "build-test":
        build_test()
    else:
        score_test(args.labels)
