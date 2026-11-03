import random

import pytest

from eval.label import recheck_lines, rule_text, sample_recheck, split_recheck

LABELS = {"a.jpg": {"1": True, "2": False, "3": True}, "b.jpg": {"4": False, "5": True, "6": False}}


def test_sample_is_balanced_and_only_uses_eligible_paintings():
    picked = sample_recheck(LABELS, {1, 2, 3, 4, 5, 6}, 4, random.Random(0))
    assert sum(p["old"] for p in picked) == 2 and len(picked) == 4
    assert {p["id"] for p in sample_recheck(LABELS, {1, 2}, 4, random.Random(0))} == {1, 2}


def test_sample_keeps_the_requested_size_when_one_class_runs_short():
    labels = {"a.jpg": {"1": True, "2": False, "3": False, "4": False}}
    assert len(sample_recheck(labels, {1, 2, 3, 4}, 4, random.Random(0))) == 4


def test_recheck_answers_never_reach_the_merged_labels():
    recheck = [{"query": "a.jpg", "id": 1, "old": True}]
    fresh, answers = split_recheck({"a.jpg": {"1": False, "9": True}}, recheck)
    assert fresh == {"a.jpg": {"9": True}}
    assert answers == [{"query": "a.jpg", "id": 1, "old": True, "new": False}]


def test_missing_recheck_answer_stops_scoring():
    with pytest.raises(SystemExit):
        split_recheck({"a.jpg": {"9": True}}, [{"query": "a.jpg", "id": 1, "old": True}])


def test_summary_counts_flips_in_each_direction():
    text = recheck_lines([{"old": True, "new": True}, {"old": True, "new": False},
                          {"old": False, "new": True}, {"old": False, "new": False}])[0]
    assert "2 of 4 (50%) kept" in text
    assert "1 of 2 poor became good and 1 of 2 good became poor" in text
    assert recheck_lines([]) == []


def test_page_rule_keeps_the_rule_and_leaves_out_the_committed_decision():
    text = rule_text()
    assert "good only if all three are true" in text and "mark it poor" in text
    assert "**" not in text and "Committed decision" not in text and "--recheck" not in text
