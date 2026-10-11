"""Tests for Font Pairing API."""

import numpy as np
import pytest
from fastapi.testclient import TestClient

import corpus
from main import app

has_corpus = corpus.FAMILIES_JSON.is_file()
needs_corpus = pytest.mark.skipif(not has_corpus, reason="run `fontpair-ingest run` first")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health(client) -> None:
    for path in ("/api/health", "/health"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


@needs_corpus
def test_pair_returns_seeded_results(client) -> None:
    body = {"n": 5, "seed": 42}
    a = client.post("/api/pair", json=body).json()
    b = client.post("/api/pair", json=body).json()
    assert a["seed"] == 42
    assert len(a["results"]) == 5
    assert [(r["heading"]["id"], r["body"]["id"]) for r in a["results"]] == [
        (r["heading"]["id"], r["body"]["id"]) for r in b["results"]
    ]
    for r in a["results"]:
        assert r["heading"]["id"] != r["body"]["id"]
        assert 0 < r["score"] <= 100
        assert r["reasons"]


@needs_corpus
def test_anchor_heading(client) -> None:
    res = client.post("/api/pair", json={"n": 6, "seed": 1, "anchor_id": "playfair-display", "anchor_role": "heading"})
    results = res.json()["results"]
    assert results and all(r["heading"]["id"] == "playfair-display" for r in results)
    assert len({r["body"]["id"] for r in results}) == len(results)


@needs_corpus
def test_category_filter(client) -> None:
    res = client.post(
        "/api/pair",
        json={"n": 8, "seed": 7, "filters": {"heading_categories": ["serif"], "body_categories": ["sans"]}},
    ).json()
    assert all(r["heading"]["category"] == "serif" and r["body"]["category"] == "sans" for r in res["results"])


@needs_corpus
def test_family_search(client) -> None:
    data = client.get("/api/families", params={"q": "plex"}).json()
    names = [f["name"] for f in data["families"]]
    assert "IBM Plex Sans" in names
    detail = client.get("/api/families/ibm-plex-sans").json()
    assert 0.6 < detail["features"]["xh_ratio"] < 0.85
    assert client.get("/api/families/not-a-font").status_code == 404


@needs_corpus
def test_known_pairings_rank_highly() -> None:
    from evaluate import known_pair_percentiles

    c = corpus.load_corpus()
    pct = [p for _, _, p in known_pair_percentiles(c)]
    assert len(pct) >= 20
    assert np.mean(pct) > 0.8
