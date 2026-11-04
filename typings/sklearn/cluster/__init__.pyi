# scikit-learn ships no type annotations, so Pyright guesses `n_init: str` from its default
# of "auto". This declares the parameters as sklearn validates them at runtime. Type checking
# only: it has no effect when the code runs. Covers just the part of KMeans we use.
from typing import Any, Literal, Self

import numpy as np

class KMeans:
    cluster_centers_: np.ndarray

    def __init__(
        self,
        n_clusters: int = 8,
        *,
        init: Any = "k-means++",
        n_init: int | Literal["auto"] = "auto",
        max_iter: int = 300,
        tol: float = 1e-4,
        verbose: int = 0,
        random_state: Any = None,
        copy_x: bool = True,
        algorithm: Literal["lloyd", "elkan"] = "lloyd",
    ) -> None: ...
    def fit(self, X: Any, y: Any = None, sample_weight: Any = None) -> Self: ...
    def predict(self, X: Any) -> np.ndarray: ...
