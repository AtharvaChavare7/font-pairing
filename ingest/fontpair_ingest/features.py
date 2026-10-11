"""Turn one font file into a typographic fingerprint."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from fontTools.ttLib import TTFont

from fontpair_ingest.raster import glyph_sheet
from fontpair_ingest.shape import Glyph, aperture, roundness, stem_widths, stroke_contrast

FEATURE_COLUMNS = [
    "x_height",  # x-height / UPM
    "cap_height",  # cap height / UPM
    "xh_ratio",  # x-height / cap height — the single biggest pairing signal
    "ascender",  # ascender overshoot above cap height, / x-height
    "descender",  # descender depth / x-height
    "width",  # mean lowercase advance / x-height
    "o_aspect",  # 'o' width / height
    "weight",  # 'n' stem / x-height
    "color",  # ink coverage of lowercase within advance × x-height
    "contrast",  # thin/thick stroke ratio (1 = monoline)
    "stress",  # stress angle in degrees
    "aperture",  # 'c' opening / x-height
    "roundness",  # 'o' area vs inscribed ellipse
    "serif",  # foot width / stem width on 'l'
    "mono",  # advance coefficient of variation (0 = monospaced)
]

LOWER_WIDTH = "nohaesdbpu"


def _load_glyphs(font: TTFont) -> dict[str, Glyph]:
    cmap = font.getBestCmap() or {}
    gs = font.getGlyphSet()
    out: dict[str, Glyph] = {}
    for cp, name in cmap.items():
        ch = chr(cp)
        if ch.isspace():
            continue
        try:
            out[ch] = Glyph(gs, name)
        except Exception:
            continue
    return out


def _first(glyphs: dict[str, Glyph], chars: str) -> Glyph | None:
    for ch in chars:
        g = glyphs.get(ch)
        if g is not None and not g.empty:
            return g
    return None


def extract_features(path: Path) -> tuple[dict[str, float], np.ndarray | None]:
    """Return (scalar features, raster sheet) for a font file. Raises on unusable fonts."""
    with TTFont(path) as font:
        upm = float(font["head"].unitsPerEm)
        glyphs = _load_glyphs(font)

    x = _first(glyphs, "xvz")
    H = _first(glyphs, "HEIF")
    o = _first(glyphs, "o")
    n = _first(glyphs, "nmhu")
    if x is None or H is None or o is None or n is None:
        raise ValueError("missing core glyphs (x, H, o, n)")

    xh = x.bounds[3]
    cap = H.bounds[3]
    if xh <= 0 or cap <= 0:
        raise ValueError("degenerate metrics")

    asc_g = _first(glyphs, "hldkb")
    desc_g = _first(glyphs, "pgq")
    asc = (asc_g.bounds[3] - cap) / xh if asc_g else 0.0
    desc = -desc_g.bounds[1] / xh if desc_g else 0.25

    lower = [glyphs[c] for c in LOWER_WIDTH if c in glyphs and not glyphs[c].empty]
    advances = np.array([g.advance for g in lower]) if lower else np.array([n.advance])
    width = float(advances.mean() / xh)
    ink = sum(g.area for g in lower) if lower else n.area
    color = float(ink / max(advances.sum() * xh, 1))

    stems = stem_widths(n, 0.45 * xh)
    weight = float((stems[0] if stems else 0.1 * xh) / xh)

    ox0, oy0, ox1, oy1 = o.bounds
    contrast, stress = stroke_contrast(o)
    c = _first(glyphs, "ce")
    ap = aperture(c, xh) if c else 0.3

    l_g = _first(glyphs, "lIi")
    if l_g is not None:
        l_top = l_g.bounds[3]
        mid = stem_widths(l_g, 0.5 * l_top)
        foot = stem_widths(l_g, 0.025 * cap)
        serif = float(max(foot) / max(min(mid), 1e-6)) if mid and foot else 1.0
    else:
        serif = 1.0

    mono_set = [glyphs[ch].advance for ch in "ilmnoH" if ch in glyphs]
    mono = float(np.std(mono_set) / max(np.mean(mono_set), 1)) if len(mono_set) > 2 else 0.5

    feats = {
        "x_height": xh / upm,
        "cap_height": cap / upm,
        "xh_ratio": xh / cap,
        "ascender": float(asc),
        "descender": float(desc),
        "width": width,
        "o_aspect": float((ox1 - ox0) / max(oy1 - oy0, 1)),
        "weight": weight,
        "color": color,
        "contrast": contrast,
        "stress": stress,
        "aperture": ap,
        "roundness": roundness(o),
        "serif": min(serif, 6.0),
        "mono": mono,
    }
    sheet = glyph_sheet(glyphs, cap)
    return feats, sheet


def feature_row(path: Path) -> dict[str, Any]:
    feats, sheet = extract_features(path)
    return {**feats, "_sheet": sheet}
