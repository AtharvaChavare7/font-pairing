"""Score known-good pairings against the corpus.

For every (heading, body) row in seeds/known_pairings.csv, compute where the
known body ranks among all text-capable bodies for that heading. A percentile
of 0.95 means the engine prefers it over 95% of the alternatives.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from corpus import Corpus, load_corpus
from scoring import PairRequest, score_matrix

SEEDS = Path(__file__).resolve().parents[1] / "seeds" / "known_pairings.csv"


def known_pair_percentiles(c: Corpus, path: Path = SEEDS) -> list[tuple[str, str, float]]:
    by_name = {n: i for i, n in enumerate(c.df["name"])}
    bodies = np.nonzero(c.body_fit > 0.25)[0]
    req = PairRequest(target_dist=0.5, discovery=0.3, variety=0)
    out = []
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            h, b = by_name.get(row["heading_family"]), by_name.get(row["body_family"])
            if h is None or b is None or b not in set(bodies):
                continue
            total = score_matrix(c, np.array([h]), bodies, req)["total"][0]
            mine = total[np.searchsorted(bodies, b)]
            out.append((row["heading_family"], row["body_family"], float((total < mine).mean())))
    return out


if __name__ == "__main__":
    corpus = load_corpus()
    rows = known_pair_percentiles(corpus)
    for h, b, p in sorted(rows, key=lambda r: r[2]):
        print(f"{p:6.1%}  {h} + {b}")
    print(f"\nmean percentile {np.mean([r[2] for r in rows]):.1%} over {len(rows)} known pairings")
