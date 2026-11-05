"""Saved explanations for checking whether sources support what Gemini wrote.

Usage (from backend/):
    python -m eval.explanations sample            # fixed sample → eval/explain_sample.json (no Gemini calls)
    python -m eval.explanations run               # generate and save → eval/explain_runs.jsonl (resumable)
    python -m eval.explanations check             # code checks on the dev split → eval/RESULTS_explain_checks.md

Half of the sample is held out. `check` reads the dev split unless told otherwise: tune prompts against dev,
then measure the fix once with `run --out NEW_FILE` and `check --split test --runs NEW_FILE`.
"""

import argparse
import json
import random
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app import gemini
from app.db import connect
from app.palette import Swatch
from app.rag import explain_edge, explain_matches, fetch_artworks
from app.retrieve import match_image
from eval.explain_checks import check
from eval.label import HUMAN_DIR, list_images

EVAL_DIR = Path(__file__).parent
SAMPLE = EVAL_DIR / "explain_sample.json"
RUNS = EVAL_DIR / "explain_runs.jsonl"
RESULTS = EVAL_DIR / "RESULTS_explain_checks.md"

SEED = 11
UI_NEIGHBORS = 6  # the web map's default k: pairs a person would actually see
# How much text the pair has to draw on. These are the conditions most likely to change how well answers are supported.
EDGE_STRATA = {"rich": 10, "wiki_only": 10, "one_sided": 8, "no_text": 2}
N_UPLOAD_EDGES = 10
N_UPLOAD_MATCHES = 10
MATCHES_SHOWN = 5


def edge_stratum(source: dict[str, bool], target: dict[str, bool]) -> str:
    source_text = source["description"] or source["wiki"]
    target_text = target["description"] or target["wiki"]
    if not source_text and not target_text:
        return "no_text"
    if not source_text or not target_text:
        return "one_sided"
    return "rich" if source["description"] or target["description"] else "wiki_only"


def assign_splits(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Alternate dev and test so each stratum is split evenly. `items` is already in random order."""
    return [{**item, "split": "dev" if i % 2 == 0 else "test"} for i, item in enumerate(items)]


COVERAGE_SQL = """
select a.id,
       exists (select 1 from text_chunks c where c.artwork_id = a.id),
       exists (select 1 from text_chunks c where c.artist = a.artist and c.embedding is not null)
from artworks a where a.hist is not null and a.excluded is null
"""

PAIRS_SQL = """
select source_id, target_id from (
  select e.source_id, e.target_id,
         row_number() over (partition by e.source_id order by e.score desc, e.target_id) as rank
  from artwork_edges e
  join artworks s on s.id = e.source_id
  where e.kind = 'palette' and s.excluded is null
) ranked where rank <= %s order by source_id, target_id
"""


def build_sample() -> list[dict[str, Any]]:
    rng = random.Random(SEED)
    sample: list[dict[str, Any]] = []
    with connect() as conn:
        coverage = {r[0]: {"description": r[1], "wiki": r[2]} for r in conn.execute(COVERAGE_SQL)}
        by_stratum: dict[str, list[tuple[int, int]]] = {s: [] for s in EDGE_STRATA}
        for source_id, target_id in conn.execute(PAIRS_SQL, (UI_NEIGHBORS,)):
            if source_id in coverage and target_id in coverage:
                by_stratum[edge_stratum(coverage[source_id], coverage[target_id])].append((source_id, target_id))
        for stratum, n in EDGE_STRATA.items():
            picked = rng.sample(by_stratum[stratum], n)
            sample += assign_splits([
                {"id": f"edge-{stratum}-{i:02d}", "kind": "edge_painting", "stratum": stratum,
                 "source_id": source_id, "target_id": target_id}
                for i, (source_id, target_id) in enumerate(picked)])

        # Palettes are stored in the sample, so it can be re-run without the images, which aren't committed.
        images = rng.sample(list_images(HUMAN_DIR), N_UPLOAD_EDGES + N_UPLOAD_MATCHES)
        edges, matches = [], []
        for i, path in enumerate(images):
            palette, results = match_image(conn, path, k=MATCHES_SHOWN)
            if i < N_UPLOAD_EDGES:
                edges.append({"id": f"edge-upload-{i:02d}", "kind": "edge_upload", "stratum": "upload",
                              "image": path.name, "source_palette": palette, "target_id": results[0]["id"]})
            else:
                matches.append({"id": f"matches-{i:02d}", "kind": "matches", "stratum": "upload",
                                "image": path.name, "query_palette": palette,
                                "artwork_ids": [r["id"] for r in results]})
        sample += assign_splits(edges) + assign_splits(matches)
    return sample


def _facts(artworks: list[dict[str, Any]], upload_palette: list[Swatch] | None,
           result: dict[str, Any]) -> dict[str, Any]:
    palettes = [a["palette"] or [] for a in artworks]
    if upload_palette:
        palettes.append(upload_palette)
    return {
        "has_upload": upload_palette is not None,
        "palettes": palettes,
        "titles": [a["title"] for a in artworks],
        "artists": [a["artist"] for a in artworks if a["artist"]],
        "palette_distance": result.get("palette_distance"),
        "matched_colors": result.get("matched_colors", []),
    }


def generate_one(conn: Any, item: dict[str, Any]) -> dict[str, Any]:
    trace: dict[str, Any] = {}
    if item["kind"] == "matches":
        ids, upload = item["artwork_ids"], item["query_palette"]
        result = explain_matches(conn, upload, ids, trace=trace)
    else:
        upload = item.get("source_palette")
        ids = [i for i in (item.get("source_id"), item["target_id"]) if i is not None]
        result = explain_edge(conn, item["target_id"], source_id=item.get("source_id"),
                              source_palette=upload, trace=trace)
        if result is None:
            raise RuntimeError(f"{item['id']}: artwork not found")
    return {
        "id": item["id"], "kind": item["kind"], "stratum": item["stratum"], "split": item["split"],
        "model": gemini.GENERATE_MODEL, "thinking_level": gemini.THINKING_LEVEL,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "artwork_ids": ids,
        "facts": _facts(fetch_artworks(conn, ids), upload, result),
        **trace,
        "answer": result["answer"],
        "cited": [s["n"] for s in result["sources"] if s["cited"]],
    }


def load_runs(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def run_all(out: Path, split: str | None) -> None:
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    done = {r["id"] for r in load_runs(out)}
    todo = [s for s in sample if s["id"] not in done and (split is None or s["split"] == split)]
    print(f"{len(todo)} to generate, {len(done)} already saved in {out.name}", flush=True)
    with connect() as conn, out.open("a", encoding="utf-8") as f:
        for n, item in enumerate(todo, 1):
            try:
                record = generate_one(conn, item)
            except gemini.DailyQuotaExceeded:
                print("daily quota reached; re-run after it resets to resume", flush=True)
                return
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()
            print(f"[{n}/{len(todo)}] {item['id']}: {len(record['sources'])} sources", flush=True)


def report(runs: list[dict[str, Any]], split: str) -> str:
    checked = [(r, check(r)) for r in runs]
    generated = [(r, c) for r, c in checked if r["sources"]]
    with_error = [r["id"] for r, c in generated if any(f["severity"] == "error" for f in c["findings"])]
    totals: Counter[str] = Counter()
    for _, c in checked:
        totals.update(c["counts"])

    def tally(check_name: str) -> tuple[int, int]:
        hits = [sum(f["check"] == check_name for f in c["findings"]) for _, c in generated]
        return sum(1 for h in hits if h), sum(hits)

    lines = [
        "# Explanation code checks", "",
        f"Split: **{split}**. {len(runs)} saved explanations: {len(generated)} written by "
        f"{runs[0]['model'] if runs else 'n/a'}, {totals['no_sources']} with no sources (no model call).", "",
        "These checks need no AI and only catch mechanical errors: numbers, quotes and wording against what the "
        "model was given. They don't show that a source supports a claim, so passing here is not a measure of "
        "faithfulness.", "",
        f"**{len(with_error)} of {len(generated)} explanations have at least one error.**", "",
        "| Check | Severity | Explanations | Occurrences |", "|---|---|---|---|",
    ]
    names = Counter()
    severity = {}
    for _, c in generated:
        for f in c["findings"]:
            names[f["check"]] += 1
            severity[f["check"]] = f["severity"]
    for name in sorted(names, key=lambda x: (severity[x] != "error", -names[x])):
        affected, total = tally(name)
        lines.append(f"| `{name}` | {severity[name]} | {affected} | {total} |")
    if not names:
        lines.append("| none | | 0 | 0 |")
    lines += ["", "## What was checked", "",
              f"- Hex codes: {totals['hexes']}", f"- Matched pairs written with an arrow: {totals['pairs']}",
              f"- ΔE values: {totals['delta_e']}", f"- Palette distances: {totals['distances']}",
              f"- Pixel shares next to a hex code: {totals['shares']}",
              f"- Quoted phrases: {totals['quotes']} ({totals['quotes_verified']} found in a cited source, "
              f"{totals['quotes_names']} painting titles or artist names)",
              f"- Sentences: {totals['sentences']}", "",
              "## By group", "", "| Kind | Text available | Explanations | With an error |", "|---|---|---|---|"]
    groups = Counter((r["kind"], r["stratum"]) for r, _ in generated)
    for (kind, stratum), n in sorted(groups.items()):
        errors = sum(1 for r, c in generated if (r["kind"], r["stratum"]) == (kind, stratum)
                     and any(f["severity"] == "error" for f in c["findings"]))
        lines.append(f"| {kind} | {stratum} | {n} | {errors} |")
    lines += ["", "## Errors", ""]
    for r, c in generated:
        for f in c["findings"]:
            if f["severity"] == "error":
                lines.append(f"- `{r['id']}` `{f['check']}`: {f['detail']}")
    if not with_error:
        lines.append("None.")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sample")
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--out", type=Path, default=RUNS)
    run_parser.add_argument("--split", choices=["dev", "test"])
    check_parser = sub.add_parser("check")
    check_parser.add_argument("--runs", type=Path, default=RUNS)
    check_parser.add_argument("--split", choices=["dev", "test"], default="dev")
    check_parser.add_argument("--out", type=Path, default=RESULTS)
    args = parser.parse_args()

    if args.command == "sample":
        if SAMPLE.exists():
            parser.error(f"{SAMPLE.name} already exists; the sample is fixed. Delete it to draw a new one.")
        items = build_sample()
        SAMPLE.write_text(json.dumps(items, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{len(items)} items → {SAMPLE.name}: {dict(Counter(i['split'] for i in items))}")
    elif args.command == "run":
        run_all(args.out, args.split)
    else:
        runs = [r for r in load_runs(args.runs) if r["split"] == args.split]
        text = report(runs, args.split)
        args.out.write_text(text, encoding="utf-8")
        print(text)
