"""Pairing engine.

A good pairing has *concordant structure* and *contrasting voice*:

  score = harmony^α · contrast_fit^β · legibility(body) · character(heading)^½
          · familiarity^γ · valley · kinship

harmony       proportions agree — x-height/cap ratio, letter width, bowl
              shape and aperture — so the two faces share a rhythm.
contrast_fit  how close the pair's *style distance* lands to the requested
              target (0 = quiet, near-family pairing; 1 = dramatic contrast).
              Style distance mixes classification, measured serifs, stroke
              contrast, typographic colour and glyph-shape embedding distance.
legibility    the body face must survive paragraphs (see corpus._body_fitness).
familiarity   a prior on Google Fonts popularity rank, centred where the
              familiar ↔ undiscovered slider points.
valley        the "uncanny valley": two faces of the same genre that look
              almost — but not quite — alike read as a mistake. Penalised
              unless they are a designed superfamily.
kinship       designed companions (Source Serif/Sans, IBM Plex, PT, Alegreya…)
              get a bonus.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from pydantic import BaseModel, Field

from corpus import DNA_METRICS, Corpus, get_corpus
from filters import FilterParams, build_mask

CLASS_DIST = {
    frozenset(["serif", "sans"]): 1.0,
    frozenset(["serif", "display"]): 0.7,
    frozenset(["sans", "display"]): 0.7,
    frozenset(["serif", "mono"]): 0.85,
    frozenset(["sans", "mono"]): 0.55,
    frozenset(["display", "mono"]): 0.75,
    frozenset(["display"]): 0.45,
    frozenset(["handwriting"]): 0.4,
}
CATS = ["serif", "sans", "display", "handwriting", "mono"]

# Harmony tolerances (one "sigma" of acceptable difference) and weights.
# Tuned coarsely against seeds/known_pairings.csv — see evaluate.py.
XH_TOL, XH_W = 0.06, 2.0  # x-height / cap-height
WIDTH_TOL, WIDTH_W = 0.20, 1.0  # log ratio of mean lowercase width
ASPECT_TOL, ASPECT_W = 0.12, 0.8  # 'o' width / height
APERTURE_TOL, APERTURE_W = 0.18, 0.5
CONTRAST_SIGMA = 0.22  # how tightly style distance must hit the target


def _class_matrix() -> np.ndarray:
    m = np.zeros((len(CATS), len(CATS)))
    for i, a in enumerate(CATS):
        for j, b in enumerate(CATS):
            if a == b:
                m[i, j] = CLASS_DIST.get(frozenset([a]), 0.0)
            elif "handwriting" in (a, b):
                m[i, j] = 0.9
            else:
                m[i, j] = CLASS_DIST[frozenset([a, b])]
    return m


CLASS_M = _class_matrix()


class PairRequest(BaseModel):
    target_dist: float = Field(default=0.5, ge=0.0, le=1.0)
    discovery: float = Field(default=0.3, ge=0.0, le=1.0)
    variety: float = Field(default=0.35, ge=0.0, le=1.0)
    anchor_id: str | None = None
    anchor_role: Literal["heading", "body", "either"] = "either"
    n: int = Field(default=10, ge=1, le=50)
    seed: int | None = None
    filters: FilterParams = Field(default_factory=FilterParams)


class FontInfo(BaseModel):
    id: str
    name: str
    category: str
    designers: list[str]
    weights: list[int]
    styles: list[str]  # Google Fonts style keys: "400", "400i", "700"…
    has_italic: bool
    is_variable: bool
    popularity: int
    x_height: float
    dna: dict[str, float]  # corpus percentile per DNA metric


class PairResult(BaseModel):
    heading: FontInfo
    body: FontInfo
    score: float
    breakdown: dict[str, float]
    reasons: list[str]
    notes: list[str]
    size_adjust: float  # body font-size multiplier that optically matches x-heights


class PairResponse(BaseModel):
    seed: int
    corpus_size: int
    results: list[PairResult]


def font_info(c: Corpus, i: int) -> FontInfo:
    r = c.df.iloc[i]
    return FontInfo(
        id=r["slug"],
        name=r["name"],
        category=c.cat[i],
        designers=list(r["designers"]),
        weights=[int(w) for w in r["weights"]],
        styles=list(r["styles"]),
        has_italic=bool(r["has_italic"]),
        is_variable=bool(r["is_variable"]),
        popularity=int(r["popularity"]),
        x_height=float(r["x_height"]),
        dna={m: round(float(c.pct.at[i, m]), 3) for m in DNA_METRICS},
    )


def shared_designer(c: Corpus, h: int, b: int) -> bool:
    return bool(set(c.df.at[h, "designers"]) & set(c.df.at[b, "designers"]))


def _col(c: Corpus, name: str, idx: np.ndarray) -> np.ndarray:
    return c.df[name].to_numpy(dtype=float)[idx]


def score_matrix(c: Corpus, H: np.ndarray, B: np.ndarray, req: PairRequest) -> dict[str, np.ndarray]:
    """All component scores for every heading (rows) × body (cols) combination."""

    def pair(name: str) -> tuple[np.ndarray, np.ndarray]:
        return _col(c, name, H)[:, None], _col(c, name, B)[None, :]

    # --- harmony: proportions in agreement --------------------------------
    xh_h, xh_b = pair("xh_ratio")
    w_h, w_b = pair("width")
    oa_h, oa_b = pair("o_aspect")
    ap_h, ap_b = pair("aperture")
    d2 = (
        XH_W * ((xh_h - xh_b) / XH_TOL) ** 2
        + WIDTH_W * (np.log(w_h / w_b) / WIDTH_TOL) ** 2
        + ASPECT_W * ((oa_h - oa_b) / ASPECT_TOL) ** 2
        + APERTURE_W * ((ap_h - ap_b) / APERTURE_TOL) ** 2
    ) / (XH_W + WIDTH_W + ASPECT_W + APERTURE_W)
    harmony = np.exp(-d2 / 2)
    # Display/script headings are set large; proportion matching matters less.
    expressive = np.isin(c.cat[H], ["display", "handwriting"])[:, None]
    harmony_eff = np.where(expressive, np.sqrt(harmony), harmony)

    # --- style distance ---------------------------------------------------
    ci_h = np.array([CATS.index(x) for x in c.cat[H]])
    ci_b = np.array([CATS.index(x) for x in c.cat[B]])
    class_d = CLASS_M[ci_h][:, ci_b]
    s_h, s_b = pair("serif")
    serif_d = np.abs(np.clip((s_h - 1.15), 0, 1) - np.clip((s_b - 1.15), 0, 1))
    k_h, k_b = pair("contrast")
    contrast_d = np.clip(np.abs(k_h - k_b) / 0.6, 0, 1)
    col_h, col_b = pair("color")
    color_d = np.clip(np.abs(col_h - col_b) / 0.3, 0, 1)
    eh, eb = c.emb[H], c.emb[B]
    raw = np.sqrt(np.maximum((eh**2).sum(1)[:, None] + (eb**2).sum(1)[None, :] - 2 * eh @ eb.T, 0))
    emb_d = c.dist_pct(raw)
    style = 0.35 * class_d + 0.15 * serif_d + 0.15 * contrast_d + 0.25 * emb_d + 0.10 * color_d
    contrast_fit = np.exp(-((style - req.target_dist) ** 2) / (2 * CONTRAST_SIGMA**2))

    # --- priors -----------------------------------------------------------
    centre = 0.12 + 0.75 * req.discovery
    fam = np.exp(-((c.pop_rank - centre) ** 2) / (2 * 0.28**2))
    familiarity = np.sqrt(fam[H][:, None] * fam[B][None, :])

    legibility = np.broadcast_to(c.body_fit[B][None, :], harmony.shape)
    character = np.broadcast_to(c.head_fit[H][:, None], harmony.shape)

    # --- relationships ----------------------------------------------------
    same_root = c.root[H][:, None] == c.root[B][None, :]
    # "Red Rose" and "Red Hat" share a prefix but aren't a superfamily: also
    # require a shared designer or both names following "<root> Sans/Serif…".
    for i, j in zip(*np.nonzero(same_root)):
        h, b = H[i], B[j]
        if not (c.styled_name[h] and c.styled_name[b]) and not shared_designer(c, h, b):
            same_root[i, j] = False
    same_cat = ci_h[:, None] == ci_b[None, :]
    valley = np.where(same_cat & (emb_d < 0.22) & ~same_root, 0.4, 1.0)
    kin = np.where(same_root & ~same_cat, 1.25, 1.0)
    same_group = c.group[H][:, None] == c.group[B][None, :]
    identical = H[:, None] == B[None, :]
    allowed = ~(same_group | identical)

    total = (
        harmony_eff**0.9
        * contrast_fit**1.2
        * legibility
        * np.sqrt(character)
        * familiarity**0.6
        * valley
        * kin
        * allowed
    )
    return {
        "total": total,
        "harmony": harmony,
        "style": style,
        "contrast_fit": contrast_fit,
        "legibility": legibility,
        "familiarity": familiarity,
        "emb_d": emb_d,
        "kin": kin,
        "valley": valley,
    }


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def explain(c: Corpus, h: int, b: int, comp: dict[str, float]) -> tuple[list[str], list[str]]:
    """Plain-language reasons (and caveats) derived from the measured geometry."""
    df = c.df
    H, B = df.iloc[h], df.iloc[b]
    reasons: list[str] = []
    notes: list[str] = []
    ch, cb = c.cat[h], c.cat[b]

    if comp["kin"] > 1:
        reasons.append(f"Designed companions — {H['name']} and {B['name']} come from the same superfamily.")
    elif set(H["designers"]) & set(B["designers"]):
        who = sorted(set(H["designers"]) & set(B["designers"]))[0]
        reasons.append(f"Same designer ({who}) — shared drawing habits keep them on speaking terms.")

    if {ch, cb} == {"serif", "sans"}:
        lead = "Serif heading over sans text" if ch == "serif" else "Sans heading over serif text"
        reasons.append(f"{lead}: clear hierarchy from structure alone, the classic contrast.")
    elif ch in ("display", "handwriting"):
        reasons.append(f"{H['name']} carries the personality; {B['name']} stays out of the way in paragraphs.")
    elif ch == cb == "sans" and comp["style"] < 0.35:
        reasons.append("Two sans faces with related skeletons — a calm, near-monochrome system.")

    dxh = abs(H["xh_ratio"] - B["xh_ratio"])
    if dxh < 0.03:
        reasons.append(
            f"x-heights match ({_pct(H['xh_ratio'])} vs {_pct(B['xh_ratio'])} of cap height), "
            "so lowercase sits at the same optical size."
        )
    elif dxh > 0.08:
        notes.append(
            f"x-heights differ ({_pct(H['xh_ratio'])} vs {_pct(B['xh_ratio'])}); "
            "lean on size, not weight, to separate levels."
        )

    if abs(np.log(H["width"] / B["width"])) < 0.07:
        reasons.append("Near-identical letter widths keep line length and rhythm consistent.")

    kh, kb = H["contrast"], B["contrast"]
    if kh < 0.3 and kb > 0.6:
        reasons.append(
            f"High-contrast strokes up top (thin/thick {kh:.2f}) against a near-monoline body ({kb:.2f}) "
            "— elegance where it's big, sturdiness where it's small."
        )
    elif abs(kh - kb) < 0.1 and ch != cb:
        reasons.append("Matching stroke contrast lets two different classifications share the same texture.")

    if H["stress"] >= 8 and B["stress"] >= 8:
        reasons.append("Both carry a diagonal, pen-derived stress — shared humanist DNA.")
    if H["aperture"] > 0.42 and B["aperture"] > 0.42:
        reasons.append("Both have open apertures, which reads friendly and stays legible small.")
    elif H["aperture"] < 0.3 and B["aperture"] < 0.3:
        reasons.append("Both have tight apertures — a compact, engineered feel throughout.")

    if B["has_bold"] and B["has_italic"]:
        reasons.append(f"{B['name']} ships bold and italic, so real body copy (emphasis, links) works.")
    else:
        notes.append(f"{B['name']} lacks {'italic' if B['has_bold'] else 'bold'} — emphasis will be synthesized.")

    if comp["valley"] < 1:
        notes.append("These are close cousins; make the size jump between levels decisive.")
    if c.body_fit[b] < 0.5:
        notes.append(f"{B['name']} is best kept to short passages, not long reading.")

    return reasons[:5], notes[:3]


def _sample(total: np.ndarray, n: int, rng: np.random.Generator, variety: float, max_h: int, max_b: int):
    """Gumbel-perturbed greedy pick with per-font caps for a diverse, seeded result set."""
    flat = total.ravel()
    k = min(len(flat), max(400, n * 40))
    top = np.argpartition(-flat, k - 1)[:k]
    top = top[flat[top] > 0]
    logits = np.log(flat[top] + 1e-9)
    if variety > 0:
        logits = logits + variety * 0.5 * rng.gumbel(size=len(top))
    order = top[np.argsort(-logits)]
    used_h: dict[int, int] = {}
    used_b: dict[int, int] = {}
    picks: list[tuple[int, int]] = []
    rows = total.shape[1]
    for f in order:
        i, j = divmod(int(f), rows)
        if used_h.get(i, 0) >= max_h or used_b.get(j, 0) >= max_b:
            continue
        used_h[i] = used_h.get(i, 0) + 1
        used_b[j] = used_b.get(j, 0) + 1
        picks.append((i, j))
        if len(picks) == n:
            break
    return picks


def score_pairs(request: PairRequest) -> PairResponse:
    """Score and sample font pairs."""
    seed = request.seed if request.seed is not None else int(np.random.default_rng().integers(0, 2**31))
    c = get_corpus()
    if c is None:
        return PairResponse(seed=seed, corpus_size=0, results=[])

    rng = np.random.default_rng(seed)
    head_mask, body_mask = build_mask(c, request.filters)
    all_idx = np.arange(len(c))

    plans: list[tuple[np.ndarray, np.ndarray]] = []
    anchor = c.index.get(request.anchor_id) if request.anchor_id else None
    if anchor is not None:
        others_h, others_b = all_idx[head_mask], all_idx[body_mask & (c.body_fit > 0.25)]
        if request.anchor_role in ("heading", "either"):
            plans.append((np.array([anchor]), others_b))
        if request.anchor_role in ("body", "either"):
            plans.append((others_h, np.array([anchor])))
    else:
        plans.append((all_idx[head_mask], all_idx[body_mask & (c.body_fit > 0.25)]))

    candidates: list[tuple[float, int, int, dict[str, float]]] = []
    for H, B in plans:
        if len(H) == 0 or len(B) == 0:
            continue
        comp = score_matrix(c, H, B, request)
        caps = (request.n, 1) if len(H) == 1 else (1, request.n) if len(B) == 1 else (1, 2)
        for i, j in _sample(comp["total"], request.n, rng, request.variety, *caps):
            parts = {k: float(v[i, j]) for k, v in comp.items()}
            candidates.append((parts["total"], int(H[i]), int(B[j]), parts))

    candidates.sort(key=lambda t: -t[0])
    seen: set[frozenset[int]] = set()
    results: list[PairResult] = []
    for total, h, b, parts in candidates:
        # the same two fonts with roles swapped would just repeat the specimen
        if frozenset((h, b)) in seen:
            continue
        seen.add(frozenset((h, b)))
        reasons, notes = explain(c, h, b, parts)
        xh_h, xh_b = c.df.at[h, "x_height"], c.df.at[b, "x_height"]
        results.append(
            PairResult(
                heading=font_info(c, h),
                body=font_info(c, b),
                score=round(min(total, 1.0) * 100, 1),
                breakdown={
                    "harmony": round(parts["harmony"], 3),
                    "contrast": round(parts["style"], 3),
                    "contrast_fit": round(parts["contrast_fit"], 3),
                    "legibility": round(parts["legibility"], 3),
                    "familiarity": round(parts["familiarity"], 3),
                },
                reasons=reasons,
                notes=notes,
                size_adjust=round(float(xh_h / xh_b), 3),
            )
        )
        if len(results) == request.n:
            break
    return PairResponse(seed=seed, corpus_size=len(c), results=results)
