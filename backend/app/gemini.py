"""Thin wrapper around the Gemini API: text embeddings + generation."""

import os
import time
from functools import cache

import numpy as np
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

load_dotenv()

EMBED_MODEL = "gemini-embedding-001"
EMBED_DIM = 768  # must match text_chunks.embedding
EMBED_BATCH = 50
GENERATE_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview")


@cache
def client() -> genai.Client:
    http = types.HttpOptions(timeout=60_000)
    # Vertex AI (billed to a GCP project, no free-tier daily cap): the SDK reads
    # GOOGLE_CLOUD_PROJECT / GOOGLE_CLOUD_LOCATION and gcloud's application-default credentials.
    if os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true"):
        return genai.Client(http_options=http)
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set (or set GOOGLE_GENAI_USE_VERTEXAI=true)")
    return genai.Client(api_key=key, http_options=http)


class DailyQuotaExceeded(RuntimeError):
    """The free tier's per-day request quota is used up; retrying won't help until it resets."""


def _with_backoff(fn, attempts: int = 6):
    for attempt in range(attempts):
        try:
            return fn()
        except errors.APIError as e:
            if e.code == 429 and "PerDay" in str(e):
                raise DailyQuotaExceeded(str(e)) from e
            if e.code not in (429, 500, 503) or attempt == attempts - 1:
                raise
            time.sleep(min(60, 2 ** attempt * 2))
    raise AssertionError("unreachable")


def embed(texts: list[str], task: str = "RETRIEVAL_DOCUMENT") -> list[np.ndarray]:
    """Embed texts as unit-length float32 vectors (task: RETRIEVAL_DOCUMENT or RETRIEVAL_QUERY)."""
    config = types.EmbedContentConfig(task_type=task, output_dimensionality=EMBED_DIM)
    out = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = texts[i:i + EMBED_BATCH]
        res = _with_backoff(lambda: client().models.embed_content(
            model=EMBED_MODEL, contents=batch, config=config))
        for e in res.embeddings or []:
            v = np.asarray(e.values, dtype=np.float32)
            out.append(v / np.linalg.norm(v))  # truncated dims aren't normalized by the API
    return out


def generate(prompt: str, system: str, temperature: float = 0.3) -> str:
    config = types.GenerateContentConfig(system_instruction=system, temperature=temperature)
    res = _with_backoff(lambda: client().models.generate_content(
        model=GENERATE_MODEL, contents=prompt, config=config))
    return (res.text or "").strip()
