"""Fixed-length color feature vector for stage-1 ANN retrieval (pgvector)."""

from dataclasses import dataclass

import numpy as np

from app.palette import ImageInput, load_lab


@dataclass(frozen=True)
class HistConfig:
    """Bin layout for the LAB histogram. Tuned by eval; dim must match the `hist` column."""
    bins: tuple[int, int, int] = (8, 8, 8)  # L, a, b
    # a/b are clipped to this range; sRGB colors fall almost entirely inside it.
    ab_range: float = 100.0
    hellinger: bool = True  # sqrt after L1-normalizing, so cosine ≈ Bhattacharyya

    @property
    def dim(self) -> int:
        return int(np.prod(self.bins))


DEFAULT_CONFIG = HistConfig()


def lab_histogram(lab: np.ndarray, config: HistConfig = DEFAULT_CONFIG) -> np.ndarray:
    """(N, 3) LAB pixels → flattened, normalized histogram of length `config.dim`."""
    r = config.ab_range
    pixels = np.column_stack([
        np.clip(lab[:, 0], 0, 100),
        np.clip(lab[:, 1], -r, r),
        np.clip(lab[:, 2], -r, r),
    ])
    hist, _ = np.histogramdd(pixels, bins=config.bins, range=[(0, 100), (-r, r), (-r, r)])
    hist = hist.ravel()
    hist /= hist.sum()
    if config.hellinger:
        hist = np.sqrt(hist)
    return hist.astype(np.float32)


def image_histogram(image: ImageInput, config: HistConfig = DEFAULT_CONFIG) -> np.ndarray:
    return lab_histogram(load_lab(image), config)
