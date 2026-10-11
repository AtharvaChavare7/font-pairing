"""Load the feature-store snapshot into numpy.

The ingest pipeline writes api/data/families.json + embeddings.npy. They live
inside the API package so a deployed API (e.g. a Vercel service rooted at api/)
ships its own data, and reading JSON avoids a ~90 MB pyarrow dependency.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

SNAPSHOT_DIR = Path(__file__).resolve().parent / "data"
FAMILIES_JSON = SNAPSHOT_DIR / "families.json"
EMBED_NPY = SNAPSHOT_DIR / "embeddings.npy"

# Metrics shown on the "typographic DNA" strip in the UI.
DNA_METRICS = ["xh_ratio", "width", "weight", "contrast", "aperture", "serif"]

CATEGORY_KEYS = {
    "Serif": "serif",
    "Sans Serif": "sans",
    "Display": "display",
    "Handwriting": "handwriting",
    "Monospace": "mono",
}


@dataclass
class Corpus:
    df: pd.DataFrame
    emb: np.ndarray  # n × d whitened PCA embedding
    index: dict[str, int]  # slug → row
    dist_cdf: np.ndarray  # sorted sample of pairwise embedding distances
    pop_rank: np.ndarray  # 0 (most popular) … 1 (least), log-scaled
    body_fit: np.ndarray  # 0…1 suitability as running text
    head_fit: np.ndarray  # 0…1 suitability as a heading
    cat: np.ndarray  # category keys
    group: np.ndarray  # clone group (or own slug)
    root: np.ndarray  # superfamily root token
    styled_name: np.ndarray  # name is "<root> Sans/Serif/Slab/…"
    pct: pd.DataFrame  # corpus percentile (0…1) of each DNA metric

    def __len__(self) -> int:
        return len(self.df)

    def dist_pct(self, d: np.ndarray) -> np.ndarray:
        """Map raw embedding distances to their corpus percentile (0…1)."""
        return np.searchsorted(self.dist_cdf, d) / len(self.dist_cdf)


_corpus: Corpus | None = None
_attempted = False


def _smooth(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    t = np.clip((x - lo) / (hi - lo), 0, 1)
    return t * t * (3 - 2 * t)


def _body_fitness(df: pd.DataFrame, cat: np.ndarray) -> np.ndarray:
    """
    How well a family survives 16px paragraphs. Category sets the ceiling;
    measured geometry then penalises hairline contrast, tiny x-heights,
    extreme widths, very light/heavy stems and missing bold/italic.
    """
    base = np.select(
        [cat == "sans", cat == "serif", cat == "mono", cat == "display", cat == "handwriting"],
        [1.0, 1.0, 0.55, 0.18, 0.04],
        0.3,
    )
    contrast = 0.35 + 0.65 * _smooth(df["contrast"].to_numpy(), 0.12, 0.34)
    xh = 0.55 + 0.45 * _smooth(df["xh_ratio"].to_numpy(), 0.56, 0.66)
    w = df["width"].to_numpy()
    width = 1 - 0.6 * (_smooth(-w, -0.95, -0.78) + _smooth(w, 1.38, 1.6))
    st = df["weight"].to_numpy()
    weight = 1 - 0.7 * (_smooth(-st, -0.10, -0.07) + _smooth(st, 0.24, 0.32))
    styles = np.where(df["has_bold"] & df["has_italic"], 1.0, np.where(df["has_bold"] | df["has_italic"], 0.85, 0.7))
    ap = 0.85 + 0.15 * _smooth(df["aperture"].to_numpy(), 0.15, 0.4)
    return np.clip(base * contrast * xh * width * weight * styles * ap, 0, 1)


def _heading_fitness(df: pd.DataFrame, cat: np.ndarray) -> np.ndarray:
    """
    Headings tolerate almost anything. Expressive faces pay a small "risk" cost
    so they win on fit rather than by default; hairlines and monospace too.
    """
    st = df["weight"].to_numpy()
    light = 0.75 + 0.25 * _smooth(st, 0.05, 0.1)
    voice = np.select([cat == "display", cat == "handwriting", cat == "mono"], [0.8, 0.65, 0.8], 1.0)
    return light * voice


_GENERIC = {"noto", "libre", "the", "big", "sans", "serif", "mono", "pt", "ibm", "dm", "zen", "m", "sometype"}


def _root_token(name: str) -> str:
    """Superfamily key: 'Source Serif 4' → 'source', 'IBM Plex Sans' → 'ibm plex'."""
    toks = name.lower().split()
    if not toks:
        return name
    if toks[0] in _GENERIC and len(toks) > 1 and toks[1] not in ("sans", "serif", "mono"):
        return " ".join(toks[:2])
    return toks[0]


_STYLE_WORDS = {"sans", "serif", "slab", "mono", "display", "text", "caption", "code", "grotesk", "round", "condensed"}


def _styled_name(name: str, root: str) -> bool:
    rest = name.lower()[len(root) :].split()
    return not rest or any(w in _STYLE_WORDS for w in rest)


def load_corpus(path: Path = FAMILIES_JSON, emb_path: Path = EMBED_NPY) -> Corpus | None:
    """Load the snapshot from api/data/ if available."""
    global _corpus, _attempted
    _attempted = True
    if not path.is_file() or not emb_path.is_file():
        _corpus = None
        return None

    df = pd.read_json(path, orient="records").reset_index(drop=True)
    df["clone_group_id"] = df["clone_group_id"].where(df["clone_group_id"].notna(), None)
    emb = np.load(emb_path)
    cat = df["category"].map(CATEGORY_KEYS).fillna("display").to_numpy()

    rng = np.random.default_rng(0)
    n = len(df)
    a, b = rng.integers(0, n, 40_000), rng.integers(0, n, 40_000)
    keep = a != b
    sample = np.sort(np.linalg.norm(emb[a[keep]] - emb[b[keep]], axis=1))

    pop = df["popularity"].to_numpy(dtype=float)
    pop_rank = np.log(np.clip(pop, 1, None)) / math.log(max(pop.max(), 2))

    group = df["clone_group_id"].fillna(df["name"]).to_numpy()
    root = np.array([_root_token(nm) for nm in df["name"]])

    _corpus = Corpus(
        df=df,
        emb=emb,
        index={s: i for i, s in enumerate(df["slug"])},
        dist_cdf=sample,
        pop_rank=pop_rank,
        body_fit=_body_fitness(df, cat),
        head_fit=_heading_fitness(df, cat),
        cat=cat,
        group=group,
        root=root,
        pct=df[DNA_METRICS].rank(pct=True),
        styled_name=np.array([_styled_name(nm, r) for nm, r in zip(df["name"], root)]),
    )
    return _corpus


def get_corpus() -> Corpus | None:
    # lazy: serverless runtimes may not run ASGI startup events
    if _corpus is None and not _attempted:
        load_corpus()
    return _corpus


def is_loaded() -> bool:
    return _corpus is not None
