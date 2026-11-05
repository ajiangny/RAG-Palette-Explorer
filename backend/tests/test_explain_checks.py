import pytest

from app import rag
from eval.explain_checks import check, sentence_spans
from eval.explanations import assign_splits, edge_stratum, paired_change

SOURCES = [
    {"n": 1, "title": "The Bedroom", "url": "u1",
     "content": "He painted “the walls pale lilac”. The artist understood it as a calming and restful image."},
    {"n": 2, "title": "Seurat", "url": "u2",
     "content": "These are in gay, calm or sad combinations. He paints the smell of the earth, a clear & bea[u]tiful "
                "effect in an other worldly realm."},
]


def make_run(answer, *, raw=None, kind="edge_painting", upload=False, sources=SOURCES):
    return {
        "id": "x", "kind": kind, "answer": answer, "raw_answer": answer if raw is None else raw, "sources": sources,
        "facts": {
            "has_upload": upload,
            "palettes": [[{"hex": "#a37918", "weight": 0.179}, {"hex": "#778ca3", "weight": 0.265}],
                         [{"hex": "#91774d", "weight": 0.3}, {"hex": "#7d8f96", "weight": 0.2}]],
            "titles": ["The Bedroom", "Haystacks", "Landsape with Waterfall", 'Scenes from Dante\'s "Inferno" (recto)'], "artists": ["Georges Seurat"],
            "palette_distance": 11.95,
            "matched_colors": [{"a": "#a37918", "b": "#91774d", "share": 0.179, "delta_e": 9.8}],
        },
    }


def found(answer, **kwargs):
    return [f["check"] for f in check(make_run(answer, **kwargs))["findings"] if f["severity"] == "error"]


@pytest.mark.parametrize("answer", [
    "The match #a37918 ↔ #91774d has ΔE 9.8 at a palette distance of 12.0 [1].",
    "The pair (#91774d ↔ #a37918, ΔE 10) is close, with palette distance 11.95 [1].",  # either order, rounded
    "#778ca3 (27%) dominates [1].",
    'He described "the walls pale lilac" [1].',
    'It was “a calming and restful image,” he wrote [1].',  # comma inside the quote, curly quotes
    'He called it "calming ... image" [1].',
    'In "The Bedroom" and "Haystacks" the colors agree [1].',  # titles aren't source quotes
    'Refers to "calm" tones [2].',
    'A "clear & beautiful effect" [2].',  # the source's editorial brackets
    'The "The Bedroom\'s" colors [1].',  # possessive title
    'In "Landscape with Waterfall" the grays agree [1].',  # corrects a typo in the museum record
    'An "other-worldly" realm [2].',  # hyphen only
    """In "Scenes from Dante's 'Inferno'" the colors agree [1].""",  # nested quotes, partial title
    "Van Gogh's #a37918 and Seurat's #91774d (18% share, ΔE 9.8) agree [1].",
    "#a37918 and #91774d differ by a ΔE of only 9.8 [1].",
    "These differ by ΔE below 5 [1].",  # a comparison, not a stated value
    "#a37918 and #778ca3 align with #91774d and #7d8f96 (ΔE 9.8, respectively) [1].",  # crossed pairs
])
def test_accurate_text_passes(answer):
    assert found(answer) == []


@pytest.mark.parametrize("answer, expected", [
    ("#123456 dominates [1].", "unknown_hex"),
    ("#a37918 ↔ #7d8f96 are linked [1].", "unmatched_pair"),
    ("#a37918 ↔ #91774d has ΔE 3.1 [1].", "wrong_delta_e"),
    ("The colors differ by ΔE 3.1 [1].", "wrong_delta_e"),
    ("Van Gogh's #a37918 and Seurat's #91774d (18% share, ΔE 3.1) agree [1].", "wrong_delta_e"),
    ("A ΔE of only 3.1 [1].", "wrong_delta_e"),
    ("#778ca3 and #7d8f96 differ by ΔE 3.1 [1].", "wrong_delta_e"),  # not a matched pair, and no value fits
    ('He would "paint the smell of the earth" [2].', "quote_altered"),
    ("The palette distance of 30.0 shows it [1].", "wrong_distance"),
    ("#778ca3 (60%) dominates [1].", "wrong_share"),
    ('He praised "emotional truth" [1].', "quote_not_found"),
    ('He praised "gay, calm or sad" tones [1].', "quote_wrong_source"),
    ('He praised "gay, calm or sad" tones.', "quote_uncited"),
    ("This lifts your image [1].", "phantom_upload"),
    ("Painting A is warm [1].", "label_leak"),
])
def test_each_error_is_caught(answer, expected):
    assert expected in found(answer)


def test_one_word_quote_needs_the_whole_word():
    source = [{"n": 1, "title": "t", "url": "u", "content": "a calming image"}]
    assert found('It was "calm" [1].', sources=source) == ["quote_not_found"]


def test_citation_in_another_sentence_does_not_count():
    assert found('He praised "gay, calm or sad" tones. Later work differs [2].') == ["quote_uncited"]


def test_uploads_may_say_your_image_and_matches_may_use_labels():
    assert found("This lifts your image [1].", upload=True) == []
    assert found("Painting A is warm [1].", kind="matches", upload=True) == []


def test_invented_citations_are_caught_from_the_raw_answer_after_cleanup_removed_them():
    assert found("Monet used color [1].", raw="Monet used color [1][7].") == ["invented_citation"]


def test_sentence_without_citation_or_palette_data_is_only_a_warning():
    findings = check(make_run("Monet loved water lilies. #a37918 is warm."))["findings"]
    assert {(f["check"], f["severity"]) for f in findings} == {("uncited_sentence", "warning"), ("no_citations", "warning")}
    assert [f["detail"] for f in findings if f["check"] == "uncited_sentence"] == ["Monet loved water lilies."]


def test_run_without_sources_has_nothing_to_check():
    assert check(make_run(rag.NO_SOURCES_ANSWER, raw="", sources=[])) == {"findings": [], "counts": {"no_sources": 1}}


def test_empty_answer_is_an_error():
    assert found("", raw="") == ["empty_answer"]


@pytest.mark.parametrize("text, n", [
    ("One thing [1]. Another thing [2].", 2),
    ("J. M. W. Turner lived near St. Ives in c. 1830. Next one.", 2),
    ('He said "done." Then he left.', 2),
    ("ΔE 9.8 is small.\n\nNew paragraph", 2),
    ("One thing. [1][2] Another.", 2),
])
def test_sentence_spans(text, n):
    assert len(sentence_spans(text)) == n


def test_trailing_citation_stays_with_its_sentence():
    text = "One thing. [1][2] Another."
    a, b = sentence_spans(text)[0]
    assert text[a:b] == "One thing. [1][2]"


@pytest.mark.parametrize("source, target, expected", [
    ({"description": True, "wiki": False}, {"description": False, "wiki": True}, "rich"),
    ({"description": False, "wiki": True}, {"description": False, "wiki": True}, "wiki_only"),
    ({"description": True, "wiki": True}, {"description": False, "wiki": False}, "one_sided"),
    ({"description": False, "wiki": False}, {"description": False, "wiki": False}, "no_text"),
])
def test_edge_stratum(source, target, expected):
    assert edge_stratum(source, target) == expected


def test_assign_splits_alternates():
    assert [i["split"] for i in assign_splits([{}, {}, {}])] == ["dev", "test", "dev"]


def test_spelling_variants_are_not_altered_quotes():
    source = [{"n": 1, "title": "t", "url": "u", "content": "soft colour and grey tones"}]
    assert found('It has "soft color and gray tones" [1].', sources=source) == []


def test_paired_change_uses_only_shared_items_and_detects_a_consistent_drop():
    before, after, low, high, n = paired_change({"a": 2.0, "b": 2.0, "c": 2.0, "gone": 9.0}, {"a": 1.0, "b": 1.0, "c": 1.0})
    assert (before, after, low, high, n) == (2.0, 1.0, -1.0, -1.0, 3)
