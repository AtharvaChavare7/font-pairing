"""Font Pairing API."""

import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from corpus import get_corpus, load_corpus
from scoring import PairRequest, PairResponse, font_info, score_pairs

ROOT = Path(__file__).resolve().parents[1]
FEEDBACK_LOG = ROOT / "data" / "work" / "feedback.jsonl"


@asynccontextmanager
async def lifespan(_: FastAPI):
    load_corpus()
    yield


app = FastAPI(title="Font Pairing API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_static = ROOT / "web-static"
if _static.is_dir():
    app.mount("/ui", StaticFiles(directory=str(_static), html=True), name="ui")


@app.get("/", include_in_schema=False)
def index() -> RedirectResponse:
    return RedirectResponse("/ui/")


@app.get("/api/health")
@app.get("/health", include_in_schema=False)
def health() -> dict:
    c = get_corpus()
    return {"status": "ok", "corpus_loaded": c is not None, "families": len(c) if c else 0}


@app.post("/api/pair", response_model=PairResponse)
def pair(request: PairRequest) -> PairResponse:
    return score_pairs(request)


@app.get("/api/families")
def list_families(q: str = "", page: int = 1, per_page: int = 50) -> dict:
    c = get_corpus()
    if c is None:
        return {"families": [], "total": 0, "page": page, "per_page": per_page}
    df = c.df
    if q:
        names = df["name"].str.lower()
        needle = q.lower().strip()
        hits = df[names.str.contains(needle, regex=False)]
        # prefix matches first, then by popularity
        hits = hits.assign(_pre=~hits["name"].str.lower().str.startswith(needle))
        hits = hits.sort_values(["_pre", "popularity"])
    else:
        hits = df.sort_values("popularity")
    total = len(hits)
    start = max(page - 1, 0) * per_page
    rows = hits.iloc[start : start + per_page]
    return {
        "families": [font_info(c, int(i)).model_dump() for i in rows.index],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@app.get("/api/families/{family_id}")
def get_family(family_id: str) -> dict:
    c = get_corpus()
    if c is None or family_id not in c.index:
        raise HTTPException(status_code=404, detail="family not found")
    i = c.index[family_id]
    r = c.df.iloc[i]
    features = {
        k: float(r[k])
        for k in (
            "x_height", "cap_height", "xh_ratio", "ascender", "descender", "width", "o_aspect",
            "weight", "color", "contrast", "stress", "aperture", "roundness", "serif", "mono",
        )
    }
    return {
        **font_info(c, i).model_dump(),
        "features": features,
        "body_fitness": round(float(c.body_fit[i]), 3),
        "clone_group": r["clone_group_id"],
    }


class Feedback(BaseModel):
    heading: str
    body: str
    vote: int  # +1 like, -1 dislike
    seed: int | None = None
    target_dist: float | None = None


@app.post("/api/feedback")
def feedback(payload: Feedback) -> dict:
    line = json.dumps({**payload.model_dump(), "ts": time.time()})
    try:
        FEEDBACK_LOG.parent.mkdir(parents=True, exist_ok=True)
        with FEEDBACK_LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        # read-only filesystem (serverless): keep the signal in the logs instead
        print(f"feedback {line}", flush=True)
    return {"status": "received"}
