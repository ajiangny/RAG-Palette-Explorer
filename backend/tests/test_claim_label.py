import json
import random

from eval.claim_label import add_rechecks, build_page, pick_explanations, score, to_items


def make_run(run_id, stratum="rich", answer="One thing [1]. Two things.\n\nThird."):
    return {"id": run_id, "stratum": stratum, "answer": answer}


def test_to_items_keeps_context_and_citations():
    items = to_items(make_run("a"))
    assert [i["key"] for i in items] == ["a#0", "a#1", "a#2"]
    assert items[0]["sentence"].strip() == "One thing [1]."
    assert items[0]["cited"] == [1] and items[1]["cited"] == []
    assert items[1]["before"].strip() == "One thing [1]." and items[2]["before"] == ""


def test_pick_covers_every_group_and_stops_at_the_target():
    runs = [make_run(f"r{i}", "rich") for i in range(5)] + [make_run(f"w{i}", "wiki") for i in range(5)]
    picked = pick_explanations(runs, random.Random(0), 6)
    assert {r["stratum"] for r in picked} == {"rich", "wiki"}
    assert len(picked) == 2


def test_rechecks_come_after_the_gap_and_point_at_the_original():
    items = [{"key": str(i)} for i in range(100)]
    out = add_rechecks(items, random.Random(0), n=15, gap=40)
    copies = [i for i in out if "recheck_of" in i]
    assert len(out) == 115 and len(copies) == 15
    keys = [i["key"] for i in out]
    assert all(keys.index(c["key"]) - keys.index(c["recheck_of"]) > 40 for c in copies)


def test_score_uses_first_answers_and_ignores_no_claim():
    pool = {"runs_file": "f", "items": [
        {"key": "a#0", "explanation": "a", "cited": [1]},
        {"key": "a#1", "explanation": "a", "cited": [1]},
        {"key": "a#2", "explanation": "a", "cited": []},
        {"key": "b#0", "explanation": "b", "cited": [1]},
        {"key": "b#0~recheck", "explanation": "b", "cited": [1], "recheck_of": "b#0"},
    ]}
    labels = {"a#0": "supported", "a#1": "stretched", "a#2": "no_claim", "b#0": "supported", "b#0~recheck": "stretched"}
    text = score(pool, labels)
    assert "| Cited sentences that are supported | 67%" in text
    assert "| Sentences with a claim but no citation | 0 of 3 |" in text
    assert "| Fully supported explanations | 1 of 2 |" in text
    assert "Consistency: 0 of 1" in text


def test_page_cannot_be_broken_out_of_by_source_text():
    page = build_page({"items": [], "sources": {"a": [{"n": 1, "title": "</script><b>", "content": "x"}]}}, "rule")
    assert "</script><b>" not in page
    assert json.dumps("rule") in page
