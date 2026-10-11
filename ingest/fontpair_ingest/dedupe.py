"""Outline-hash clone detection.

Google Fonts ships metric-compatible clones (Arimo ≈ Liberation Sans, Tinos,
Cousine…) and many re-releases. Fonts whose glyph rasters are near-identical
get a shared clone_group_id so the scorer never pairs a font with its twin.
"""

from __future__ import annotations

import numpy as np

CLONE_THRESHOLD = 0.02  # mean absolute pixel difference


def clone_groups(names: list[str], sheets: np.ndarray, threshold: float = CLONE_THRESHOLD) -> list[str | None]:
    """
    Leader clustering: each unassigned font becomes a leader and absorbs every
    unassigned font within `threshold` of it. Unlike single-link union-find this
    cannot chain a whole genre (all neo-grotesques) into one group.
    """
    n = len(names)
    leader = [-1] * n
    # coarse hash: downsample to shortlist candidates, then exact compare
    coarse = sheets.reshape(n, -1, 4).mean(axis=2)
    for i in range(n):
        if leader[i] >= 0:
            continue
        leader[i] = i
        d = np.abs(coarse[i + 1 :] - coarse[i]).mean(axis=1)
        for j in np.nonzero(d < threshold * 1.5)[0] + i + 1:
            j = int(j)
            if leader[j] < 0 and np.abs(sheets[i] - sheets[j]).mean() < threshold:
                leader[j] = i

    counts: dict[int, int] = {}
    for r in leader:
        counts[r] = counts.get(r, 0) + 1
    return [names[r] if counts[r] > 1 else None for r in leader]
