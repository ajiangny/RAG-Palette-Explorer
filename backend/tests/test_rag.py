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
