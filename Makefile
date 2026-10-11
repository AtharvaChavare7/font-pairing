.PHONY: ingest ingest-clone evaluate api web web-static test install install-offline venv-ingest venv-api

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
	$(PY_API) -m pip install -r $(ROOT)api/requirements.txt
	cd $(ROOT)web && npm install

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

web:
	@if [ -d "$(ROOT)web/node_modules" ]; then \
		cd $(ROOT)web && npm run dev; \
	else \
		$(MAKE) web-static; \
	fi

web-static:
	@echo "Next.js deps missing — static UI at http://localhost:3001 (or http://localhost:8000/ui via make api) (API CORS enabled)"
	cd $(ROOT)web-static && $(PY_API) -m http.server 3001

test:
	cd $(ROOT)ingest && $(PY_INGEST) -m pytest -q
	cd $(ROOT)api && $(PY_API) -m pytest -q
