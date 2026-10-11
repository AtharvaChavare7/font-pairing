"""Geometry measurements on a synthetic font with known proportions."""

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

from fontpair_ingest.features import extract_features


def _rect(pen, x0, y0, x1, y1, clockwise=True):
    pts = [(x0, y0), (x0, y1), (x1, y1), (x1, y0)]
    if not clockwise:
        pts.reverse()
    pen.moveTo(pts[0])
    for p in pts[1:]:
        pen.lineTo(p)
    pen.closePath()


def _build(tmp_path):
    upm = 1000
    glyphs = {}

    def glyph(draw):
        pen = TTGlyphPen(None)
        draw(pen)
        return pen.glyph()

    # 'o': box ring, sides 100 thick, top/bottom 50 thick → contrast 0.5
    glyphs["o"] = glyph(lambda p: (_rect(p, 50, 0, 550, 500), _rect(p, 150, 50, 450, 450, False)))
    glyphs["x"] = glyph(lambda p: _rect(p, 50, 0, 550, 500))
    glyphs["H"] = glyph(lambda p: _rect(p, 50, 0, 650, 700))
    # 'n': stem 80 wide
    glyphs["n"] = glyph(lambda p: (_rect(p, 50, 0, 130, 500), _rect(p, 400, 0, 480, 500)))
    glyphs["l"] = glyph(lambda p: _rect(p, 50, 0, 130, 750))
    glyphs[".notdef"] = glyph(lambda p: None)
    order = [".notdef", "o", "x", "H", "n", "l"]

    fb = FontBuilder(upm, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap({ord(c): c for c in "oxHnl"})
    fb.setupGlyf({k: glyphs[k] for k in order})
    fb.setupHorizontalMetrics({k: (600, 0) for k in order})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "Test", "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost()
    path = tmp_path / "test.ttf"
    fb.save(str(path))
    return path


def test_synthetic_metrics(tmp_path) -> None:
    feats, _ = extract_features(_build(tmp_path))
    assert abs(feats["x_height"] - 0.5) < 1e-6
    assert abs(feats["cap_height"] - 0.7) < 1e-6
    assert abs(feats["xh_ratio"] - 0.5 / 0.7) < 1e-6
    assert abs(feats["weight"] - 80 / 500) < 0.01
    assert abs(feats["contrast"] - 0.5) < 0.05
    assert feats["serif"] < 1.1  # straight 'l' → sans
    assert feats["mono"] < 0.05  # every advance is 600
