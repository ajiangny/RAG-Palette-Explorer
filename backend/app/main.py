"""FastAPI app. Run from backend/: uvicorn app.main:app --reload"""

import os
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import UnidentifiedImageError
from pydantic import BaseModel, Field, model_validator

from app.db import connect
from app.graph import graph_for_artwork, graph_for_upload
from app.rag import explain_edge, explain_matches
from app.retrieve import match_image

MAX_UPLOAD_BYTES = 15 * 1024 * 1024

app = FastAPI(title="Palette RAG Explorer")
# In dev the Vite server proxies /api, so CORS only matters for a deployed frontend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in os.environ.get("FRONTEND_ORIGINS", "http://localhost:5173").split(",") if o],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/artworks/random")
def random_artwork() -> dict:
    with connect() as conn:
        row = conn.execute("select id, title, artist from artworks where hist is not null "
                           "order by random() limit 1").fetchone()
    if row is None:
        raise HTTPException(404, "collection is empty")
    return {"id": row[0], "title": row[1], "artist": row[2]}


async def read_upload(file: UploadFile) -> bytes:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "image too large (max 15 MB)")
    if not data:
        raise HTTPException(400, "empty upload")
    return data


@app.post("/match")
async def match(
    file: Annotated[UploadFile, File()],
    k: Annotated[int, Query(ge=1, le=50)] = 10,
    candidates: Annotated[int, Query(ge=1, le=500)] = 100,
    alpha: Annotated[float, Query(ge=0, le=1)] = 0.0,
) -> dict:
    data = await read_upload(file)
    try:
        with connect() as conn:
            palette, results = match_image(conn, data, k=k, candidates=max(candidates, k), alpha=alpha)
    except (UnidentifiedImageError, OSError) as e:
        raise HTTPException(400, f"could not read image: {e}") from e
    return {"query_palette": palette, "results": results}


class SwatchIn(BaseModel):
    lab: list[float] = Field(min_length=3, max_length=3)
    hex: str
    weight: float = Field(ge=0, le=1)


class ExplainRequest(BaseModel):
    query_palette: list[SwatchIn] = Field(min_length=1, max_length=12)
    artwork_ids: list[int] = Field(min_length=1, max_length=10)


@app.post("/explain")
def explain(req: ExplainRequest) -> dict:
    with connect() as conn:
        result = explain_matches(conn, [s.model_dump() for s in req.query_palette], req.artwork_ids)
    if not result["artworks"]:
        raise HTTPException(404, "none of the artwork_ids exist")
    return result


GraphK = Annotated[int, Query(ge=1, le=10)]
GraphDepth = Annotated[int, Query(ge=1, le=3)]


@app.get("/graph/{artwork_id}")
def graph_from_artwork(artwork_id: int, k: GraphK = 6, depth: GraphDepth = 2) -> dict:
    with connect() as conn:
        result = graph_for_artwork(conn, artwork_id, k=k, depth=depth)
    if result is None:
        raise HTTPException(404, "artwork not found")
    return result


@app.post("/graph")
async def graph_from_upload(file: Annotated[UploadFile, File()], k: GraphK = 6,
                            depth: GraphDepth = 2) -> dict:
    data = await read_upload(file)
    try:
        with connect() as conn:
            return graph_for_upload(conn, data, k=k, depth=depth)
    except (UnidentifiedImageError, OSError) as e:
        raise HTTPException(400, f"could not read image: {e}") from e


class ExplainEdgeRequest(BaseModel):
    """An edge of the web: target is a painting; source is a painting or the uploaded image's palette."""
    target_id: int
    source_id: int | None = None
    source_palette: list[SwatchIn] | None = Field(default=None, min_length=1, max_length=12)

    @model_validator(mode="after")
    def one_source(self):
        if (self.source_id is None) == (self.source_palette is None):
            raise ValueError("give exactly one of source_id or source_palette")
        if self.source_id == self.target_id:
            raise ValueError("source and target are the same artwork")
        return self


@app.post("/explain-edge")
def explain_edge_endpoint(req: ExplainEdgeRequest) -> dict:
    palette = [s.model_dump() for s in req.source_palette] if req.source_palette else None
    with connect() as conn:
        result = explain_edge(conn, req.target_id, source_id=req.source_id, source_palette=palette)
    if result is None:
        raise HTTPException(404, "artwork not found")
    return result
