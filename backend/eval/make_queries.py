"""Generate the automatic test set: crops and photo-like versions of collection paintings.

Usage (from backend/):
    python -m eval.make_queries

Each query's ground truth is the painting it came from. Paintings are split 50/50 into
dev (for tuning) and test (for reporting). Seeded, so the images can be regenerated
exactly; eval/testset.json is committed, the images (data/eval_queries/) are not.
"""

import io
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance

from eval.featurize import corpus
from ingest.aic import BACKEND_DIR, image_cache_dir

SEED = 7
N_PAINTINGS = 100
QUERY_DIR = BACKEND_DIR / "data" / "eval_queries"
TESTSET = Path(__file__).with_name("testset.json")


def random_crop(img: Image.Image, rng: np.random.Generator, area: tuple[float, float]) -> Image.Image:
    """Crop a random window covering `area` (fraction range) of the image, aspect ratio 0.75–1.33."""
    w, h = img.size
    frac = rng.uniform(*area)
    aspect = rng.uniform(0.75, 1.33)
    cw = min(w, int(round(np.sqrt(frac * w * h * aspect))))
    ch = min(h, int(round(frac * w * h / cw)))
    x = int(rng.integers(0, w - cw + 1))
    y = int(rng.integers(0, h - ch + 1))
    return img.crop((x, y, x + cw, y + ch))


def photo_like(img: Image.Image, rng: np.random.Generator) -> Image.Image:
    """Simulate a phone photo of the painting: tighter crop, exposure/saturation/hue drift, JPEG."""
    img = random_crop(img, rng, (0.7, 0.9))
    img = ImageEnhance.Brightness(img).enhance(rng.uniform(0.85, 1.15))
    img = ImageEnhance.Color(img).enhance(rng.uniform(0.8, 1.2))
    hsv = np.asarray(img.convert("HSV")).copy()
    hsv[..., 0] = (hsv[..., 0].astype(int) + int(rng.integers(-4, 5))) % 256  # ±~5° hue
    img = Image.fromarray(hsv, "HSV").convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=35)
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")


def main() -> None:
    rng = np.random.default_rng(SEED)
    rows = corpus()
    picked = [rows[i] for i in rng.choice(len(rows), N_PAINTINGS, replace=False)]
    cache = image_cache_dir()
    QUERY_DIR.mkdir(parents=True, exist_ok=True)
    testset = []
    for n, art in enumerate(picked):
        split = "dev" if n < N_PAINTINGS // 2 else "test"
        src = Image.open(cache / f"{art['image_id']}.jpg").convert("RGB")
        for kind, make in [("crop", lambda im: random_crop(im, rng, (0.4, 0.7))),
                           ("photo", lambda im: photo_like(im, rng))]:
            name = f"{kind}_{art['id']}.jpg"
            make(src).save(QUERY_DIR / name, quality=92)
            testset.append({"query": name, "kind": kind, "split": split,
                            "source_id": art["id"], "source_title": art["title"]})
    TESTSET.write_text(json.dumps(testset, indent=1, ensure_ascii=False) + "\n")
    print(f"{len(testset)} queries from {N_PAINTINGS} paintings → {QUERY_DIR}, {TESTSET.name}")


if __name__ == "__main__":
    main()
