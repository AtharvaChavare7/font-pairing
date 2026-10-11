"""Orchestrate ingestion pipeline."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import typer

from fontpair_ingest.config import (
    API_SNAPSHOT_DIR,
    CLONE_FAMILIES_PARQUET,
    DATA_OUT,
    DATA_WORK,
    EMBED_NPY,
    FACES_PARQUET,
    FAMILIES_PARQUET,
    GOOGLE_FONTS_DIR,
    REJECTS_PATH,
)
from fontpair_ingest.dedupe import clone_groups
from fontpair_ingest.discover import discover_corpus
from fontpair_ingest.embed import pca_embed
from fontpair_ingest.features import FEATURE_COLUMNS, extract_features
from fontpair_ingest.grouping import group_faces_into_families
from fontpair_ingest.sources import clone_google_fonts
from fontpair_ingest.subset import eligible, fetch_metadata, fetch_subsets, regular_weight, slug, subset_path

app = typer.Typer(help="Font Pairing ingestion pipeline")


def _measure(path: str) -> tuple[dict[str, float] | None, np.ndarray | None, str | None]:
    try:
        feats, sheet = extract_features(Path(path))
        return feats, sheet, None
    except Exception as exc:
        return None, None, repr(exc)


def _family_row(meta: dict[str, Any]) -> dict[str, Any]:
    styles = list(meta.get("fonts", {}))
    weights = sorted({int(s.rstrip("i")) for s in styles if s.rstrip("i").isdigit()})
    axes = [a["tag"] for a in meta.get("axes", [])]
    return {
        "name": meta["family"],
        "slug": slug(meta["family"]),
        "category": meta.get("category") or "",
        "stroke": meta.get("stroke") or "",
        "classifications": list(meta.get("classifications", [])),
        "designers": list(meta.get("designers", [])),
        "popularity": int(meta.get("popularity") or 9999),
        "trending": int(meta.get("trending") or 9999),
        "date_added": meta.get("dateAdded") or "",
        "styles": styles,
        "weights": weights,
        "regular_weight": regular_weight(meta),
        "has_italic": any(s.endswith("i") for s in styles),
        "has_bold": any(w >= 600 for w in weights),
        "axes": axes,
        "is_variable": bool(axes),
        "subsets": list(meta.get("subsets", [])),
        "is_brand": bool(meta.get("isBrandFont")),
    }


def run_api_ingest(limit: int | None = None, workers: int | None = None, refresh: bool = False) -> None:
    """Google Fonts API → measured features → families.parquet + embeddings.npy."""
    DATA_WORK.mkdir(parents=True, exist_ok=True)
    DATA_OUT.mkdir(parents=True, exist_ok=True)

    metas = [m for m in fetch_metadata(force=refresh) if eligible(m)]
    metas.sort(key=lambda m: m.get("popularity") or 9999)
    if limit:
        metas = metas[:limit]
    typer.echo(f"Eligible families: {len(metas)}")

    typer.echo("Downloading measurement subsets from fonts.googleapis.com…")
    errors = fetch_subsets(metas)
    for e in errors:
        typer.secho(f"  fetch failed — {e}", fg=typer.colors.YELLOW)

    metas = [m for m in metas if subset_path(m["family"]).is_file()]
    typer.echo(f"Measuring {len(metas)} fonts…")
    paths = [str(subset_path(m["family"])) for m in metas]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(_measure, paths, chunksize=16))

    rows, sheets, rejects = [], [], []
    for meta, (feats, sheet, err) in zip(metas, results):
        if feats is None or sheet is None:
            rejects.append({"family": meta["family"], "error": err or "no raster sheet"})
            continue
        rows.append({**_family_row(meta), **feats})
        sheets.append(sheet)

    if rejects:
        pd.DataFrame(rejects).to_json(REJECTS_PATH, orient="records", lines=True)
    typer.echo(f"Measured: {len(rows)} | rejected: {len(rejects)} (see {REJECTS_PATH})")

    sheet_arr = np.vstack(sheets)
    emb, ratio = pca_embed(sheet_arr)
    typer.echo(f"PCA: {emb.shape[1]} dims explain {ratio.sum():.1%} of glyph-shape variance")

    df = pd.DataFrame(rows)
    df["clone_group_id"] = clone_groups(df["name"].tolist(), sheet_arr)
    n_clones = df["clone_group_id"].notna().sum()
    typer.echo(f"Clone groups: {df['clone_group_id'].nunique()} covering {n_clones} families")

    df.to_parquet(FAMILIES_PARQUET, index=False)
    np.save(EMBED_NPY, emb)
    typer.echo(f"Wrote {FAMILIES_PARQUET} ({len(df)} families, {len(FEATURE_COLUMNS)} features)")
    typer.echo(f"Wrote {EMBED_NPY}")

    API_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_json(API_SNAPSHOT_DIR / "families.json", orient="records")
    np.save(API_SNAPSHOT_DIR / "embeddings.npy", emb)
    typer.echo(f"Wrote API snapshot to {API_SNAPSHOT_DIR}")


def run_clone_discovery(corpus_root: Path | None = None) -> None:
    """Discover faces in a google/fonts clone, group families, write Parquet outputs."""
    root = corpus_root or GOOGLE_FONTS_DIR
    if not (root / "ofl").is_dir():
        typer.secho(
            f"Corpus not found at {root}. Run `fontpair-ingest clone` or copy google-fonts there.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    DATA_WORK.mkdir(parents=True, exist_ok=True)
    DATA_OUT.mkdir(parents=True, exist_ok=True)

    typer.echo(f"Discovering fonts under {root}...")
    faces, reject_count = discover_corpus(root)
    total_attempts = len(faces) + reject_count
    reject_rate = (reject_count / total_attempts * 100) if total_attempts else 0.0
    typer.echo(f"Faces discovered: {len(faces)} | rejects logged: {reject_count} ({reject_rate:.2f}%)")

    families, face_rows = group_faces_into_families(faces, root)
    typer.echo(f"Families: {len(families)}")

    pd.DataFrame([f.__dict__ for f in families]).to_parquet(CLONE_FAMILIES_PARQUET, index=False)
    pd.DataFrame(face_rows).to_parquet(FACES_PARQUET, index=False)
    typer.echo(f"Wrote {CLONE_FAMILIES_PARQUET}")
    typer.echo(f"Wrote {FACES_PARQUET}")


@app.command("run")
def run_cmd(
    limit: int | None = typer.Option(None, "--limit", help="Only the N most popular families (for quick runs)"),
    workers: int | None = typer.Option(None, "--workers", help="Measurement processes (default: CPU count)"),
    refresh: bool = typer.Option(False, "--refresh", help="Re-download Google Fonts metadata"),
) -> None:
    """Fetch from the Google Fonts API, measure every family, write the feature store."""
    run_api_ingest(limit=limit, workers=workers, refresh=refresh)


@app.command("clone")
def clone_cmd(force: bool = typer.Option(False, "--force", help="Re-clone corpus")) -> None:
    """Clone Google Fonts repository (optional; `run` does not need it)."""
    clone_google_fonts(force=force)


@app.command("discover")
def discover_cmd(
    corpus: Path | None = typer.Option(
        None,
        "--corpus",
        help="Path to google-fonts root (default: data/raw/google-fonts)",
    ),
) -> None:
    """Walk a google/fonts clone and write clone_faces/clone_families Parquet."""
    run_clone_discovery(corpus)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        run_api_ingest()


if __name__ == "__main__":
    app()
