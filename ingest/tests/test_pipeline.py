"""Tests for ingestion pipeline."""

from fontpair_ingest import __version__


def test_version() -> None:
    assert __version__ == "0.1.0"
