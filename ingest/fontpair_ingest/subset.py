"""Fetch tiny measurement subsets from the Google Fonts CSS2 API.

Instead of cloning the multi-GB google/fonts repo, request each family's
regular face with `text=` so Google returns a TTF containing only the glyphs
we measure (~5 KB per family).
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

import httpx
import typer

from fontpair_ingest.config import GF_METADATA_JSON, GF_METADATA_URL, SUBSET_DIR
from fontpair_ingest.shape import MEASURE_TEXT

CSS2 = "https://fonts.googleapis.com/css2"
# A non-browser UA makes the CSS2 API answer with TrueType URLs.
UA = {"User-Agent": "fontpair-ingest/0.1"}
_URL = re.compile(r"url\((https://[^)]+)\)")


def slug(family: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", family.lower()).strip("-")


def fetch_metadata(force: bool = False) -> list[dict[str, Any]]:
    """Download (or load cached) Google Fonts family metadata."""
    if not GF_METADATA_JSON.is_file() or force:
        GF_METADATA_JSON.parent.mkdir(parents=True, exist_ok=True)
        typer.echo(f"Fetching {GF_METADATA_URL}")
        resp = httpx.get(GF_METADATA_URL, headers=UA, timeout=60, follow_redirects=True)
        resp.raise_for_status()
        GF_METADATA_JSON.write_text(resp.text, encoding="utf-8")
    text = GF_METADATA_JSON.read_text(encoding="utf-8")
    text = text[text.index("{") :]  # strip XSSI guard if present
    return json.loads(text)["familyMetadataList"]


def eligible(meta: dict[str, Any]) -> bool:
    """Latin-capable text families; skip colour/emoji, symbol and script-specific Noto."""
    if "latin" not in meta.get("subsets", []):
        return False
    if meta.get("colorCapabilities"):
        return False
    if "Symbols" in meta.get("classifications", []):
        return False
    if meta.get("primaryScript") and meta.get("isNoto"):
        return False  # Noto Sans <Script> repeats Noto Sans' Latin
    return True


def regular_weight(meta: dict[str, Any]) -> int:
    """Pick the upright face closest to 400."""
    uprights = [int(v) for v in meta.get("fonts", {}) if v.isdigit()]
    if not uprights:
        return 400
    return min(uprights, key=lambda w: (abs(w - 400), w))


def css2_query(meta: dict[str, Any], text: str) -> dict[str, str]:
    if not any(v.isdigit() for v in meta.get("fonts", {})):
        italics = [int(v[:-1]) for v in meta.get("fonts", {}) if v[:-1].isdigit()]
        w = min(italics or [400], key=lambda w: abs(w - 400))
        return {"family": f"{meta['family']}:ital,wght@1,{w}", "text": text}
    w = regular_weight(meta)
    fam = meta["family"] if w == 400 else f"{meta['family']}:wght@{w}"
    return {"family": fam, "text": text}


async def _fetch_one(client: httpx.AsyncClient, meta: dict[str, Any], sem: asyncio.Semaphore) -> str | None:
    out = SUBSET_DIR / f"{slug(meta['family'])}.ttf"
    if out.is_file() and out.stat().st_size > 0:
        return None
    async with sem:
        try:
            css = await client.get(CSS2, params=css2_query(meta, MEASURE_TEXT))
            css.raise_for_status()
            m = _URL.search(css.text)
            if not m:
                return f"{meta['family']}: no font url"
            font = await client.get(m.group(1))
            font.raise_for_status()
            out.write_bytes(font.content)
        except Exception as exc:  # network hiccups are logged, not fatal
            return f"{meta['family']}: {exc!r}"
    return None


async def _fetch_all(metas: list[dict[str, Any]], concurrency: int) -> list[str]:
    SUBSET_DIR.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(headers=UA, timeout=30, follow_redirects=True) as client:
        tasks = [_fetch_one(client, m, sem) for m in metas]
        errors = []
        done = 0
        for coro in asyncio.as_completed(tasks):
            err = await coro
            done += 1
            if err:
                errors.append(err)
            if done % 200 == 0:
                typer.echo(f"  {done}/{len(tasks)}")
        return errors


def fetch_subsets(metas: list[dict[str, Any]], concurrency: int = 16) -> list[str]:
    """Download measurement subsets for every family; returns error messages."""
    return asyncio.run(_fetch_all(metas, concurrency))


def subset_path(family: str) -> Path:
    return SUBSET_DIR / f"{slug(family)}.ttf"
