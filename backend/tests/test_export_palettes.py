from ingest.export_palettes import TITLE_CHARS, compact


def test_compact_sorts_by_weight_and_strips_hashes():
    rows = [(7, "Haystacks", [
        {"hex": "#112233", "weight": 0.2, "lab": [1, 2, 3]},
        {"hex": "#aabbcc", "weight": 0.8, "lab": [4, 5, 6]},
    ])]
    assert compact(rows) == [{"id": 7, "t": "Haystacks", "c": "aabbcc112233", "w": [0.8, 0.2]}]


def test_compact_handles_missing_and_long_titles():
    palette = [{"hex": "#000000", "weight": 1.0}]
    untitled, long = compact([(1, None, palette), (2, "x" * 500, palette)])
    assert untitled["t"] == "Untitled"
    assert len(long["t"]) == TITLE_CHARS
