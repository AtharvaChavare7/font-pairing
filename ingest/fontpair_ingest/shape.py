"""Contrast, stress, and aperture from glyph outlines.

All measurements work on flattened outlines (polylines) rather than a raster,
so they are resolution-independent. Every length is normalised by units-per-em
or by the x-height so fonts with different UPMs compare directly.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from fontTools.pens.areaPen import AreaPen
from fontTools.pens.basePen import BasePen
from fontTools.pens.boundsPen import BoundsPen

# Glyphs requested from the Google Fonts CSS2 `text=` subset endpoint.
MEASURE_TEXT = "HOxonaecsplhdgkvbmrtiuIEFRqz"


class FlattenPen(BasePen):
    """Collect contours as polylines; curves are subdivided into short segments."""

    def __init__(self, glyphset: Any, steps: int = 12) -> None:
        super().__init__(glyphset)
        self.steps = steps
        self.contours: list[list[tuple[float, float]]] = []
        self._cur: list[tuple[float, float]] = []

    def _moveTo(self, pt: tuple[float, float]) -> None:
        self._cur = [pt]

    def _lineTo(self, pt: tuple[float, float]) -> None:
        self._cur.append(pt)

    def _curveToOne(self, p1, p2, p3) -> None:  # cubic
        p0 = self._cur[-1]
        for i in range(1, self.steps + 1):
            t = i / self.steps
            mt = 1 - t
            x = mt**3 * p0[0] + 3 * mt**2 * t * p1[0] + 3 * mt * t**2 * p2[0] + t**3 * p3[0]
            y = mt**3 * p0[1] + 3 * mt**2 * t * p1[1] + 3 * mt * t**2 * p2[1] + t**3 * p3[1]
            self._cur.append((x, y))

    def _qCurveToOne(self, p1, p2) -> None:  # quadratic
        p0 = self._cur[-1]
        for i in range(1, self.steps + 1):
            t = i / self.steps
            mt = 1 - t
            x = mt**2 * p0[0] + 2 * mt * t * p1[0] + t**2 * p2[0]
            y = mt**2 * p0[1] + 2 * mt * t * p1[1] + t**2 * p2[1]
            self._cur.append((x, y))

    def _closePath(self) -> None:
        if len(self._cur) > 2:
            self.contours.append(self._cur)
        self._cur = []

    _endPath = _closePath


class Glyph:
    """Flattened glyph with segment arrays for fast line intersection."""

    def __init__(self, glyphset: Any, name: str) -> None:
        g = glyphset[name]
        self.advance = float(g.width)
        fp = FlattenPen(glyphset)
        g.draw(fp)
        self.contours = fp.contours
        bp = BoundsPen(glyphset)
        g.draw(bp)
        self.bounds = bp.bounds  # (xmin, ymin, xmax, ymax) or None
        ap = AreaPen(glyphset)
        g.draw(ap)
        self.area = abs(ap.value)

        segs = []
        for c in self.contours:
            pts = np.asarray(c + [c[0]], dtype=float)
            segs.append(np.hstack([pts[:-1], pts[1:]]))
        self.segs = np.vstack(segs) if segs else np.zeros((0, 4))

    @property
    def empty(self) -> bool:
        return self.bounds is None or len(self.segs) == 0

    def hruns(self, y: float) -> list[tuple[float, float]]:
        """Filled x-intervals along the horizontal line y (nonzero winding)."""
        s = self.segs
        return _runs(s[:, 0], s[:, 1] - y, s[:, 2], s[:, 3] - y)

    def vruns(self, x: float) -> list[tuple[float, float]]:
        """Filled y-intervals along the vertical line x (nonzero winding)."""
        s = self.segs
        return _runs(s[:, 1], s[:, 0] - x, s[:, 3], s[:, 2] - x)

    def raster(self, size: int, box: tuple[float, float, float, float]) -> np.ndarray:
        """Nonzero-winding scanline fill of the outline into a size×size grid over `box`."""
        x0, y0, x1, y1 = box
        img = np.zeros((size, size), dtype=np.float32)
        xs = x0 + (np.arange(size) + 0.5) * (x1 - x0) / size
        for row in range(size):
            y = y1 - (row + 0.5) * (y1 - y0) / size
            for a, b in self.hruns(y):
                img[row, (xs >= a) & (xs < b)] = 1.0
        return img


def _runs(u0: np.ndarray, v0: np.ndarray, u1: np.ndarray, v1: np.ndarray) -> list[tuple[float, float]]:
    """
    Filled intervals along the line v = 0, for segments (u0,v0)→(u1,v1).

    Uses the nonzero winding rule, as renderers do: many variable fonts ship
    overlapping contours (a serif drawn over a stem), which even-odd pairing of
    crossings would wrongly treat as holes.
    """
    m = (np.minimum(v0, v1) <= 0) & (np.maximum(v0, v1) > 0)
    if not m.any():
        return []
    t = -v0[m] / (v1[m] - v0[m])
    u = u0[m] + t * (u1[m] - u0[m])
    d = np.sign(v1[m] - v0[m]).astype(int)
    order = np.argsort(u, kind="stable")
    runs: list[tuple[float, float]] = []
    wind, start = 0, 0.0
    for ui, di in zip(u[order], d[order]):
        prev = wind
        wind += di
        if prev == 0 and wind != 0:
            start = float(ui)
        elif prev != 0 and wind == 0:
            runs.append((start, float(ui)))
    return runs


def stem_widths(g: Glyph, y: float) -> list[float]:
    """Widths of the filled runs along the horizontal line y."""
    return [b - a for a, b in g.hruns(y)]


def _ray_runs(segs: np.ndarray, angle: float) -> list[float]:
    """Filled-run widths along a line through the origin at `angle` (radians)."""
    ca, sa = math.cos(angle), math.sin(angle)
    # rotate so the ray lies on the u axis
    u0 = segs[:, 0] * ca + segs[:, 1] * sa
    v0 = -segs[:, 0] * sa + segs[:, 1] * ca
    u1 = segs[:, 2] * ca + segs[:, 3] * sa
    v1 = -segs[:, 2] * sa + segs[:, 3] * ca
    return [b - a for a, b in _runs(u0, v0, u1, v1)]


def stroke_contrast(o: Glyph) -> tuple[float, float]:
    """
    Thin/thick ratio of the 'o' and the stress angle in degrees.

    For each candidate stress axis, measure the bowl's thin strokes along the
    axis (top/bottom for vertical stress) and the thick strokes across it
    (the sides). The axis with the thinnest hairline is the stress; contrast is
    thin/thick on that axis. 1.0 = monoline, ~0.15 = Didone; stress is ~0 for
    rational designs and 10-25° for humanist/old-style.
    """
    xmin, ymin, xmax, ymax = o.bounds
    centre = np.array([(xmin + xmax) / 2, (ymin + ymax) / 2] * 2)
    segs = o.segs - centre

    best: tuple[float, float, float] | None = None  # (thin, thick, deg)
    for deg in range(-40, 41, 4):
        a = math.radians(deg)
        across = _ray_runs(segs, a)  # sides of the bowl
        along = _ray_runs(segs, a + math.pi / 2)  # top/bottom of the bowl
        if len(across) < 2 or len(along) < 2:
            continue
        thick = (across[0] + across[-1]) / 2
        thin = (along[0] + along[-1]) / 2
        if thin > 0 and thick > 0 and (best is None or thin < best[0]):
            best = (thin, thick, float(deg))

    if best is None:
        return 1.0, 0.0
    thin, thick, deg = best
    return float(min(thin / thick, 1.0)), abs(deg)


def aperture(c: Glyph, xh: float) -> float:
    """
    Openness of the 'c': vertical gap at the right side relative to x-height.
    Wide apertures (humanist) read better at small sizes; closed (grotesque/
    Didone) feel tighter.
    """
    xmin, ymin, xmax, ymax = c.bounds
    w = xmax - xmin
    x = xmin + 0.85 * w
    runs = c.vruns(x)
    if len(runs) < 2:
        # line only hits one terminal: the gap is everything but that ink
        ink = sum(b - a for a, b in runs)
        return float(np.clip(1.0 - ink / max(xh, 1), 0, 1))
    # runs: bottom terminal, top terminal → the gap between them
    gap = runs[1][0] - runs[0][1]
    return float(np.clip(gap / max(xh, 1), 0, 1))


def roundness(o: Glyph) -> float:
    """
    How the 'o' fills its bounding box versus an ideal ellipse.
    >1 = squarish (superelliptic, e.g. Eurostile), ~1 = elliptical, <1 = pointed.
    Uses outer-contour area only.
    """
    if not o.contours:
        return 1.0
    areas = []
    for c in o.contours:
        pts = np.asarray(c)
        x, y = pts[:, 0], pts[:, 1]
        areas.append(abs(0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)))
    outer = max(areas)
    xmin, ymin, xmax, ymax = o.bounds
    ellipse = math.pi * (xmax - xmin) * (ymax - ymin) / 4
    return float(outer / ellipse) if ellipse > 0 else 1.0
