# Palette RAG Explorer

Upload an image → extract its color palette → find public-domain paintings (Art Institute of Chicago) with similar palettes → get a Gemini-written explanation of how those artists used color, with cited sources.

**Stack:** Python (FastAPI) · React + TypeScript · Supabase Postgres + pgvector · Gemini

## Setup

```bash
# 1. Python env
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Secrets
cp ../.env.example .env   # fill in DATABASE_URL and GEMINI_API_KEY

# 3. Schema: paste supabase/migrations/001_init.sql into the Supabase SQL editor and run it

# 4. Check the connection
python -m app.db

# 5. Ingest paintings and build the palette index (both are resumable)
python -m ingest.aic --limit 200
python -m ingest.build_index

# Tests
pytest tests

# 6. Run the API, then match an image
uvicorn app.main:app --reload
curl -F file=@some_image.jpg localhost:8000/match
```

## Status
- [x] Phase 0–1: scaffold + schema
- [x] Phase 2: AIC ingestion
- [x] Phase 3: palette extraction + histograms
- [x] Phase 4: two-stage retrieval
- [ ] Phase 5: RAG explanations
- [ ] Phase 6: frontend
- [ ] Phase 7: evaluation
- [ ] Phase 8: deploy
