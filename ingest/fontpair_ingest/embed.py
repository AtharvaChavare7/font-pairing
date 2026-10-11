"""PCA embedding over normalized glyph rasters."""

from __future__ import annotations

import numpy as np

EMBED_DIMS = 24


def pca_embed(sheets: np.ndarray, dims: int = EMBED_DIMS) -> tuple[np.ndarray, np.ndarray]:
    """
    Project raster sheets (n × pixels) onto their top principal components via
    SVD. Returns (embeddings n × dims, explained-variance ratios). Embeddings
    are whitened so every component contributes equally to distances.
    """
    x = sheets.astype(np.float64)
    x -= x.mean(axis=0, keepdims=True)
    u, s, _ = np.linalg.svd(x, full_matrices=False)
    var = s**2
    ratio = var[:dims] / var.sum()
    emb = u[:, :dims] * np.sqrt(len(x))  # whitened scores
    return emb.astype(np.float32), ratio
