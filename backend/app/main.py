"""FastAPI app. Run from backend/: uvicorn app.main:app --reload"""

from typing import Annotated

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from PIL import UnidentifiedImageError

from app.db import connect
from app.retrieve import match_image

MAX_UPLOAD_BYTES = 15 * 1024 * 1024

app = FastAPI(title="Palette RAG Explorer")


@app.get("/health")
def health() -> dict:
    return {"ok": True}


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
