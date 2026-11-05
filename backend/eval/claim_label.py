"""Hand labels: do the sources Gemini was given support each sentence it wrote? See eval/CLAIM_LABELING_RULE.md.

Usage (from backend/):
    python -m eval.claim_label build                   # fixed pool → eval/claim_pool.json, eval/claim_labeling.html
    python -m eval.claim_label score FILE              # downloaded labels → eval/claim_labels.json, RESULTS_claim_labels.md

Whole explanations from the dev split are labeled, so "fully supported" can be measured. The test split stays
unlabeled, to measure a later fix.
"""

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from eval.explain_checks import citations, sentence_spans
from eval.explanations import load_runs

EVAL_DIR = Path(__file__).parent
RUNS = EVAL_DIR / "explain_runs_before_quote_rule.jsonl"
POOL = EVAL_DIR / "claim_pool.json"
PAGE = EVAL_DIR / "claim_labeling.html"
LABELS = EVAL_DIR / "claim_labels.json"
RESULTS = EVAL_DIR / "RESULTS_claim_labels.md"
RULE = EVAL_DIR / "CLAIM_LABELING_RULE.md"

SEED = 23
TARGET_SENTENCES = 150
N_RECHECK = 15
RECHECK_GAP = 40  # sentences between a sentence's two appearances, at least
VERDICTS = ["supported", "stretched", "miscited", "unsupported", "no_claim"]
ROUNDS = 2000


def pick_explanations(runs: list[dict[str, Any]], rng: random.Random, target: int) -> list[dict[str, Any]]:
    """Whole explanations, one group at a time, until there are at least `target` sentences."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run in sorted(runs, key=lambda r: r["id"]):
        groups[run["stratum"]].append(run)
    for members in groups.values():
        rng.shuffle(members)
    picked, total = [], 0
    while total < target and any(groups.values()):
        for stratum in sorted(groups):
            if groups[stratum] and total < target:
                run = groups[stratum].pop()
                picked.append(run)
                total += len(sentence_spans(run["answer"]))
    return picked


def to_items(run: dict[str, Any]) -> list[dict[str, Any]]:
    text = run["answer"]
    items = []
    for n, (start, end) in enumerate(sentence_spans(text)):
        paragraph_start = text.rfind("\n", 0, start) + 1
        paragraph_end = text.find("\n", end)
        paragraph_end = len(text) if paragraph_end < 0 else paragraph_end
        items.append({
            "key": f"{run['id']}#{n}", "explanation": run["id"],
            "before": text[paragraph_start:start], "sentence": text[start:end], "after": text[end:paragraph_end],
            "cited": sorted(citations(text[start:end])),
        })
    return items


def add_rechecks(items: list[dict[str, Any]], rng: random.Random, n: int = N_RECHECK,
                 gap: int = RECHECK_GAP) -> list[dict[str, Any]]:
    """Insert second appearances of `n` sentences, each at least `gap` positions after the first."""
    out = list(items)
    for original in rng.sample(items[:max(1, len(items) - gap)], min(n, max(1, len(items) - gap))):
        earliest = out.index(original) + gap + 1
        copy = {**original, "key": f"{original['key']}~recheck", "recheck_of": original["key"]}
        out.insert(rng.randint(min(earliest, len(out)), len(out)), copy)
    return out


def build_pool() -> dict[str, Any]:
    rng = random.Random(SEED)
    runs = [r for r in load_runs(RUNS) if r["split"] == "dev" and r.get("repeat", 0) == 0 and r["sources"]]
    picked = pick_explanations(runs, rng, TARGET_SENTENCES)
    items = [item for run in picked for item in to_items(run)]
    rng.shuffle(items)
    return {
        "runs_file": RUNS.name,
        "items": add_rechecks(items, rng),
        "sources": {r["id"]: [{"n": s["n"], "title": s["title"], "content": s["content"]} for s in r["sources"]]
                    for r in picked},
    }


def score(pool: dict[str, Any], labels: dict[str, str], seed: int = SEED) -> str:
    first = [i for i in pool["items"] if "recheck_of" not in i and i["key"] in labels]
    rechecks = [i for i in pool["items"] if "recheck_of" in i and i["key"] in labels and i["recheck_of"] in labels]
    missing = sum(1 for i in pool["items"] if i["key"] not in labels)

    by_explanation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in first:
        by_explanation[item["explanation"]].append(item)

    def precision(members: list[list[dict[str, Any]]]) -> float:
        cited = [i for group in members for i in group if i["cited"] and labels[i["key"]] != "no_claim"]
        return sum(labels[i["key"]] == "supported" for i in cited) / len(cited) if cited else 0.0

    groups = list(by_explanation.values())
    rng = random.Random(seed)
    boots = sorted(precision(rng.choices(groups, k=len(groups))) for _ in range(ROUNDS)) if groups else [0.0, 0.0]
    low, high = boots[int(len(boots) * 0.025)], boots[int(len(boots) * 0.975)]

    claims = [i for i in first if labels[i["key"]] != "no_claim"]
    uncited = [i for i in claims if not i["cited"]]
    complete = [g for g in groups if len(g) == sum(1 for i in pool["items"]
                                                   if i["explanation"] == g[0]["explanation"] and "recheck_of" not in i)]
    clean = sum(all(labels[i["key"]] in ("supported", "no_claim") for i in g) for g in complete)
    counts = Counter(labels[i["key"]] for i in first)

    lines = ["# Sentence support, labeled by hand", "",
             f"One human labeler, under `CLAIM_LABELING_RULE.md`. {len(first)} sentences from {len(groups)} explanations "
             f"on the dev split (`{pool['runs_file']}`, first run of each). {missing} unanswered.", "",
             "Sentences, not single claims: one stretched phrase marks the whole sentence.", "",
             "| Measure | Result |", "|---|---|",
             f"| Cited sentences that are supported | {precision(groups):.0%} (95% CI {low:.0%} to {high:.0%}) |",
             f"| Sentences with a claim but no citation | {len(uncited)} of {len(claims)} |",
             f"| Fully supported explanations | {clean} of {len(complete)} |", "",
             "| Verdict | Sentences |", "|---|---|"]
    lines += [f"| {v} | {counts[v]} |" for v in VERDICTS]
    if rechecks:
        same = sum(labels[i["key"]] == labels[i["recheck_of"]] for i in rechecks)
        lines += ["", f"Consistency: {same} of {len(rechecks)} repeated sentences got the same verdict."]
    return "\n".join(lines) + "\n"


PAGE_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Claim Labeling</title>
<style>
:root{--bg:#f7f6f2;--panel:#fff;--ink:#22221f;--muted:#6b6a63;--line:#dcdad2;--mark:#ffe9a8;--accent:#2f5d8a}
@media (prefers-color-scheme:dark){:root{--bg:#191a1c;--panel:#232427;--ink:#e9e8e3;--muted:#a3a29b;--line:#3b3c40;--mark:#6a5414;--accent:#8db8e0}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,sans-serif}
header{display:flex;flex-wrap:wrap;gap:12px;align-items:center;padding:10px 16px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--bg);z-index:1}
header b{margin-right:auto}main{display:grid;grid-template-columns:minmax(0,5fr) minmax(0,7fr);gap:16px;padding:16px;max-width:1500px;margin:auto}
@media (max-width:860px){main{grid-template-columns:minmax(0,1fr)}}
section{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:16px;min-width:0}
mark{background:var(--mark);color:inherit;padding:1px 2px}.left{align-self:start;position:sticky;top:60px}@media (max-width:860px){.left{position:static}}
h2{font-size:13px;letter-spacing:.04em;text-transform:uppercase;color:var(--muted);margin:0 0 8px}h2:not(:first-child){margin-top:20px}
.src{border-top:1px solid var(--line);padding:10px 0;overflow-wrap:anywhere;white-space:pre-wrap}.src b{display:block;white-space:normal}
button{font:inherit;color:inherit;background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:9px 12px;cursor:pointer;min-height:44px}
button:hover{border-color:var(--accent)}button.on{background:var(--accent);border-color:var(--accent);color:var(--bg)}
.verdicts{display:grid;gap:8px;margin-top:16px}.verdicts button{text-align:left}kbd{font:12px ui-monospace,monospace;border:1px solid currentColor;border-radius:3px;padding:0 4px;margin-right:6px}
details{margin-top:14px;color:var(--muted);font-size:14px}details div{white-space:pre-wrap;margin-top:8px}.note{color:var(--muted);font-size:14px}
</style></head><body>
<header><b id="progress"></b><button id="back">← Back</button><button id="skip">Next unanswered →</button><button id="save">Download labels</button></header>
<main><section class="left"><h2>Sentence to judge</h2><p id="context"></p><div class="verdicts" id="verdicts"></div>
<details><summary>Labeling rule</summary><div id="rule"></div></details></section>
<section><h2 id="citedHead"></h2><div id="cited"></div><h2 id="otherHead"></h2><div id="other"></div></section></main>
<script>
const POOL=__POOL__;const RULE=__RULE__;const STORE='claim-labels-v1';
const NAMES={supported:'Supported',stretched:'Stretched',miscited:'Miscited or uncited',unsupported:'Unsupported',no_claim:'No sourced claim'};
const KEYS=Object.keys(NAMES);let labels={};try{labels=JSON.parse(localStorage.getItem(STORE))||{}}catch(e){}
const persist=()=>{try{localStorage.setItem(STORE,JSON.stringify(labels))}catch(e){}};
const items=POOL.items;let at=items.findIndex(i=>!labels[i.key]);if(at<0)at=0;
const $=id=>document.getElementById(id);$('rule').textContent=RULE;
function sourceList(el,list){el.replaceChildren(...list.map(s=>{const d=document.createElement('div');d.className='src';const t=document.createElement('b');t.textContent='['+s.n+'] '+s.title;d.append(t,s.content);return d}))}
function show(){const it=items[at];const done=items.filter(i=>labels[i.key]).length;
$('progress').textContent=done+' of '+items.length+' labeled · sentence '+(at+1);
const m=document.createElement('mark');m.textContent=it.sentence;$('context').replaceChildren(it.before,m,it.after);
const all=POOL.sources[it.explanation];const cited=all.filter(s=>it.cited.includes(s.n));const other=all.filter(s=>!it.cited.includes(s.n));
$('citedHead').textContent=cited.length?'Cited sources':'No citation in this sentence';sourceList($('cited'),cited);
$('otherHead').textContent=other.length?'Other sources Gemini was given':'';sourceList($('other'),other);
$('verdicts').replaceChildren(...KEYS.map((k,n)=>{const b=document.createElement('button');if(labels[it.key]===k)b.className='on';const key=document.createElement('kbd');key.textContent=n+1;b.append(key,NAMES[k]);b.onclick=()=>choose(k);return b}));
scrollTo(0,0)}
function choose(k){labels[items[at].key]=k;persist();const next=items.findIndex((i,n)=>n>at&&!labels[i.key]);const any=items.findIndex(i=>!labels[i.key]);at=next>=0?next:any>=0?any:at;show()}
$('back').onclick=()=>{at=Math.max(0,at-1);show()};
$('skip').onclick=()=>{const n=items.findIndex((i,j)=>j>at&&!labels[i.key]);if(n>=0){at=n;show()}};
$('save').onclick=()=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(labels,null,1)],{type:'application/json'}));a.download='claim_labels.json';a.click()};
addEventListener('keydown',e=>{if(e.metaKey||e.ctrlKey||e.altKey)return;const n=Number(e.key);if(n>=1&&n<=KEYS.length)choose(KEYS[n-1]);if(e.key==='ArrowLeft')$('back').click()});
show();
</script></body></html>
"""


def _embed(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def build_page(pool: dict[str, Any], rule: str) -> str:
    return PAGE_TEMPLATE.replace("__POOL__", _embed(pool)).replace("__RULE__", _embed(rule))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build")
    score_parser = sub.add_parser("score")
    score_parser.add_argument("file", type=Path)
    args = parser.parse_args()

    if args.command == "build":
        if POOL.exists():
            built = json.loads(POOL.read_text(encoding="utf-8"))
            print(f"using the existing {POOL.name}; the pool is fixed")
        else:
            built = build_pool()
            POOL.write_text(json.dumps(built, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        PAGE.write_text(build_page(built, RULE.read_text(encoding="utf-8")), encoding="utf-8")
        unique = sum("recheck_of" not in i for i in built["items"])
        print(f"{len(built['items'])} to label ({unique} sentences + {len(built['items']) - unique} repeats) "
              f"from {len(built['sources'])} explanations → {PAGE}")
    else:
        answers = json.loads(args.file.read_text(encoding="utf-8"))
        known = json.loads(POOL.read_text(encoding="utf-8"))
        LABELS.write_text(json.dumps(answers, indent=1) + "\n", encoding="utf-8")
        text = score(known, answers)
        RESULTS.write_text(text, encoding="utf-8")
        print(text)
