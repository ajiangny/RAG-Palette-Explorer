"""Ingest public-domain paintings from the Art Institute of Chicago API.

Usage (from backend/):
    python -m ingest.aic --limit 200

Resumable: metadata is upserted on aic_id, and images already in the cache are
not downloaded again, so re-running with a larger --limit picks up where it left off.
"""

import argparse
import html
import os
import re
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

from app.db import connect

load_dotenv()

API_URL = "https://api.artic.edu/api/v1/artworks/search"
IIIF_URL = "https://www.artic.edu/iiif/2"
# AIC asks API clients to identify themselves.
HEADERS = {"AIC-User-Agent": "palette-rag-explorer (andrewjiang74@gmail.com)",
           "User-Agent": "palette-rag-explorer/0.1"}
FIELDS = ["id", "title", "artist_title", "date_display", "style_title", "image_id", "description"]
PAGE_SIZE = 100
REQUEST_DELAY = 1.0  # seconds between requests; AIC rate-limits at 60/min

BACKEND_DIR = Path(__file__).resolve().parent.parent


def image_cache_dir() -> Path:
    d = Path(os.environ.get("IMAGE_CACHE_DIR", "data/images"))
    if not d.is_absolute():
        d = BACKEND_DIR / d
    d.mkdir(parents=True, exist_ok=True)
    return d


def strip_html(text: str | None) -> str | None:
    if not text:
        return None
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    return text or None


def display_url(image_id: str) -> str:
    return f"{IIIF_URL}/{image_id}/full/843,/0/default.jpg"


def feature_url(image_id: str) -> str:
    return f"{IIIF_URL}/{image_id}/full/400,/0/default.jpg"


def get_with_retry(client: httpx.Client, method: str, url: str, **kw) -> httpx.Response:
    for attempt in range(5):
        try:
            r = client.request(method, url, **kw)
            if r.status_code == 429 or r.status_code >= 500:
                raise httpx.HTTPStatusError("retryable", request=r.request, response=r)
            return r
        except (httpx.TransportError, httpx.HTTPStatusError):
            if attempt == 4:
                raise
            time.sleep(2 ** attempt * REQUEST_DELAY)
    raise AssertionError("unreachable")


def fetch_page(client: httpx.Client, page: int) -> dict:
    body = {
        "query": {"bool": {"filter": [
            {"term": {"is_public_domain": True}},
            {"term": {"artwork_type_id": 1}},  # Painting
            {"exists": {"field": "image_id"}},
        ]}},
        "fields": FIELDS,
        "limit": PAGE_SIZE,
        "page": page,
    }
    r = get_with_retry(client, "POST", API_URL, json=body)
    r.raise_for_status()
    return r.json()


def download_image(client: httpx.Client, image_id: str, cache: Path) -> bool:
    path = cache / f"{image_id}.jpg"
    if path.exists() and path.stat().st_size > 0:
        return True
    r = get_with_retry(client, "GET", feature_url(image_id))
    time.sleep(REQUEST_DELAY)
    if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image/"):
        return False
    tmp = path.with_suffix(".part")
    tmp.write_bytes(r.content)
    tmp.rename(path)
    return True


UPSERT_SQL = """
insert into artworks (aic_id, title, artist, date, style, image_id, image_url, description)
values (%(aic_id)s, %(title)s, %(artist)s, %(date)s, %(style)s, %(image_id)s, %(image_url)s, %(description)s)
on conflict (aic_id) do update set
  title = excluded.title, artist = excluded.artist, date = excluded.date,
  style = excluded.style, image_id = excluded.image_id,
  image_url = excluded.image_url, description = excluded.description
"""


def ingest(limit: int) -> None:
    cache = image_cache_dir()
    saved = skipped = 0
    page = 1
    with httpx.Client(headers=HEADERS, timeout=30) as client:
        while saved < limit:
            data = fetch_page(client, page)
            if not data["data"]:
                break
            batch = []
            for art in data["data"]:
                if saved + len(batch) >= limit:
                    break
                image_id = art.get("image_id")
                if not image_id or not download_image(client, image_id, cache):
                    skipped += 1
                    continue
                batch.append({
                    "aic_id": art["id"],
                    "title": art.get("title") or "Untitled",
                    "artist": art.get("artist_title"),
                    "date": art.get("date_display"),
                    "style": art.get("style_title"),
                    "image_id": image_id,
                    "image_url": display_url(image_id),
                    "description": strip_html(art.get("description")),
                })
            # Short-lived connection per page: downloads are slow and the pooler
            # drops connections that sit idle across them.
            with connect() as conn, conn.cursor() as cur:
                cur.executemany(UPSERT_SQL, batch)
            saved += len(batch)
            total_pages = data["pagination"]["total_pages"]
            print(f"page {page}/{total_pages}: {saved} saved, {skipped} skipped", flush=True)
            if page >= total_pages:
                break
            page += 1
            time.sleep(REQUEST_DELAY)
    print(f"done: {saved} artworks saved, {skipped} skipped (no image)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=200)
    ingest(parser.parse_args().limit)
