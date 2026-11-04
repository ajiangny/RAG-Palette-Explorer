"""Write every searchable painting's palette to a static file for client-side scoring.

The browser scores these palettes on every palette edit, so it needs them without a network call.
Rerun after the collection changes. From backend/: python -m ingest.export_palettes
"""

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.db import connect

OUT = Path(__file__).resolve().parents[2] / "frontend" / "public" / "palettes.json"
TITLE_CHARS = 80

SQL = "select id, title, palette from artworks where hist is not null and excluded is null order by id"


def compact(rows: Iterable[tuple[int, str | None, list[dict[str, Any]]]]) -> list[dict[str, Any]]:
    """One entry per painting: colors as hex strings, heaviest first, with matching weights."""
    items = []
    for artwork_id, title, palette in rows:
        swatches = sorted(palette, key=lambda s: s["weight"], reverse=True)
        items.append({
            "id": artwork_id,
            "t": (title or "Untitled")[:TITLE_CHARS],
            "c": "".join(s["hex"].lstrip("#") for s in swatches),
            "w": [round(s["weight"], 3) for s in swatches],
        })
    return items


def main() -> None:
    with connect() as conn:
        items = compact(conn.execute(SQL))
    OUT.write_text(json.dumps({"items": items}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(items)} paintings, {OUT.stat().st_size / 1024:.0f} KB -> {OUT}")


if __name__ == "__main__":
    main()
