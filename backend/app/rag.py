"""Cited explanations: retrieve text chunks for the matched artists, ask Gemini, validate citations."""

import re
from collections.abc import Sequence
from functools import cache
from typing import Any

import numpy as np
import psycopg

from app import gemini
from app.palette import Swatch
from app.retrieve import matched_colors, palette_distance

PER_ARTIST_CHUNKS = 3
MAX_ARTWORKS = 5
COLOR_QUERY = "The artist's use of color, palette, light and painting technique"
NO_SOURCES_ANSWER = ("No reference texts were found for these artists, so there is nothing to "
                     "cite about how they used color.")

SYSTEM_PROMPT = """You are an art historian explaining how painters used color.
Rules:
- Use ONLY the numbered sources for facts about artists, works, techniques or history.
- Cite every such claim inline with its source number, e.g. [2] or [1][3].
- The palettes (hex colors with pixel shares) are computed data; you may describe them without citation.
- If the sources say little or nothing about an artist's color use, say so plainly instead of guessing.
- Plain prose, no headings, no bullet lists, no bibliography at the end."""


def format_palette(palette: Sequence[Swatch]) -> str:
    return ", ".join(f"{s['hex']} ({s['weight'] * 100:.0f}%)" for s in palette)


def fetch_artworks(conn: psycopg.Connection, ids: Sequence[int]) -> list[dict[str, Any]]:
    rows = conn.execute(
        "select id, title, artist, date, style, image_url, palette from artworks where id = any(%s)",
        (list(ids),)).fetchall()
    by_id: dict[int, dict[str, Any]] = {
        r[0]: dict(zip(("id", "title", "artist", "date", "style", "image_url", "palette"), r))
        for r in rows
    }
    return [by_id[i] for i in ids if i in by_id]


@cache
def color_query_vector() -> np.ndarray:
    # Chunks are already filtered by artist, so one generic query works for all of them;
    # embedding it once per process keeps /explain off the embedding quota.
    return gemini.embed([COLOR_QUERY], task="RETRIEVAL_QUERY")[0]


def retrieve_sources(conn: psycopg.Connection, artworks: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """AIC descriptions of these exact artworks + the top color-related chunks per artist."""
    sources: dict[int, dict[str, Any]] = {}
    for r in conn.execute(
            "select id, source_title, source_url, content from text_chunks where artwork_id = any(%s)",
            ([a["id"] for a in artworks],)):
        sources[r[0]] = {"title": r[1], "url": r[2], "content": r[3]}

    for artist in dict.fromkeys(a["artist"] for a in artworks if a["artist"]):
        for r in conn.execute(
                "select id, source_title, source_url, content from match_chunks(%s::vector, %s, %s)",
                (color_query_vector(), [artist], PER_ARTIST_CHUNKS)):
            sources.setdefault(r[0], {"title": r[1], "url": r[2], "content": r[3]})
    return [{"n": n, **s} for n, s in enumerate(sources.values(), 1)]


CITATION = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


def clean_citations(text: str, n_sources: int) -> tuple[str, set[int]]:
    """Drop citation numbers that don't refer to a real source; return the cited set."""
    cited: set[int] = set()

    def fix(m: re.Match) -> str:
        nums = [int(x) for x in m.group(1).split(",") if 1 <= int(x) <= n_sources]
        cited.update(nums)
        return "".join(f"[{x}]" for x in nums)

    text = CITATION.sub(fix, text)
    return re.sub(r"[ \t]+([.,;:])", r"\1", re.sub(r"[ \t]{2,}", " ", text)).strip(), cited


def answer(context: str, task: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Ask Gemini to do `task` over `context` + numbered sources; return text + validated sources."""
    if not sources:
        return {"answer": NO_SOURCES_ANSWER, "sources": []}
    numbered = "\n\n".join(f"[{s['n']}] {s['title']} ({s['url']})\n{s['content']}" for s in sources)
    prompt = f"{context}\n\nSources:\n{numbered}\n\nTask: {task}"
    text, cited = clean_citations(gemini.generate(prompt, SYSTEM_PROMPT), len(sources))
    return {
        "answer": text,
        "sources": [{"n": s["n"], "title": s["title"], "url": s["url"], "cited": s["n"] in cited}
                    for s in sources],
    }


def describe_artwork(a: dict[str, Any]) -> str:
    who = a["artist"] or "unknown artist"
    when = f", {a['date']}" if a.get("date") else ""
    return f'"{a["title"]}" by {who}{when}; palette: {format_palette(a["palette"] or [])}'


def explain_matches(conn: psycopg.Connection, query_palette: Sequence[Swatch],
                    artwork_ids: Sequence[int]) -> dict[str, Any]:
    artworks = fetch_artworks(conn, artwork_ids[:MAX_ARTWORKS])
    context = (f"The user's image has this palette: {format_palette(query_palette)}\n\n"
               "Paintings with the most similar palettes:\n"
               + "\n".join(f"- {describe_artwork(a)}" for a in artworks))
    task = ("In 2–4 short paragraphs, explain how the artists of these paintings used color, "
            "and how that relates to the user's palette. Cite sources inline.")
    return {"artworks": [a["id"] for a in artworks], **answer(context, task, retrieve_sources(conn, artworks))}


def explain_edge(conn: psycopg.Connection, target_id: int, source_id: int | None = None,
                 source_palette: Sequence[Swatch] | None = None) -> dict[str, Any] | None:
    """Why two nodes of the web are linked. The source is a painting or the uploaded image's palette."""
    ids = [i for i in (source_id, target_id) if i is not None]
    artworks = fetch_artworks(conn, ids)
    if len(artworks) != len(ids):
        return None
    target = artworks[-1]
    if source_id is not None:
        palette_a, label_a = artworks[0]["palette"], f"Painting A: {describe_artwork(artworks[0])}"
    else:
        assert source_palette is not None
        palette_a, label_a = source_palette, f"Image A (the user's upload); palette: {format_palette(source_palette)}"
    distance = palette_distance(palette_a, target["palette"])
    pairs = matched_colors(palette_a, target["palette"])
    context = "\n".join([
        label_a,
        f"Painting B: {describe_artwork(target)}",
        f"Palette distance (weighted CIEDE2000, 0 = identical): {distance:.1f}",
        "Matched colors (A ↔ B, share of pixels, ΔE):",
        *(f"- {p['a']} ↔ {p['b']}, {p['share'] * 100:.0f}%, ΔE {p['delta_e']}" for p in pairs),
    ])
    task = ("In 1–2 short paragraphs, explain why A and B are linked by palette, referring to the "
            "matched colors, and how the artists' approaches to color compare. Cite sources inline. "
            "Refer to paintings by title and to an upload as \"your image\", never as A or B.")
    return {"source": source_id, "target": target_id, "palette_distance": round(distance, 3),
            "matched_colors": pairs, **answer(context, task, retrieve_sources(conn, artworks))}
