import pytest
from google.genai import errors

from app import gemini
from ingest.wiki import CHUNK_CHARS, MAX_CHUNKS_PER_ARTICLE, chunk_article, pack


def para(word: str, n: int = 60) -> str:
    return " ".join([word] * n) + "."


ARTICLE = "\n".join([
    para("lead"),
    "== Life ==",
    "=== Early years ===",
    para("early"),
    "=== Later years ===",
    para("later"),
    "== Style ==",
    para("style"),
    "== References ==",
    para("refs"),
])


def test_subsections_pack_under_top_heading_and_priority_first():
    chunks = chunk_article(ARTICLE)
    assert len(chunks) == 3
    assert chunks[0].startswith("lead")
    assert chunks[1].startswith("[Style] style")
    assert chunks[2].startswith("[Life] early") and "later" in chunks[2]  # one chunk, not two
    assert not any("refs" in c for c in chunks)


def test_subsection_heading_can_mark_its_section_as_priority():
    text = "\n".join([para("lead"), "== Life ==", para("bio"), "== Career ==",
                      "=== Painting technique ===", para("tech")])
    chunks = chunk_article(text)
    assert chunks[1].startswith("[Career] tech")


def test_chunks_respect_size_and_count_caps():
    sections = "\n".join(f"== Section {i} ==\n" + "\n".join(para(f"w{i}", 200) for _ in range(5))
                         for i in range(10))
    chunks = chunk_article(para("lead") + "\n" + sections)
    assert len(chunks) == MAX_CHUNKS_PER_ARTICLE
    assert all(len(c) <= CHUNK_CHARS for c in chunks)


def test_pack_splits_long_paragraphs_on_sentences():
    long = " ".join(f"Sentence number {i} is here." for i in range(400))
    out = pack([long], max_chars=500)
    assert all(len(c) <= 500 for c in out)
    assert " ".join(out).replace("\n", " ") == long


def quota_error(quota_id: str) -> errors.ClientError:
    return errors.ClientError(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED",
                                              "message": f"Quota exceeded: {quota_id}"}})


def test_daily_quota_raises_immediately(monkeypatch):
    calls = []

    def fn():
        calls.append(1)
        raise quota_error("EmbedContentRequestsPerDayPerProjectPerModel-FreeTier")
    with pytest.raises(gemini.DailyQuotaExceeded):
        gemini._with_backoff(fn)
    assert len(calls) == 1


def test_per_minute_quota_is_retried(monkeypatch):
    monkeypatch.setattr(gemini.time, "sleep", lambda s: None)
    calls = []

    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise quota_error("EmbedContentRequestsPerMinutePerProjectPerModel-FreeTier")
        return "ok"
    assert gemini._with_backoff(fn) == "ok"
    assert len(calls) == 3
