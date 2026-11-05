import pytest

from app import rag
from app.rag import NO_SOURCES_ANSWER, answer, clean_citations, format_palette

SOURCES = [{"n": i, "title": f"T{i}", "url": f"https://example.org/{i}", "content": "text"}
           for i in (1, 2, 3)]


def test_format_palette():
    assert format_palette([{"lab": [0, 0, 0], "hex": "#112233", "weight": 0.314},
                           {"lab": [0, 0, 0], "hex": "#ffffff", "weight": 0.686}]) == "#112233 (31%), #ffffff (69%)"


@pytest.mark.parametrize("text, expected, cited", [
    ("Monet used broken color [1].", "Monet used broken color [1].", {1}),
    ("Both did [1, 3].", "Both did [1][3].", {1, 3}),
    ("Invented [7].", "Invented.", set()),
    ("Mixed [2, 9][3] here.", "Mixed [2][3] here.", {2, 3}),
    ("No citations.", "No citations.", set()),
])
def test_clean_citations(text, expected, cited):
    assert clean_citations(text, 3) == (expected, cited)


def test_answer_without_sources_does_not_call_gemini(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("should not be called")
    monkeypatch.setattr(rag.gemini, "generate", boom)
    assert answer("ctx", "task", []) == {"answer": NO_SOURCES_ANSWER, "sources": []}


def test_answer_validates_citations_and_flags_cited_sources(monkeypatch):
    seen = {}

    def fake_generate(prompt, system):
        seen["prompt"] = prompt
        return "Van Gogh used complementary contrasts [2]. Also [5]."
    monkeypatch.setattr(rag.gemini, "generate", fake_generate)

    out = answer("palette ctx", "explain", SOURCES)
    assert out["answer"] == "Van Gogh used complementary contrasts [2]. Also."
    assert [s["cited"] for s in out["sources"]] == [False, True, False]
    assert all(s["url"].startswith("https://") for s in out["sources"])
    assert "[3] T3 (https://example.org/3)" in seen["prompt"]
    assert seen["prompt"].startswith("palette ctx")


def test_trace_keeps_source_text_and_raw_answer_but_the_response_does_not(monkeypatch):
    monkeypatch.setattr(rag.gemini, "generate", lambda prompt, system: "Claim [1]. Invented [9].")
    trace = {}
    out = answer("ctx", "task", SOURCES, trace)
    assert trace["raw_answer"] == "Claim [1]. Invented [9]."
    assert trace["sources"][0]["content"] == "text"
    assert (trace["context"], trace["task"]) == ("ctx", "task")
    assert "content" not in out["sources"][0]
    assert out["answer"] == "Claim [1]. Invented."


def test_trace_records_a_run_with_no_sources():
    trace = {}
    answer("ctx", "task", [], trace)
    assert trace["raw_answer"] is None and trace["sources"] == []


@pytest.mark.parametrize("source_id, source_palette, mentions_upload", [
    (1, None, False),
    (None, [{"lab": [50, 0, 0], "hex": "#777777", "weight": 1.0}], True),
])
def test_edge_prompt_only_mentions_your_image_for_an_upload(monkeypatch, source_id, source_palette, mentions_upload):
    palette = [{"lab": [50, 0, 0], "hex": "#777777", "weight": 1.0}]
    art = {"id": 2, "title": "T", "artist": "X", "date": None, "palette": palette}
    monkeypatch.setattr(rag, "fetch_artworks", lambda conn, ids: [{**art, "id": i} for i in ids])
    monkeypatch.setattr(rag, "retrieve_sources", lambda conn, artworks: SOURCES)
    monkeypatch.setattr(rag.gemini, "generate", lambda prompt, system: "Claim [1].")
    trace = {}
    rag.explain_edge(None, 2, source_id=source_id, source_palette=source_palette, trace=trace)
    assert ("your image" in trace["task"]) is mentions_upload
    assert "never as A or B" in trace["task"]
