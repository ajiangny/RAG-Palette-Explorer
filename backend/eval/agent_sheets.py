"""Blind image sheets so an AI labeler can judge the dev pool under eval/LABELING_RULE.md.

Usage (from backend/):
    python -m eval.agent_sheets pass1                  # every pooled pair, before and after the National Gallery
    python -m eval.agent_sheets pass2 --labels FILE    # 36 of pass 1's pairs again, 18 good and 18 poor
    python -m eval.agent_sheets final                  # every pair in the final test's pool

Writes data/eval_agent/<pass>/sheet_*.jpg and data/eval_agent/<pass>_key.json. Sheets show only the image,
paintings and neutral cell ids; the key that maps ids back to pairs sits outside the sheet folder.
Each sheet also prints a random check code, so a labeler that never received the image can't pass as having seen it.
"""

import argparse
import json
import random
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.db import connect
from eval.featurize import corpus_features, featurize_many
from eval.label import FINAL_POOL, HUMAN_DIR, POOL_FILE, SYSTEMS, TEST_DIR, list_images, top_ids
from ingest.aic import BACKEND_DIR, image_cache_dir

OUT = BACKEND_DIR / "data" / "eval_agent"
BEFORE_POOL = OUT / "pool_before_clean.json"
PER_SHEET = 6
CELL = 300
QUERY = 460
LABEL = 28
GRAY = (128, 128, 128)  # neutral, so the background doesn't shift how colors look
CODE_CHARS = "ACDEFGHJKLMNPQRTUVWXY34679"  # no look-alikes such as 0/O or 1/I


def fit(path: Path, box: int) -> Image.Image:
    img = Image.open(path).convert("RGBA")
    img.thumbnail((box, box), Image.LANCZOS)
    flat = Image.new("RGB", img.size, GRAY)
    flat.paste(img, mask=img.getchannel("A"))
    return flat


def before_pool() -> list[dict[str, Any]]:
    """Every system's top 5 on the cleaned collection without the National Gallery."""
    rows, feats = corpus_features()
    with connect() as conn:
        nga = {r[0] for r in conn.execute("select id from artworks where source = 'nga'")}
    keep = [i for i, r in enumerate(rows) if r["id"] not in nga]
    ids = [rows[i]["id"] for i in keep]
    sub = [feats[i] for i in keep]
    H = np.stack([f["hist"]["8x8x8"] for f in sub])
    H /= np.linalg.norm(H, axis=1, keepdims=True)
    images = list_images(HUMAN_DIR)
    return [{"query": p.name, "results": {name: top_ids(qf, H, sub, ids, cfg) for name, cfg in SYSTEMS.items()}}
            for p, qf in zip(images, featurize_many(images))]


def render(name: str, pairs: Iterable[tuple[str, int]], seed: int, image_dir: Path = HUMAN_DIR) -> None:
    with connect() as conn:
        image_ids = dict(conn.execute("select id, image_id from artworks").fetchall())
    by_query: dict[str, list[int]] = {}
    for query, painting in pairs:
        by_query.setdefault(query, []).append(painting)
    rng = random.Random(seed)
    queries = sorted(by_query)
    rng.shuffle(queries)
    folder = OUT / name
    folder.mkdir(parents=True, exist_ok=False)
    code_rng = random.Random(seed + 1000)
    key, codes, n = {}, {}, 0
    for query in queries:
        rng.shuffle(by_query[query])
        for start in range(0, len(by_query[query]), PER_SHEET):
            n += 1
            sheet = Image.new("RGB", (QUERY + 3 * CELL + 50, 2 * (CELL + LABEL) + 30), GRAY)
            draw = ImageDraw.Draw(sheet)
            q = fit(image_dir / query, QUERY)
            draw.text((10, 8), "UPLOADED IMAGE", fill="white")
            sheet.paste(q, (10, LABEL))
            for c, painting in enumerate(by_query[query][start:start + PER_SHEET], 1):
                x, y = QUERY + 30 + (c - 1) % 3 * CELL, ((c - 1) // 3) * (CELL + LABEL)
                cell = f"s{n:03d}-{c}"
                draw.text((x, y + 8), cell, fill="white")
                sheet.paste(fit(image_cache_dir() / f"{image_ids[painting]}.jpg", CELL - 10), (x, y + LABEL))
                key[cell] = {"query": query, "id": painting}
            code = "".join(code_rng.choices(CODE_CHARS, k=4))
            codes[f"sheet_{n:03d}"] = code
            draw.text((10, sheet.height - 34), f"CHECK CODE: {code}", fill="white", font=ImageFont.load_default(size=22))
            sheet.save(folder / f"sheet_{n:03d}.jpg", quality=92)
    (OUT / f"{name}_key.json").write_text(json.dumps(key, indent=1) + "\n")
    (OUT / f"{name}_codes.json").write_text(json.dumps(codes, indent=1) + "\n")
    print(f"{name}: {len(key)} pairs on {n} sheets across {len(queries)} images → {folder}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("name", choices=["pass1", "pass2", "final"])
    parser.add_argument("--labels", type=Path)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.name == "final":
        pool = json.loads(FINAL_POOL.read_text())
        render("final", [(q["query"], i) for q in pool for i in q["pooled"]], seed=21, image_dir=TEST_DIR)
    elif args.name == "pass1":
        before = before_pool()
        BEFORE_POOL.write_text(json.dumps(before, indent=1) + "\n")
        pairs = {(q["query"], i) for q in json.loads(POOL_FILE.read_text()) for i in q["pooled"]}
        pairs |= {(q["query"], i) for q in before for r in q["results"].values() for i in r}
        render("pass1", sorted(pairs), seed=11)
    else:
        key = json.loads((OUT / "pass1_key.json").read_text())
        labels = json.loads(args.labels.read_text())
        rng = random.Random(12)
        good = sorted(c for c, v in labels.items() if v)
        poor = sorted(c for c, v in labels.items() if not v)
        cells = rng.sample(good, min(18, len(good))) + rng.sample(poor, min(18, len(poor)))
        render("pass2", [(key[c]["query"], key[c]["id"]) for c in cells], seed=13)


if __name__ == "__main__":
    main()
