"""Build the citation corpus: Wikipedia artist articles + AIC artwork descriptions.

Usage (from backend/):
    python -m ingest.wiki

Resumable: artists that already have Wikipedia chunks and artworks whose
description is already stored are skipped.

Only Wikipedia chunks are embedded. On Gemini's free tier every text embedded counts
as one request (1,000/day), so descriptions, which /explain fetches by artwork id,
are stored without an embedding, and articles are packed into a few large chunks.
"""

import re
import time
import unicodedata

import httpx

from app.db import connect
from app.gemini import DailyQuotaExceeded, embed
from ingest.aic import get_with_retry

WIKI_API = "https://en.wikipedia.org/w/api.php"
MUSEUMS = {"aic": "Art Institute of Chicago", "cma": "Cleveland Museum of Art", "nga": "National Gallery of Art"}
HEADERS = {"User-Agent": "palette-rag-explorer/0.1 (andrewjiang74@gmail.com)"}
REQUEST_DELAY = 0.5

CHUNK_CHARS = 3500  # ≈ 900 tokens; gemini-embedding-001 accepts up to 2,048
MAX_CHUNKS_PER_ARTICLE = 8  # /explain uses the top 3 per artist
SKIP_SECTIONS = {"references", "external links", "see also", "further reading", "notes",
                 "bibliography", "sources", "citations", "gallery", "footnotes",
                 "selected works", "list of works", "works cited", "exhibitions"}
# Sections most likely to talk about color; kept first when an article is long.
PRIORITY_SECTIONS = re.compile(r"style|technique|method|colou?r|palette|light|brush|painting|works?\b", re.IGNORECASE)
# The article lead must look like it is about an artist (AIC's artist field
# sometimes holds a culture, e.g. "Islamic" → the article on Islam).
ARTIST_WORDS = re.compile(r"\b(painter|artist|printmaker|illustrator|draughtsman|draftsman|"
                          r"sculptor|calligrapher|muralist|watercolou?rist)\b", re.IGNORECASE)
# The named artist didn't paint this ("Follower of Titian", "Workshop of Titian") or the name is
# only a guess, so that artist's biography would misdescribe the painting. "Attributed to X" and
# "X and Workshop" still credit X, so they keep their article.
NOT_BY_NAMED_ARTIST = re.compile(r"\b(after|follower|imitator|circle|style|manner|school|assistant|possibly|probably|copy)\b"
                                 r"|(?<!and )\b(workshop|studio)\b", re.IGNORECASE)


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
    parts = re.split(r"^(={2,})\s*(.+?)\s*\1\s*$", text, flags=re.MULTILINE)
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
    """Chunks of one article, each prefixed with its top-level section, color-relevant sections first.

    Subsections are packed together under their top-level heading so chunks come out
    near CHUNK_CHARS instead of one small chunk per subsection.
    """
    groups: dict[str, tuple[list[str], bool]] = {}
    for heading, body in split_sections(text):
        top = heading.split(" / ")[0]
        paras, prio = groups.setdefault(top, ([], False))
        paras.extend(p.strip() for p in body.split("\n") if len(p.strip()) > 40)
        groups[top] = (paras, prio or bool(heading and PRIORITY_SECTIONS.search(heading)))
    lead, prio_chunks, rest = [], [], []
    for top, (paras, prio) in groups.items():
        chunks = [f"[{top}] {c}" if top else c for c in pack(paras, CHUNK_CHARS - len(top) - 3)]
        (lead if not top else prio_chunks if prio else rest).extend(chunks)
    return (lead + prio_chunks + rest)[:MAX_CHUNKS_PER_ARTICLE]


INSERT_SQL = """
insert into text_chunks (artwork_id, artist, source_title, source_url, content, embedding)
values (%s, %s, %s, %s, %s, %s)
on conflict (source_url, md5(content)) do nothing
"""


def ingest_wikipedia() -> bool:
    """Returns False if it stopped early on the daily embedding quota."""
    with connect() as conn:
        artists = [r[0] for r in conn.execute("""
            select distinct a.artist from artworks a
            where a.artist is not null
              and not exists (select 1 from text_chunks c
                              where c.artist = a.artist and c.artwork_id is null)
            order by 1""")]
    skipped = [a for a in artists if NOT_BY_NAMED_ARTIST.search(a)]
    artists = [a for a in artists if not NOT_BY_NAMED_ARTIST.search(a)]
    print(f"{len(artists)} artists to fetch ({len(skipped)} skipped: not by the named artist)", flush=True)
    found = 0
    with httpx.Client(headers=HEADERS, timeout=30) as client:
        for n, artist in enumerate(artists, 1):
            article = fetch_article(client, artist)
            if not article:
                print(f"[{n}/{len(artists)}] {artist}: no artist article", flush=True)
                continue
            title, url, text = article
            chunks = chunk_article(text)
            try:
                vectors = embed([f"{title}\n{c}" for c in chunks])
            except DailyQuotaExceeded:
                print(f"daily embedding quota reached with {len(artists) - n + 1} artists left; "
                      "re-run after midnight Pacific to resume", flush=True)
                return False
            with connect() as conn, conn.cursor() as cur:
                cur.executemany(INSERT_SQL, [(None, artist, f"{title} — Wikipedia", url, c, v)
                                             for c, v in zip(chunks, vectors)])
            found += 1
            print(f"[{n}/{len(artists)}] {artist} → {title}: {len(chunks)} chunks", flush=True)
    print(f"wikipedia: {found}/{len(artists)} artists matched")
    return True


def ingest_descriptions() -> None:
    with connect() as conn:
        rows = conn.execute("""
            select a.id, a.source, a.source_url, a.title, a.artist, a.description from artworks a
            where a.description is not null
              and not exists (select 1 from text_chunks c where c.artwork_id = a.id)
            order by a.id""").fetchall()
    # No embedding: /explain looks these up by artwork_id, never by vector search.
    docs = [(art_id, artist, f"{title} — {MUSEUMS[source]}", source_url, chunk, None)
            for art_id, source, source_url, title, artist, desc in rows
            for chunk in pack([desc])]
    with connect() as conn, conn.cursor() as cur:
        cur.executemany(INSERT_SQL, docs)
    print(f"{len(rows)} museum descriptions stored", flush=True)


if __name__ == "__main__":
    ingest_descriptions()
    ingest_wikipedia()
    with connect() as conn:
        print("text_chunks:", conn.execute(
            "select count(*), count(distinct artist), count(*) filter (where embedding is null) from text_chunks"
        ).fetchone(), "(rows, artists, null embeddings)")
