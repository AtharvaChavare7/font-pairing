"""Paths and constants for ingestion."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_RAW = REPO_ROOT / "data" / "raw"
DATA_WORK = REPO_ROOT / "data" / "work"
DATA_OUT = REPO_ROOT / "data" / "out"

GOOGLE_FONTS_DIR = DATA_RAW / "google-fonts"
REJECTS_PATH = DATA_WORK / "rejects.jsonl"

# Outputs of the git-clone discovery path (`fontpair-ingest discover`)
FACES_PARQUET = DATA_OUT / "clone_faces.parquet"
CLONE_FAMILIES_PARQUET = DATA_OUT / "clone_families.parquet"

# Google Fonts API path (`fontpair-ingest run`) — what the API serves
GF_METADATA_URL = "https://fonts.google.com/metadata/fonts"
GF_METADATA_JSON = DATA_RAW / "gf-metadata.json"
SUBSET_DIR = DATA_RAW / "gf-subsets"
FAMILIES_PARQUET = DATA_OUT / "families.parquet"
EMBED_NPY = DATA_OUT / "embeddings.npy"

GOOGLE_LICENSE_DIRS = ("ofl", "apache", "ufl")
HOSTABLE_LICENSE_DIRS = frozenset(GOOGLE_LICENSE_DIRS)

SCRIPT_COVERAGE_THRESHOLD = 0.9
