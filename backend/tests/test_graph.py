import pytest
from fastapi.testclient import TestClient

import app.main
from app.graph import UPLOAD_ID, expand
from app.retrieve import matched_colors
from tests.test_retrieve import BLUE, NAVY, RED, swatch

# Toy collection: node -> ranked neighbors (id, score, artist). Artist of node n is ARTIST[n].
ARTIST = {1: "A", 2: "B", 3: "A", 4: "A", 5: "C", 6: "D", 7: "E", 8: "B", 9: None, 10: None}
LINKS = {
    1: [2, 3, 4, 5],
    2: [1, 8, 6, 3],
    3: [4, 7, 1],
    4: [3, 1, 9],
    5: [10, 6],
    6: [5, 2],
}


def lookup(ids):
    return {i: [(n, 1.0 - 0.1 * r, ARTIST[n]) for r, n in enumerate(LINKS.get(i, []))] for i in ids}


def run(center=1, k=2, depth=2, cap=2):
    return expand(center, ARTIST.get(center), lookup([center]).get(center, []), lookup,
                  k=k, depth=depth, max_per_artist=cap)


def test_depth_one_takes_top_k():
    depth_of, edges = run(k=2, depth=1)
    assert depth_of == {1: 0, 2: 1, 3: 1}
    assert set(edges) == {(1, 2), (1, 3)}


def test_artist_cap_skips_to_next_neighbor():
    # Center is artist A and 3 is also A, so 4 (a third A) is skipped in favor of 5.
    depth_of, _ = run(k=3, depth=1)
    assert depth_of == {1: 0, 2: 1, 3: 1, 5: 1}


def test_depth_two_with_cross_links_and_no_duplicates():
    depth_of, edges = run(k=2, depth=2)
    # Ring 2: 2 → 8 (B, ok) and 6; 3 → 4 is a third "A" → skipped, then 7.
    assert depth_of == {1: 0, 2: 1, 3: 1, 8: 2, 6: 2, 7: 2}
    # 2's top-2 includes 1 (already present) → cross-link kept once, undirected.
    assert edges[(1, 2)] == pytest.approx(1.0)
    assert (2, 8) in edges and (3, 7) in edges
    assert len(edges) == len(set(edges))


def test_null_artist_is_not_capped_and_upload_center_works():
    first = [(9, 0.9, None), (10, 0.8, None), (5, 0.7, "C")]
    depth_of, edges = expand(UPLOAD_ID, None, first, lookup, k=3, depth=1)
    assert depth_of == {UPLOAD_ID: 0, 9: 1, 10: 1, 5: 1}
    assert all(UPLOAD_ID in e for e in edges)


def test_max_nodes_caps_the_web():
    depth_of, _ = expand(1, "A", lookup([1])[1], lookup, k=6, depth=3, max_per_artist=10, max_nodes=4)
    assert len(depth_of) == 4


def test_matched_colors_reports_the_transport_pairs():
    p = [swatch(RED, 0.7), swatch(BLUE, 0.3)]
    q = [swatch(RED, 0.6), swatch(NAVY, 0.4)]
    for s, h in zip(p + q, ["#red", "#blue", "#red2", "#navy"]):
        s["hex"] = h
    pairs = matched_colors(p, q)
    assert pairs[0] == {"a": "#red", "b": "#red2", "share": 0.6, "delta_e": 0.0}
    assert {(x["a"], x["b"]) for x in pairs} == {("#red", "#red2"), ("#blue", "#navy"), ("#red", "#navy")}
    assert sum(x["share"] for x in pairs) == pytest.approx(1.0, abs=1e-3)


@pytest.mark.parametrize("body", [
    {"target_id": 1},                                   # no source
    {"target_id": 1, "source_id": 1},                   # self-edge
    {"target_id": 1, "source_id": 2,
     "source_palette": [{"lab": [50, 0, 0], "hex": "#777777", "weight": 1}]},  # both sources
])
def test_explain_edge_validation(body):
    assert TestClient(app.main.app).post("/explain-edge", json=body).status_code == 422
