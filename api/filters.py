"""Hard constraint filters applied before scoring."""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel, Field

from corpus import Corpus

OVERUSED_RANK = 25  # Roboto, Open Sans, Montserrat, Lato, Poppins…


class FilterParams(BaseModel):
    script_latin: bool = True
    exclude_overused: bool = False
    require_variable: bool = False
    heading_categories: list[str] = Field(default_factory=list)  # serif|sans|display|handwriting|mono
    body_categories: list[str] = Field(default_factory=list)
    exclude_ids: list[str] = Field(default_factory=list)


def _cats(corpus: Corpus, wanted: list[str]) -> np.ndarray:
    if not wanted:
        return np.ones(len(corpus), dtype=bool)
    return np.isin(corpus.cat, wanted)


def build_mask(corpus: Corpus, params: FilterParams) -> tuple[np.ndarray, np.ndarray]:
    """Boolean masks of families allowed as (heading, body)."""
    df = corpus.df
    base = np.ones(len(corpus), dtype=bool)
    if params.script_latin:
        base &= df["subsets"].apply(lambda s: "latin" in s).to_numpy()
    if params.exclude_overused:
        base &= df["popularity"].to_numpy() > OVERUSED_RANK
    if params.require_variable:
        base &= df["is_variable"].to_numpy()
    if params.exclude_ids:
        base &= ~df["slug"].isin(params.exclude_ids).to_numpy()
    # only the leader of each clone group is offered as a candidate
    leaders = (df["clone_group_id"].isna() | (df["clone_group_id"] == df["name"])).to_numpy()
    base &= leaders
    return base & _cats(corpus, params.heading_categories), base & _cats(corpus, params.body_categories)
