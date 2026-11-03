# Palette RAG Explorer

Upload an image → extract its color palette → find public-domain paintings (Art Institute of Chicago + Cleveland Museum of Art) with similar palettes → get a Gemini-written explanation of how those artists used color, with cited sources.

**Stack:** Python (FastAPI) · React + TypeScript · Supabase Postgres + pgvector · Gemini

## Setup

```bash
# 1. Python env
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Secrets
cp ../.env.example .env   # fill in DATABASE_URL and GEMINI_API_KEY

# 3. Schema: run supabase/migrations/*.sql in order in the Supabase SQL editor

# 4. Check the connection
python -m app.db

# 5. Ingest paintings and build the palette index (both are resumable)
python -m ingest.aic --limit 2000
python -m ingest.cma
python -m ingest.build_index    # palettes, histograms, and precomputed palette edges
python -m ingest.wiki          # Wikipedia + AIC description chunks, embedded with Gemini

# Tests
pytest tests

# 6. Run the API, then match an image
uvicorn app.main:app --reload
curl -F file=@some_image.jpg localhost:8000/match
# then POST /explain with {"query_palette": [...], "artwork_ids": [...]} from the /match response

# Web map: start from a painting, or from an upload
curl 'localhost:8000/graph/1?depth=2&k=6'
curl -F file=@some_image.jpg 'localhost:8000/graph?depth=2&k=6'
# Why are two nodes linked? (source_id, or source_palette for the uploaded image)
curl -X POST localhost:8000/explain-edge -H 'Content-Type: application/json' -d '{"source_id": 1, "target_id": 2}'
```

## Evaluation

```bash
cd backend
python -m eval.make_queries   # 200 crop / photo-like queries from 100 paintings (seeded)
python -m eval.run_eval       # sweep → eval/results.csv, eval/RESULTS.md

# Human-judged precision@5: put ~30 photos/designs in backend/data/eval_human/, then
python -m eval.label build    # open eval/labeling.html, label blind, download labels
python -m eval.label score ~/Downloads/human_labels.json
```

Results: [backend/eval/RESULTS.md](backend/eval/RESULTS.md) (AIC only: [RESULTS_aic_only.md](backend/eval/RESULTS_aic_only.md)).

## Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173 (proxies /api to the backend on :8000)
```

Drop an image (or pick a random painting) to build a palette web. Click a painting for details,
re-center, or expand it; click a line to get a cited explanation of why two paintings connect.

After the corpus grows, run `python -m ingest.build_index --rebuild-edges` so existing paintings'
edges can point at the new ones.

Gemini's free tier allows 1,000 embedding requests per day, and every text embedded counts as
one request even inside a batched call. To stay under it, only Wikipedia chunks are embedded (≤ 8
per artist, ~900 tokens each); AIC descriptions are stored unembedded because `/explain` looks them
up by artwork id. If the quota runs out, `ingest.wiki` stops cleanly; re-run it after midnight
Pacific and it resumes. Enabling billing on the Gemini key removes the daily cap.
Set `GEMINI_MODEL` in `.env` to override the generation model (default `gemini-3-flash-preview`).

## Status
- [x] Phase 0–1: scaffold + schema
- [x] Phase 2: AIC ingestion
- [x] Phase 3: palette extraction + histograms
- [x] Phase 4: two-stage retrieval
- [x] Phase 5: RAG explanations
- [x] Phase 5b: web map backend (`/graph`, `/explain-edge`)
- [x] Phase 6: frontend (React + TS, react-force-graph-2d)
- [x] Phase 7: evaluation
- [ ] Phase 8: deploy
