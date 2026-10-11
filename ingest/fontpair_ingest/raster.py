"""Glyph rasterization."""

from __future__ import annotations

import numpy as np

from fontpair_ingest.shape import Glyph

# Glyphs whose silhouettes form the visual-similarity embedding. Chosen to
# cover bowls (o, e), terminals (a, g, s), diagonals (k, R) and a cap (H).
SHEET_GLYPHS = "aegnosRkH"
CELL = 28


def glyph_sheet(glyphs: dict[str, Glyph], cap: float) -> np.ndarray | None:
    """
    Rasterize SHEET_GLYPHS into fixed cells normalised by cap height, so the
    vector captures shape, not size. Returns a flat float32 vector or None
    if any glyph is missing.
    """
    cells = []
    for ch in SHEET_GLYPHS:
        g = glyphs.get(ch)
        if g is None or g.empty:
            return None
        xmin, _, xmax, _ = g.bounds
        cx = (xmin + xmax) / 2
        half = 0.72 * cap
        box = (cx - half, -0.36 * cap, cx + half, 1.08 * cap)
        cells.append(g.raster(CELL, box))
    return np.concatenate([c.ravel() for c in cells]).astype(np.float32)
