"""Ingest CC0 paintings from the Cleveland Museum of Art Open Access API.

Usage (from backend/):
    python -m ingest.cma
    python -m ingest.build_index --rebuild-edges   # then features, and edges that can reach the new paintings
    python -m ingest.wiki                          # Wikipedia text for new artists + CMA descriptions

Resumable: rows are upserted on (source, source_id) and cached images are not downloaded again.
"""

import io
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

from app.db import connect
from ingest.aic import HEADERS, get_with_retry, image_cache_dir, strip_html

API_URL = "https://openaccess-api.clevelandart.org/api/artworks/"
PAGE_SIZE = 1000
FIELDS = "id,accession_number,title,creators,creation_date,culture,description,images,url"
DOWNLOAD_WORKERS = 4
CACHE_WIDTH = 400  # same width as the AIC images, so features are computed alike


def artist_name(creators: list[dict[str, Any]] | None) -> str | None:
    """'John Singleton Copley (American, 1738–1815)' → 'John Singleton Copley' (matches AIC's form)."""
    if not creators:
        return None
    main = next((c for c in creators if c.get("role") == "artist"), creators[0])
    name = re.sub(r"\s*\(.*\)\s*$", "", main.get("description") or "").strip()
    return name or None


def fetch_all(client: httpx.Client) -> list[dict[str, Any]]:
    out, skip = [], 0
    while True:
        r = get_with_retry(client, "GET", API_URL, params={
            "type": "Painting", "has_image": 1, "cc0": 1, "limit": PAGE_SIZE, "skip": skip, "fields": FIELDS})
        r.raise_for_status()
        data = r.json()["data"]
        out.extend(data)
        print(f"listed {len(out)} paintings", flush=True)
        if len(data) < PAGE_SIZE:
            return out
        skip += PAGE_SIZE


def download(client: httpx.Client, url: str, path: Path) -> bool:
    if path.exists() and path.stat().st_size > 0:
        return True
    try:
        r = get_with_retry(client, "GET", url)
        if r.status_code != 200:
            return False
        img = Image.open(io.BytesIO(r.content))
        img.load()  # reject truncated files before caching
    except (httpx.HTTPError, OSError):
        return False
    img = img.convert("RGB")
    if img.width > CACHE_WIDTH:
        img = img.resize((CACHE_WIDTH, round(img.height * CACHE_WIDTH / img.width)), Image.Resampling.LANCZOS)
    tmp = path.with_suffix(".part")
    img.save(tmp, format="JPEG", quality=90)
    tmp.rename(path)
    return True


UPSERT_SQL = """
insert into artworks (source, source_id, source_url, title, artist, date, style, image_id, image_url,
                      description, excluded)
values ('cma', %(source_id)s, %(source_url)s, %(title)s, %(artist)s, %(date)s, %(style)s,
        %(image_id)s, %(image_url)s, %(description)s, %(excluded)s)
on conflict (source, source_id) do update set
  source_url = excluded.source_url, title = excluded.title, artist = excluded.artist, date = excluded.date,
  style = excluded.style, image_id = excluded.image_id, image_url = excluded.image_url,
  description = excluded.description, excluded = excluded.excluded
"""


# Cleveland's "Painting" type includes manuscript pages with no painting on them. Folios with a
# picture on one side ("A Monk Preaching (recto); Text (verso)") are kept.
NOT_A_PAINTING = re.compile(r"^text\b|\btext pages?\b|\bblank\b|^genealogical text|:\s*text\s*$", re.IGNORECASE)


def exclusion_reason(title: str) -> str | None:
    return "manuscript text or blank page" if NOT_A_PAINTING.search(title) else None


def row(art: dict[str, Any]) -> dict[str, Any] | None:
    web = ((art.get("images") or {}).get("web") or {}).get("url")
    if not web or not art.get("accession_number"):
        return None
    return {
        "source_id": str(art["id"]),
        "source_url": art.get("url") or f"https://clevelandart.org/art/{art['accession_number']}",
        "title": art.get("title") or "Untitled",
        "artist": artist_name(art.get("creators")),
        "date": art.get("creation_date"),
        "style": (art.get("culture") or [None])[0],
        "image_id": f"cma-{art['accession_number']}",
        "image_url": web,
        "description": strip_html(art.get("description")),
        "excluded": exclusion_reason(art.get("title") or ""),
    }


def ingest() -> None:
    cache = image_cache_dir()
    with httpx.Client(headers=HEADERS, timeout=60) as client:
        rows = [r for r in map(row, fetch_all(client)) if r]
        with ThreadPoolExecutor(DOWNLOAD_WORKERS) as pool:
            ok = list(pool.map(lambda r: download(client, r["image_url"], cache / f"{r['image_id']}.jpg"), rows))
    saved = [r for r, good in zip(rows, ok) if good]
    failed = [r["source_id"] for r, good in zip(rows, ok) if not good]
    with connect() as conn, conn.cursor() as cur:
        cur.executemany(UPSERT_SQL, saved)
        cur.execute("delete from artworks where source = 'cma' and source_id = any(%s)", (failed,))
    print(f"done: {len(saved)} CMA paintings saved, {len(failed)} skipped (image unavailable)")


if __name__ == "__main__":
    ingest()
