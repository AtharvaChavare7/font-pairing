.PHONY: ingest ingest-clone evaluate api web test install install-offline venv-ingest venv-api

ROOT := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
VENV_INGEST := $(ROOT).venv-ingest
VENV_API := $(ROOT).venv-api
ifeq ($(OS),Windows_NT)
BIN := Scripts
PYTHON ?= python
else
BIN := bin
PYTHON ?= python3
endif
PY_INGEST := $(VENV_INGEST)/$(BIN)/python
PY_API := $(VENV_API)/$(BIN)/python
WHEELHOUSE := $(ROOT)vendor/wheelhouse

venv-ingest:
	$(PYTHON) -m venv $(VENV_INGEST)

venv-api:
	$(PYTHON) -m venv $(VENV_API)

install: venv-ingest venv-api
	$(PY_INGEST) -m pip install -e "$(ROOT)ingest[dev]"
	$(PY_API) -m pip install -r $(ROOT)api/requirements-dev.txt

install-offline:
	@bash "$(ROOT)scripts/install-offline.sh"

# Fetch every Google Fonts family via the CSS2 API and measure it (~1 min)
ingest:
	$(PY_INGEST) -m fontpair_ingest.pipeline run

# Optional: full google/fonts git clone (several GB) for `discover`
ingest-clone:
	$(PY_INGEST) -m fontpair_ingest.pipeline clone

evaluate:
	cd $(ROOT)api && $(PY_API) evaluate.py

api:
	cd $(ROOT)api && $(PY_API) -m uvicorn main:app --reload --port 8000

# Static UI on :3001 calling the API on :8000 (or use http://localhost:8000/ui)
web:
	cd $(ROOT)web-static && $(PY_API) -m http.server 3001

test:
	cd $(ROOT)ingest && $(PY_INGEST) -m pytest -q
	cd $(ROOT)api && $(PY_API) -m pytest -q
