"""Fetch and clone font corpora."""

from __future__ import annotations

import subprocess
from pathlib import Path

import typer

from fontpair_ingest.config import GOOGLE_FONTS_DIR

GOOGLE_FONTS_REPO = "https://github.com/google/fonts"


def google_fonts_present() -> bool:
    return (GOOGLE_FONTS_DIR / "ofl").is_dir()


def clone_google_fonts(force: bool = False) -> Path:
    """Clone Google Fonts git repo into data/raw/google-fonts."""
    if google_fonts_present() and not force:
        typer.echo(f"Google Fonts corpus already present at {GOOGLE_FONTS_DIR}")
        return GOOGLE_FONTS_DIR

    GOOGLE_FONTS_DIR.parent.mkdir(parents=True, exist_ok=True)
    if GOOGLE_FONTS_DIR.exists() and force:
        typer.echo(f"Removing existing {GOOGLE_FONTS_DIR}")
        import shutil

        shutil.rmtree(GOOGLE_FONTS_DIR)

    typer.echo(f"Cloning {GOOGLE_FONTS_REPO} (shallow)...")
    cmd = [
        "git",
        "clone",
        "--depth",
        "1",
        GOOGLE_FONTS_REPO,
        str(GOOGLE_FONTS_DIR),
    ]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        typer.secho(
            "git clone failed (often blocked by corporate proxy/Zscaler).\n"
            "On a machine with GitHub access, run:\n"
            f"  git clone --depth 1 {GOOGLE_FONTS_REPO} {GOOGLE_FONTS_DIR}\n"
            "Then copy that folder onto this machine.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1) from exc

    if not google_fonts_present():
        typer.secho(f"Clone finished but {GOOGLE_FONTS_DIR}/ofl not found.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    return GOOGLE_FONTS_DIR
