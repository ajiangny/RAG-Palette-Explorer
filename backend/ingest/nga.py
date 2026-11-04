"""Ingest open-access paintings from the National Gallery of Art's open data (CC0).

Usage (from backend/):
    python -m ingest.nga
    python -m ingest.build_index --rebuild-edges   # then features, and edges that can reach the new paintings
    python -m ingest.wiki                          # Wikipedia text for new artists

The gallery publishes CSV files rather than a search API. The CSVs carry no descriptions.
Resumable: rows are upserted on (source, source_id) and cached images are not downloaded again.
"""

import csv
import io
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx

from app.db import connect
from ingest.aic import get_with_retry, image_cache_dir
from ingest.cma import CACHE_WIDTH, DOWNLOAD_WORKERS, download

HEADERS = {"User-Agent": "palette-rag-explorer/0.1"}
DATA_URL = "https://raw.githubusercontent.com/NationalGalleryOfArt/opendata/main/data"
DISPLAY_WIDTH = 843  # same as the AIC display images

# The backs of double-sided panels are often coats of arms or bare wood, not a second picture.
REVERSE_SIDE = re.compile(r"\[reverse\b", re.IGNORECASE)


def exclusion_reason(title: str) -> str | None:
    return "reverse of a panel" if REVERSE_SIDE.search(title) else None


def fetch_csv(client: httpx.Client, name: str) -> list[dict[str, str]]:
    r = get_with_retry(client, "GET", f"{DATA_URL}/{name}.csv")
    r.raise_for_status()
    csv.field_size_limit(10**9)  # provenance and alt-text fields are long
    return list(csv.DictReader(io.StringIO(r.content.decode("utf-8"))))


def open_primary_images(images: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    """objectid → its primary image, for images the gallery marks open access."""
    out: dict[str, dict[str, str]] = {}
    for img in images:
        if img["viewtype"] == "primary" and img["openaccess"] == "1":
            out.setdefault(img["depictstmsobjectid"], img)
    return out


def iiif_url(img: dict[str, str], width: int) -> str:
    """IIIF URL at `width`, or at the image's own width if it is smaller (never upscaled)."""
    native = int(img["width"]) if img["width"].isdigit() else width
    return f"{img['iiifurl']}/full/{min(width, native)},/0/default.jpg"


def row(obj: dict[str, str], img: dict[str, str]) -> dict[str, Any]:
    title = obj["title"] or "Untitled"
    return {
        "source_id": obj["objectid"],
        "source_url": f"https://www.nga.gov/collection/art-object-page.{obj['objectid']}.html",
        "title": title,
        "artist": obj["attribution"] or None,
        "date": obj["displaydate"] or None,
        "image_id": f"nga-{obj['objectid']}",
        "image_url": iiif_url(img, DISPLAY_WIDTH),
        "feature_url": iiif_url(img, CACHE_WIDTH),
        "excluded": exclusion_reason(title),
    }


def select_rows(objects: list[dict[str, str]], images: list[dict[str, str]]) -> list[dict[str, Any]]:
    primary = open_primary_images(images)
    return [row(o, primary[o["objectid"]]) for o in objects
            if o["classification"] == "Painting" and o["isvirtual"] != "1" and o["objectid"] in primary]


UPSERT_SQL = """
insert into artworks (source, source_id, source_url, title, artist, date, image_id, image_url, excluded)
values ('nga', %(source_id)s, %(source_url)s, %(title)s, %(artist)s, %(date)s, %(image_id)s, %(image_url)s, %(excluded)s)
on conflict (source, source_id) do update set
  source_url = excluded.source_url, title = excluded.title, artist = excluded.artist, date = excluded.date,
  image_id = excluded.image_id, image_url = excluded.image_url, excluded = excluded.excluded
"""


def ingest() -> None:
    cache = image_cache_dir()
    with httpx.Client(headers=HEADERS, timeout=120) as client:
        rows = select_rows(fetch_csv(client, "objects"), fetch_csv(client, "published_images"))
        print(f"{len(rows)} open-access paintings listed", flush=True)
        with ThreadPoolExecutor(DOWNLOAD_WORKERS) as pool:
            ok = list(pool.map(lambda r: download(client, r["feature_url"], cache / f"{r['image_id']}.jpg"), rows))
    saved = [r for r, good in zip(rows, ok) if good]
    failed = [r["source_id"] for r, good in zip(rows, ok) if not good]
    with connect() as conn, conn.cursor() as cur:
        cur.executemany(UPSERT_SQL, saved)
        cur.execute("delete from artworks where source = 'nga' and source_id = any(%s)", (failed,))
    print(f"done: {len(saved)} NGA paintings saved, {len(failed)} skipped (image unavailable)")


if __name__ == "__main__":
    ingest()
