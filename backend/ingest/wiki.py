"""Build the citation corpus: Wikipedia artist articles + AIC artwork descriptions.

Usage (from backend/):
    python -m ingest.wiki

Resumable: artists that already have Wikipedia chunks and artworks whose
description is already stored are skipped.
"""

import re
import time
import unicodedata

import httpx

from app.db import connect
from app.gemini import embed
from ingest.aic import get_with_retry

WIKI_API = "https://en.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "palette-rag-explorer/0.1 (andrewjiang74@gmail.com)"}
REQUEST_DELAY = 0.5

CHUNK_CHARS = 2000  # ≈ 500 tokens
MAX_CHUNKS_PER_ARTICLE = 20
SKIP_SECTIONS = {"references", "external links", "see also", "further reading", "notes",
                 "bibliography", "sources", "citations", "gallery", "footnotes",
                 "selected works", "list of works", "works cited", "exhibitions"}
# Sections most likely to talk about color; kept first when an article is long.
PRIORITY_SECTIONS = re.compile(r"style|technique|method|colou?r|palette|light|brush|painting|works?\b", re.I)
# The article lead must look like it is about an artist (AIC's artist field
# sometimes holds a culture, e.g. "Islamic" → the article on Islam).
ARTIST_WORDS = re.compile(r"\b(painter|artist|printmaker|illustrator|draughtsman|draftsman|"
                          r"sculptor|calligrapher|muralist|watercolou?rist)\b", re.I)


def _norm_words(text: str) -> set[str]:
    text = unicodedata.normalize("NFKD", re.sub(r"\(.*?\)", " ", text))
    return set(re.findall(r"[a-z]+", text.encode("ascii", "ignore").decode().lower()))


def _get_page(client: httpx.Client, title: str) -> dict:
    r = get_with_retry(client, "GET", WIKI_API, params={
        "action": "query", "format": "json", "titles": title, "redirects": 1,
        "prop": "extracts|info|pageprops", "explaintext": 1, "exsectionformat": "wiki",
        "inprop": "url", "ppprop": "disambiguation",
    })
    r.raise_for_status()
    time.sleep(REQUEST_DELAY)
    return next(iter(r.json()["query"]["pages"].values()))


def _usable(page: dict) -> bool:
    text = page.get("extract") or ""
    if "missing" in page or "pageprops" in page or not text:
        return False
    return bool(ARTIST_WORDS.search(text.split("\n==", 1)[0][:1500]))


def fetch_article(client: httpx.Client, name: str) -> tuple[str, str, str] | None:
    """Return (title, url, plaintext) for the artist's article, or None if not found / not an artist.

    Tries the exact name first, then a search; a search hit only counts if every word of
    its title appears in the AIC name ("Joachim Antonisz. Wtewael" → "Joachim Wtewael").
    """
    page = _get_page(client, name)
    if not _usable(page):
        r = get_with_retry(client, "GET", WIKI_API, params={
            "action": "query", "format": "json", "list": "search",
            "srsearch": f"{name} artist", "srlimit": 3})
        r.raise_for_status()
        time.sleep(REQUEST_DELAY)
        name_words = _norm_words(name)
        hits = [h["title"] for h in r.json()["query"]["search"]
                if _norm_words(h["title"]) and _norm_words(h["title"]) <= name_words]
        if not hits:
            return None
        page = _get_page(client, hits[0])
        if not _usable(page):
            return None
    return page["title"], page["fullurl"], page["extract"]


def split_sections(text: str) -> list[tuple[str, str]]:
    """Plaintext extract with `== Heading ==` markers → [(heading, body)], lead first as ''."""
    parts = re.split(r"^(={2,})\s*(.+?)\s*\1\s*$", text, flags=re.M)
    sections = [("", parts[0])]
    top = ""
    for i in range(1, len(parts) - 2, 3):
        level, heading, body = len(parts[i]), parts[i + 1], parts[i + 2]
        if level == 2:
            top = heading
        skip = top.lower() in SKIP_SECTIONS or heading.lower() in SKIP_SECTIONS
        sections.append(("" if skip else heading if level == 2 else f"{top} / {heading}", "" if skip else body))
    return [(h, b.strip()) for h, b in sections if b.strip()]


def pack(paragraphs: list[str], max_chars: int = CHUNK_CHARS) -> list[str]:
    """Greedily pack paragraphs into chunks ≤ max_chars (long paragraphs split on sentences)."""
    pieces = []
    for p in paragraphs:
        if len(p) <= max_chars:
            pieces.append(p)
        else:
            pieces.extend(pack(re.split(r"(?<=[.!?])\s+", p), max_chars) if " " in p
                          else [p[i:i + max_chars] for i in range(0, len(p), max_chars)])
    chunks, cur = [], ""
    for p in pieces:
        if cur and len(cur) + len(p) + 1 > max_chars:
            chunks.append(cur)
            cur = p
        else:
            cur = f"{cur}\n{p}" if cur else p
    if cur:
        chunks.append(cur)
    return chunks


def chunk_article(text: str) -> list[str]:
    """Chunks of one article, each prefixed with its section, color-relevant sections first."""
    chunks = []
    for heading, body in split_sections(text):
        paras = [p.strip() for p in body.split("\n") if len(p.strip()) > 40]
        for c in pack(paras, CHUNK_CHARS - len(heading) - 4):
            chunks.append((heading, f"[{heading}] {c}" if heading else c))
    lead = [c for h, c in chunks if not h]
    prio = [c for h, c in chunks if h and PRIORITY_SECTIONS.search(h)]
    rest = [c for h, c in chunks if h and not PRIORITY_SECTIONS.search(h)]
    return (lead + prio + rest)[:MAX_CHUNKS_PER_ARTICLE]


INSERT_SQL = """
insert into text_chunks (artwork_id, artist, source_title, source_url, content, embedding)
values (%s, %s, %s, %s, %s, %s)
on conflict (source_url, content) do nothing
"""


def ingest_wikipedia() -> None:
    with connect() as conn:
        artists = [r[0] for r in conn.execute("""
            select distinct a.artist from artworks a
            where a.artist is not null
              and not exists (select 1 from text_chunks c
                              where c.artist = a.artist and c.artwork_id is null)
            order by 1""")]
    print(f"{len(artists)} artists to fetch", flush=True)
    found = 0
    with httpx.Client(headers=HEADERS, timeout=30) as client:
        for n, artist in enumerate(artists, 1):
            article = fetch_article(client, artist)
            if not article:
                print(f"[{n}/{len(artists)}] {artist}: no artist article", flush=True)
                continue
            title, url, text = article
            chunks = chunk_article(text)
            vectors = embed([f"{title}\n{c}" for c in chunks])
            with connect() as conn, conn.cursor() as cur:
                cur.executemany(INSERT_SQL, [(None, artist, f"{title} — Wikipedia", url, c, v)
                                             for c, v in zip(chunks, vectors)])
            found += 1
            print(f"[{n}/{len(artists)}] {artist} → {title}: {len(chunks)} chunks", flush=True)
    print(f"wikipedia: {found}/{len(artists)} artists matched")


def ingest_descriptions() -> None:
    with connect() as conn:
        rows = conn.execute("""
            select a.id, a.aic_id, a.title, a.artist, a.description from artworks a
            where a.description is not null
              and not exists (select 1 from text_chunks c where c.artwork_id = a.id)
            order by a.id""").fetchall()
    print(f"{len(rows)} AIC descriptions to embed", flush=True)
    for i in range(0, len(rows), 50):
        batch = rows[i:i + 50]
        docs = [(art_id, artist, f"{title} — Art Institute of Chicago",
                 f"https://www.artic.edu/artworks/{aic_id}", chunk)
                for art_id, aic_id, title, artist, desc in batch
                for chunk in pack([desc])]
        vectors = embed([f"{d[2]}\n{d[4]}" for d in docs])
        with connect() as conn, conn.cursor() as cur:
            cur.executemany(INSERT_SQL, [(*d, v) for d, v in zip(docs, vectors)])
        print(f"{min(i + 50, len(rows))}/{len(rows)} descriptions", flush=True)


if __name__ == "__main__":
    ingest_wikipedia()
    ingest_descriptions()
    with connect() as conn:
        print("text_chunks:", conn.execute(
            "select count(*), count(distinct artist), count(*) filter (where embedding is null) from text_chunks"
        ).fetchone(), "(rows, artists, null embeddings)")
