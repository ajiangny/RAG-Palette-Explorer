"""Checks on a saved explanation that need no AI: numbers, quotes, and wording against what the model was given.

These catch mechanical errors only. A claim can pass every check here and still misread its source.

`check(run)` takes one record from eval/explain_runs.jsonl and returns its findings. Severity:
    error    the text contradicts the record, or breaks a rule the prompt states
    warning  worth a look, but can be legitimate (a sentence with no citation may just describe a palette)
"""

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

from app.rag import CITATION

HEX = r"#[0-9a-fA-F]{6}\b"
NUMBER = r"(\d+(?:\.\d+)?)"
# "ΔE of only 4.3" states a value. "ΔE below 5" doesn't, so it isn't matched.
DELTA_E = r"(?:ΔE|Delta[- ]E)(?:\s+(?:of|at|is)|\s*[=:≈~])?(?:\s*(?:only|just|about|roughly|around|approximately))?\s*"
ARROW = r"(?:↔|<->|<=>|→|->)"

ARROW_PAIR = re.compile(rf"({HEX})\s*{ARROW}\s*({HEX})")
# Two hex codes close together, then a ΔE: "Jarvis's #4d4941 and Lawrence's #4c493c (15% share, ΔE 2.4)".
GAP = r"(?:[^#.]|\.\d)"
PAIR_DELTA = re.compile(rf"({HEX}){GAP}{{0,50}}?({HEX}){GAP}{{0,40}}?{DELTA_E}{NUMBER}", re.IGNORECASE)
ANY_DELTA = re.compile(rf"{DELTA_E}{NUMBER}", re.IGNORECASE)
SHARE = re.compile(rf"({HEX})\s*[,(]\s*(?:about\s+|roughly\s+|~)?{NUMBER}%", re.IGNORECASE)
DISTANCE = re.compile(rf"palette distance\b[^.\d#]{{0,25}}?{NUMBER}", re.IGNORECASE)
QUOTE = re.compile(r'“([^”]+)”|"([^"\n]+)"')
SENTENCE_END = re.compile(r'[.!?]["”’)]*(?:\s*\[\d+\])*(?=\s+[A-Z"“#(\[]|\s*$)')
ABBREVIATIONS = {"st", "mr", "mrs", "ms", "dr", "c", "ca", "no", "vs", "jr", "sr", "fig", "e.g", "i.e"}
PHANTOM_UPLOAD = re.compile(r"\byour (?:image|upload|photo|picture|palette)\b|\buser'?s (?:image|upload|palette)\b", re.IGNORECASE)
LABEL_LEAK = re.compile(r"\b(?:Painting|Image) [AB]\b|\bA and B\b")
SHARE_TOLERANCE = 1.0  # points; the prompt shows whole-number shares
ALTERED_RATIO = 0.8  # "paint the smell" vs "paints the smell" is altered; "calm" vs "calming" is not


def _hex(value: str) -> str:
    return value.lower()


def _close(said: str, actual: float, margin: float = 0.0) -> bool:
    """True if `said` is `actual` rounded to however many decimals `said` was written with."""
    decimals = len(said.split(".")[1]) if "." in said else 0
    return abs(float(said) - actual) <= 0.5 * 10 ** -decimals + margin + 1e-9


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    # Quote style, hyphens and editors' brackets ("bea[u]tiful") aren't changes to the wording.
    text = text.translate(str.maketrans({"‘": "'", "’": "'", "“": "'", "”": "'", '"': "'", "–": " ", "—": " ", "-": " "}))
    text = re.sub(r"\[(\w+)\]", r"\1", text)
    return re.sub(r"\s+", " ", text).lower()


def _contains(source: str, quote: str) -> bool:
    """Whole-word match, so "calm" isn't confirmed by "calming". Ellipses mean the parts appear in order."""
    position = 0
    for part in re.split(r"\.\.\.|…", quote):
        part = part.strip(" .,;:!?'()")
        if not part:
            continue
        match = re.compile(rf"(?<!\w){re.escape(part)}(?!\w)").search(source, position)
        if not match:
            return False
        position = match.end()
    return True


def _nearest(source: str, quote: str) -> tuple[float, str]:
    """The stretch of `source` most like `quote`, and how alike they are (0 to 1)."""
    words = source.split()
    size = len(quote.split())
    best = (0.0, "")
    for length in {max(1, size - 1), size, size + 1}:
        for i in range(max(0, len(words) - length + 1)):
            window = " ".join(words[i:i + length]).strip(" .,;:!?'()")
            ratio = SequenceMatcher(None, window, quote, autojunk=False).ratio()
            if ratio > best[0]:
                best = (ratio, window)
    return best


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """(start, end) per sentence, with trailing citations kept in the sentence they follow."""
    spans = []
    for paragraph in re.finditer(r"[^\n]+", text):
        start = paragraph.start()
        for match in SENTENCE_END.finditer(text, paragraph.start(), paragraph.end()):
            words = text[start:match.start()].split()
            last = words[-1].lower().lstrip("(\"“") if words else ""
            if last in ABBREVIATIONS or re.fullmatch(r"[a-z]", last):  # "St. Ives", "J. M. W. Turner"
                continue
            spans.append((start, match.end()))
            start = match.end()
        if text[start:paragraph.end()].strip():
            spans.append((start, paragraph.end()))
    return spans


def _citations(text: str) -> set[int]:
    return {int(n) for group in CITATION.findall(text) for n in group.split(",")}


def _check_numbers(run: dict[str, Any], text: str) -> tuple[list[dict[str, str]], dict[str, int]]:
    facts = run["facts"]
    findings: list[dict[str, str]] = []

    def flag(check: str, detail: str) -> None:
        findings.append({"check": check, "severity": "error", "detail": detail})

    shares: dict[str, list[float]] = {}
    for palette in facts["palettes"]:
        for swatch in palette:
            shares.setdefault(_hex(swatch["hex"]), []).append(swatch["weight"] * 100)
    pairs: dict[frozenset[str], dict[str, float]] = {}
    for p in facts["matched_colors"]:
        pairs[frozenset((_hex(p["a"]), _hex(p["b"])))] = p
        for color in (p["a"], p["b"]):
            shares.setdefault(_hex(color), []).append(p["share"] * 100)

    mentioned = [_hex(h) for h in re.findall(HEX, text)]
    for color in dict.fromkeys(mentioned):
        if color not in shares:
            flag("unknown_hex", f"{color} is in neither palette")

    arrow_pairs = ARROW_PAIR.findall(text)
    for a, b in arrow_pairs:
        if frozenset((_hex(a), _hex(b))) not in pairs:
            flag("unmatched_pair", f"{a} ↔ {b} was not a matched pair")

    paired_values = 0
    pair_spans = []
    for m in PAIR_DELTA.finditer(text):
        paired_values += 1
        pair_spans.append(m.span())
        pair = pairs.get(frozenset((_hex(m[1]), _hex(m[2]))))
        if pair and not _close(m[3], pair["delta_e"]):
            flag("wrong_delta_e", f"{m[1]} / {m[2]} says ΔE {m[3]}, actual {pair['delta_e']}")
        elif not pair and not any(_close(m[3], p["delta_e"]) for p in facts["matched_colors"]
                                  if {_hex(m[1]), _hex(m[2])} & {_hex(p["a"]), _hex(p["b"])}):
            # "#a and #b align with #c and #d (ΔE 4.2 and 1.9, respectively)" pairs a-c and b-d, not c-d,
            # so an unmatched pair only counts as wrong if the value fits neither color's real pairs.
            flag("wrong_delta_e", f"{m[1]} / {m[2]} says ΔE {m[3]}, but they were not matched")

    delta_values = [p["delta_e"] for p in facts["matched_colors"]]
    bare_values = 0
    for m in ANY_DELTA.finditer(text):
        if any(start <= m.start() < end for start, end in pair_spans):
            continue
        bare_values += 1
        if not any(_close(m[1], v) for v in delta_values):
            flag("wrong_delta_e", f"ΔE {m[1]} matches no computed value")

    distance_values = 0
    for m in DISTANCE.finditer(text):
        distance_values += 1
        actual = facts["palette_distance"]
        # The prompt shows one decimal, so 11.95 may legitimately be quoted as 12.0.
        if actual is None or not _close(m[1], actual, margin=0.05):
            flag("wrong_distance", f"palette distance {m[1]}, actual {actual}")

    share_values = 0
    for m in SHARE.finditer(text):
        share_values += 1
        known = shares.get(_hex(m[1]))
        if known and not any(abs(float(m[2]) - v) <= SHARE_TOLERANCE for v in known):
            flag("wrong_share", f"{m[1]} at {m[2]}%, actual {[round(v, 1) for v in known]}")

    return findings, {"hexes": len(mentioned), "pairs": len(arrow_pairs),
                      "delta_e": paired_values + bare_values,
                      "distances": distance_values, "shares": share_values}


def _check_quotes(run: dict[str, Any], text: str) -> tuple[list[dict[str, str]], dict[str, int]]:
    names = [normalize(n) for n in run["facts"]["titles"] + run["facts"]["artists"]] + ["your image"]
    sources = {s["n"]: normalize(s["content"]) for s in run["sources"]}
    spans = sentence_spans(text)
    findings: list[dict[str, str]] = []
    counts = {"quotes": 0, "quotes_verified": 0, "quotes_names": 0}

    for match in QUOTE.finditer(text):
        quote = match[1] or match[2]
        key = normalize(quote).strip(" .,;:!?'")
        counts["quotes"] += 1
        if any(key in name for name in names):  # painting titles are quoted in the prompt itself
            counts["quotes_names"] += 1
            continue
        sentence = "".join(text[a:b] for a, b in spans if a < match.end() and match.start() < b)
        cited = _citations(sentence)
        where = {n for n, content in sources.items() if _contains(content, key)}
        if where & cited:
            counts["quotes_verified"] += 1
        elif not where:
            near = max(((*_nearest(content, key), n) for n, content in sources.items()), key=lambda x: x[0])
            if near[0] >= ALTERED_RATIO:
                findings.append({"check": "quote_altered", "severity": "error",
                                 "detail": f'"{quote}" is not verbatim; [{near[2]}] says "{near[1]}"'})
            else:
                findings.append({"check": "quote_not_found", "severity": "error",
                                 "detail": f'"{quote}" is in no retrieved source'})
        elif cited:
            findings.append({"check": "quote_wrong_source", "severity": "error",
                             "detail": f'"{quote}" cites {sorted(cited)} but is in {sorted(where)}'})
        else:
            findings.append({"check": "quote_uncited", "severity": "error",
                             "detail": f'"{quote}" has no citation; it is in {sorted(where)}'})
    return findings, counts


def check(run: dict[str, Any]) -> dict[str, Any]:
    """Findings and counts for one saved run. A run with no sources made no Gemini call, so it has nothing to check."""
    text = run["answer"]
    if not run["sources"]:
        return {"findings": [], "counts": {"no_sources": 1}}

    findings: list[dict[str, str]] = []
    counts: dict[str, int] = {}
    if not text.strip():
        return {"findings": [{"check": "empty_answer", "severity": "error", "detail": "no text"}], "counts": {}}

    for checker in (_check_numbers, _check_quotes):
        new, new_counts = checker(run, text)
        findings += new
        counts.update(new_counts)

    invented = sorted(n for n in _citations(run["raw_answer"] or "") if not 1 <= n <= len(run["sources"]))
    if invented:
        findings.append({"check": "invented_citation", "severity": "error",
                         "detail": f"cited {invented}, with {len(run['sources'])} sources; cleanup removed them"})

    if not run["facts"]["has_upload"]:
        for m in PHANTOM_UPLOAD.finditer(text):
            findings.append({"check": "phantom_upload", "severity": "error",
                             "detail": f'says "{m[0]}", but no image was uploaded'})
    if run["kind"].startswith("edge"):
        for m in LABEL_LEAK.finditer(text):
            findings.append({"check": "label_leak", "severity": "error",
                             "detail": f'says "{m[0]}"; the prompt forbids A/B labels'})

    spans = sentence_spans(text)
    counts["sentences"] = len(spans)
    if not _citations(text):
        findings.append({"check": "no_citations", "severity": "warning", "detail": "no citations in the answer"})
    for a, b in spans:
        sentence = text[a:b]
        if not _citations(sentence) and not re.search(HEX, sentence) and not ANY_DELTA.search(sentence):
            findings.append({"check": "uncited_sentence", "severity": "warning", "detail": sentence.strip()})
    return {"findings": findings, "counts": counts}
