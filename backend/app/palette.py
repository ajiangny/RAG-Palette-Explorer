"""Palette extraction: k-means in CIELAB → dominant colors with pixel-share weights."""

import io
from pathlib import Path
from typing import TypedDict

import numpy as np
from PIL import Image
from skimage.color import lab2rgb, rgb2lab
from sklearn.cluster import KMeans

ImageInput = str | Path | bytes | Image.Image

MAX_SIDE = 200
KMEANS_SAMPLE = 10_000  # pixels used to fit k-means; all pixels are then assigned


class Swatch(TypedDict):
    lab: list[float]
    hex: str
    weight: float


def load_lab(image: ImageInput, max_side: int = MAX_SIDE) -> np.ndarray:
    """Load an image, downscale so its longest side is `max_side`, return (N, 3) LAB pixels."""
    if isinstance(image, bytes):
        image = Image.open(io.BytesIO(image))
    elif not isinstance(image, Image.Image):
        image = Image.open(image)
    image = image.convert("RGB")
    image.thumbnail((max_side, max_side))
    rgb = np.asarray(image, dtype=np.float64) / 255.0
    return rgb2lab(rgb).reshape(-1, 3)


def lab_to_hex(lab: np.ndarray) -> str:
    rgb = np.clip(lab2rgb(lab.reshape(1, 1, 3)).reshape(3), 0, 1)
    r, g, b = (int(round(c * 255)) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def extract_palette(image: ImageInput | np.ndarray, k: int = 6, seed: int = 0) -> list[Swatch]:
    """Return up to `k` colors sorted by pixel share (weights sum to 1).

    Accepts an image or precomputed (N, 3) LAB pixels from `load_lab`.
    """
    lab = image if isinstance(image, np.ndarray) else load_lab(image)
    # Can't have more clusters than distinct colors (e.g. flat graphics).
    k = min(k, len(np.unique(lab.round(2), axis=0)))

    rng = np.random.default_rng(seed)
    sample = lab if len(lab) <= KMEANS_SAMPLE else lab[rng.choice(len(lab), KMEANS_SAMPLE, replace=False)]
    km = KMeans(n_clusters=k, n_init=4, random_state=seed).fit(sample)

    labels = km.predict(lab)
    weights = np.bincount(labels, minlength=k) / len(labels)
    order = np.argsort(-weights)
    return [
        {"lab": [round(float(v), 2) for v in km.cluster_centers_[i]],
         "hex": lab_to_hex(km.cluster_centers_[i]),
         "weight": round(float(weights[i]), 4)}
        for i in order if weights[i] > 0
    ]
