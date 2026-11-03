"""Human-judged precision@5 on outside images (photos, designs, screenshots).

Usage (from backend/):
    # 1. put ~30 images in backend/data/eval_human/
    python -m eval.label build        # → eval/labeling.html (open it in a browser)
    # 2. mark each result as a good / poor palette match, click "Download labels"
    python -m eval.label score ~/Downloads/human_labels.json

The top 5 of every system are pooled and shuffled per query, so the labeler can't tell
which system found which painting. P@5 of a system = share of its top 5 labeled "good".
"""

import argparse
import base64
import html
import json
import random
from pathlib import Path
from typing import Any

import numpy as np

from app.db import connect
from app.retrieve import DISTANCE_SCALE, palette_distance
from eval.featurize import corpus_features, featurize_many
from eval.run_eval import DEPLOYED, INITIAL
from ingest.aic import BACKEND_DIR

HUMAN_DIR = BACKEND_DIR / "data" / "eval_human"
EVAL_DIR = Path(__file__).parent
POOL_FILE = EVAL_DIR / "human_pool.json"
PAGE = EVAL_DIR / "labeling.html"
RESULTS = EVAL_DIR / "RESULTS.md"
TOP = 5
SYSTEMS = {
    "Histogram only (stage 1, 8x8x8)": None,
    "Histogram + palette rerank, α=0 (initial design)": INITIAL,
    "Histogram + palette rerank, α=0.5 (deployed)": DEPLOYED,
}


def top_ids(qf: dict[str, Any], H: np.ndarray, corpus_feats: list, ids: list[int], cfg: dict | None) -> list[int]:
    hq = qf["hist"]["8x8x8"] / np.linalg.norm(qf["hist"]["8x8x8"])
    sims = H @ hq
    order = np.argsort(-sims)
    if cfg is None:
        return [ids[i] for i in order[:TOP]]
    cand = order[:cfg["candidates"]]
    k, alpha = cfg["k"], cfg["alpha"]
    d = np.array([palette_distance(qf["palette"][k], corpus_feats[i]["palette"][k]) for i in cand])
    score = (1 - alpha) * np.exp(-d / DISTANCE_SCALE) + alpha * sims[cand]
    return [ids[i] for i in cand[np.argsort(-score)][:TOP]]


def build(image_dir: Path) -> None:
    images = sorted(p for p in image_dir.glob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"})
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
        results = {name: top_ids(qf, H, corpus_feats, ids, cfg) for name, cfg in SYSTEMS.items()}
        pooled = sorted({i for r in results.values() for i in r})
        rng.shuffle(pooled)
        pool.append({"query": path.name, "results": results, "pooled": pooled,
                     "palette": [s["hex"] for s in qf["palette"][6]]})
    POOL_FILE.write_text(json.dumps(pool, indent=1, ensure_ascii=False) + "\n")

    # Painting thumbnails come from AIC's IIIF server (no-referrer: it rejects some referers).
    image_url = {}
    with connect() as conn:
        for i, url in conn.execute("select id, image_url from artworks where id = any(%s)",
                                   ([i for q in pool for i in q["pooled"]],)):
            image_url[i] = url.replace("/full/843,/", "/full/300,/")
    blocks = []
    for q, path in zip(pool, images):
        data = base64.b64encode(path.read_bytes()).decode()
        mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        swatches = "".join(f'<span style="background:{h}"></span>' for h in q["palette"])
        cards = "".join(
            f'<label class="card"><img src="{image_url[i]}" referrerpolicy="no-referrer" loading="lazy">'
            f'<input type="checkbox" data-q="{html.escape(q["query"])}" data-id="{i}"> good match'
            f'<small>{html.escape(by_id[i]["title"][:50])}</small></label>'
            for i in q["pooled"])
        blocks.append(f'<section><div class="query"><img src="data:{mime};base64,{data}">'
                      f'<div class="sw">{swatches}</div><b>{html.escape(q["query"])}</b></div>'
                      f'<div class="cards">{cards}</div></section>')
    PAGE.write_text(f"""<!doctype html><meta charset="utf-8"><title>Palette match labeling</title>
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
  a.download='human_labels.json';a.click();
}}
</script>
""")
    n_pooled = sum(len(q["pooled"]) for q in pool)
    print(f"{len(pool)} queries, {n_pooled} paintings to label → {PAGE}")


def score(labels_path: Path) -> None:
    labels = json.loads(labels_path.read_text())
    pool = json.loads(POOL_FILE.read_text())
    lines = ["", "## Human-judged precision@5", "",
             f"{len(pool)} outside images (photos, designs). The top {TOP} of every system were pooled and "
             "shuffled, then labeled blind as good / poor palette matches.", "",
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
              f"pooled set would score {oracle:.0%} P@5, so the collection, not the ranking, is the main limit "
              "for outside images.", ""]
    text = RESULTS.read_text().split("\n## Human-judged precision@5")[0].rstrip("\n") + "\n"
    RESULTS.write_text(text + "\n".join(lines))
    (EVAL_DIR / "human_labels.json").write_text(json.dumps(labels, indent=1) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--images", type=Path, default=HUMAN_DIR)
    s = sub.add_parser("score")
    s.add_argument("labels", type=Path)
    args = parser.parse_args()
    build(args.images) if args.cmd == "build" else score(args.labels)
