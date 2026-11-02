"""Palette web: breadth-first expansion outward from a center over palette-similarity edges.

The center is either a painting in the collection (neighbors come from the precomputed
`artwork_edges` table) or an uploaded image (its first ring is computed live).
"""

from collections import Counter
from collections.abc import Callable, Hashable, Sequence
from typing import Any

import psycopg

from app.palette import ImageInput
from app.retrieve import live_neighbors, match_image

# (artwork id, edge score, artist)
Neighbor = tuple[int, float, str | None]
Lookup = Callable[[list[int]], dict[int, list[Neighbor]]]

UPLOAD_ID = "upload"
EDGES_PER_NODE = 20  # stored per painting; spare room for the artist cap and already-seen nodes
MAX_NODES = 150


def _edge_key(a: Hashable, b: Hashable) -> tuple[Hashable, Hashable]:
    return (a, b) if str(a) <= str(b) else (b, a)


def expand(center: Hashable, center_artist: str | None, first_ring: Sequence[Neighbor],
           lookup: Lookup, k: int = 6, depth: int = 2, max_per_artist: int = 2,
           max_nodes: int = MAX_NODES) -> tuple[dict[Hashable, int], dict[tuple, float]]:
    """BFS: each node links to its top-k unseen neighbors, subject to a per-artist cap.

    Returns ({node: depth}, {(a, b): score}). Edges between nodes already in the web are kept
    as cross-links when they are within a node's top k, which is what makes it a web, not a tree.
    """
    depth_of: dict[Hashable, int] = {center: 0}
    per_artist = Counter([center_artist] if center_artist else [])
    edges: dict[tuple, float] = {}

    def link(a, b, score):
        key = _edge_key(a, b)
        edges[key] = max(edges.get(key, 0.0), score)

    frontier: list[Hashable] = [center]
    neighbors: dict[Hashable, Sequence[Neighbor]] = {center: first_ring}
    for level in range(1, depth + 1):
        if level > 1:
            neighbors = dict(lookup([n for n in frontier if isinstance(n, int)]))
        next_frontier = []
        for node in frontier:
            added = 0
            for rank, (nid, score, artist) in enumerate(neighbors.get(node, ())):
                if nid == node:
                    continue
                if nid in depth_of:
                    if rank < k:
                        link(node, nid, score)
                    continue
                if added == k or len(depth_of) >= max_nodes:
                    continue
                if artist and per_artist[artist] >= max_per_artist:
                    continue
                depth_of[nid] = level
                per_artist[artist] += bool(artist)
                link(node, nid, score)
                next_frontier.append(nid)
                added += 1
        frontier = next_frontier
    return depth_of, edges


EDGES_SQL = """
select e.source_id, e.target_id, e.score, a.artist
from artwork_edges e join artworks a on a.id = e.target_id
where e.source_id = any(%s) and e.kind = 'palette'
order by e.source_id, e.score desc
"""


def _as_neighbors(results: list[dict[str, Any]]) -> list[Neighbor]:
    return [(r["id"], r["score"], r["artist"]) for r in results]


def db_lookup(conn: psycopg.Connection) -> Lookup:
    """Neighbors from `artwork_edges`, falling back to a live computation for unindexed paintings."""
    def lookup(ids: list[int]) -> dict[int, list[Neighbor]]:
        out: dict[int, list[Neighbor]] = {i: [] for i in ids}
        for src, tgt, score, artist in conn.execute(EDGES_SQL, (ids,)):
            out[src].append((tgt, score, artist))
        for i in ids:
            if not out[i]:
                out[i] = _as_neighbors(live_neighbors(conn, i, EDGES_PER_NODE))
        return out
    return lookup


NODE_SQL = """
select id, aic_id, title, artist, date, style, image_url, palette
from artworks where id = any(%s)
"""
NODE_FIELDS = ("id", "aic_id", "title", "artist", "date", "style", "image_url", "palette")


def _to_response(conn: psycopg.Connection, center: Hashable, depth_of: dict[Hashable, int],
                 edges: dict[tuple, float], upload_node: dict[str, Any] | None = None) -> dict[str, Any]:
    ids = [n for n in depth_of if isinstance(n, int)]
    nodes = {r[0]: dict(zip(NODE_FIELDS, r)) for r in conn.execute(NODE_SQL, (ids,))}
    if upload_node:
        nodes[UPLOAD_ID] = upload_node
    return {
        "center": center,
        "nodes": [{**nodes[n], "depth": d} for n, d in depth_of.items() if n in nodes],
        "edges": [{"source": a, "target": b, "kind": "palette", "score": s}
                  for (a, b), s in edges.items() if a in nodes and b in nodes],
    }


def graph_for_artwork(conn: psycopg.Connection, artwork_id: int, k: int = 6,
                      depth: int = 2) -> dict[str, Any] | None:
    row = conn.execute("select artist from artworks where id = %s", (artwork_id,)).fetchone()
    if row is None:
        return None
    lookup = db_lookup(conn)
    depth_of, edges = expand(artwork_id, row[0], lookup([artwork_id])[artwork_id], lookup, k, depth)
    return _to_response(conn, artwork_id, depth_of, edges)


def graph_for_upload(conn: psycopg.Connection, image: ImageInput, k: int = 6,
                     depth: int = 2) -> dict[str, Any]:
    palette, first = match_image(conn, image, k=EDGES_PER_NODE)
    depth_of, edges = expand(UPLOAD_ID, None, _as_neighbors(first), db_lookup(conn), k, depth)
    upload_node = {"id": UPLOAD_ID, "title": "Your image", "artist": None, "palette": palette}
    return _to_response(conn, UPLOAD_ID, depth_of, edges, upload_node)
