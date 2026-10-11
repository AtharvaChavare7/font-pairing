# Font Pairing Engine

Suggests font pairings from the measured geometry of every family on Google Fonts.

## Run it

Windows (PowerShell), from this folder:

```powershell
python -m venv .venv-ingest; python -m venv .venv-api
.venv-ingest\Scripts\python -m pip install -e "ingest[dev]"
.venv-api\Scripts\python -m pip install -r api\requirements.txt

.venv-ingest\Scripts\python -m fontpair_ingest.pipeline run      # ~1 min: fetch + measure
.venv-api\Scripts\python -m uvicorn main:app --app-dir api --port 8000
```

Open http://localhost:8000. On macOS/Linux, `make install ingest api` does the same.

## Pipeline

1. **Fetch.** `ingest/fontpair_ingest/subset.py` reads the Google Fonts metadata feed (category, popularity, designers, styles), then asks the CSS2 API for each family's regular face with `text=` so only the ~28 glyphs we measure come back (~5 KB per family, no multi-GB clone).
2. **Measure.** `shape.py` and `features.py` flatten outlines and intersect them with lines (nonzero winding, so overlapping variable-font contours are handled correctly) to get x-height, cap height, x-height/cap ratio, ascender/descender, letter width, `o` aspect, stem weight, typographic colour, stroke contrast and stress angle, aperture, roundness, serif presence and monospacing.
3. **Embed.** `raster.py` rasterizes `aegnosRkH` into fixed cells normalized by cap height. `embed.py` runs PCA (SVD) to produce a 24-d glyph-shape embedding, and `dedupe.py` groups near-identical clones.
4. **Store.** The results go to `data/out/families.parquet` and `data/out/embeddings.npy`.

## Scoring (`api/scoring.py`)

```
score = harmony^0.9 · contrast_fit^1.2 · legibility(body) · character(heading)^½
        · familiarity^0.6 · valley · kinship
```

- **Harmony.** The proportions agree: x-height/cap, width, bowl shape, aperture.
- **Contrast fit.** How close the pair's style distance lands to the *Contrast* slider. Style distance combines classification, measured serifs, stroke contrast, colour and embedding distance.
- **Legibility.** The body face must survive paragraphs.
- **Familiarity.** A popularity prior centred on the *Discovery* slider.
- **Valley.** Penalizes near-identical cousins of the same genre.
- **Kinship.** A bonus for designed superfamilies (Source, Plex, PT, Alegreya…).

Each result comes with plain-language reasons derived from the measurements.

`seeds/known_pairings.csv` holds 32 widely recommended pairings. `api/evaluate.py` reports where each one ranks among all bodies for its heading: the mean percentile is currently about 90%. A test keeps it above 80%.

## Layout

| Path | What |
| --- | --- |
| `ingest/` | Fetch + measurement pipeline (`fontpair-ingest run`; `clone` / `discover` for a full google/fonts checkout) |
| `api/` | FastAPI: `/api/pair`, `/api/families`, `/api/families/{id}`, `/api/feedback`, UI at `/ui` |
| `web-static/` | The UI (plain HTML/CSS/JS, served by the API) |
| `web/` | Next.js scaffold (not yet used) |
| `data/` | Generated: raw subsets, feature store, `work/feedback.jsonl` |
