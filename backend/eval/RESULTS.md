# Retrieval evaluation

Automatic test set: 184 queries made from 92 collection paintings (a 40–70% crop and a photo-like copy of each), searched against all 7615 paintings. Ground truth is the source painting. Configs were tuned on the dev half; numbers below are the held-out **test** half (98 queries). Exact cosine search, in memory.

| System | Hit@1 | Hit@5 | Hit@10 | MRR | Hit@5 crop | Hit@5 photo |
|---|---|---|---|---|---|---|
| Histogram only (stage 1, 8x8x8) | 77% | 86% | 91% | 0.816 | 100% | 71% |
| Histogram + palette rerank, α=0 (initial design) | 73% | 87% | 90% | 0.794 | 92% | 82% |
| **Histogram + palette rerank, α=0.5 (deployed)** | 81% | 90% | 93% | 0.854 | 98% | 82% |
| Histogram only, best on dev (8x8x8) | 77% | 86% | 91% | 0.816 | 100% | 71% |
| Histogram + rerank, best on dev (12x12x12, k=8, 200 cand., α=0.5) | 84% | 91% | 93% | 0.873 | 98% | 84% |

With 98 test queries, one query is 1 point of Hit@k, so gaps of a few points are within noise. Every config and split is in `results.csv`.

## Human-judged precision@5

The headline result is the held-out final test in [`RESULTS_final_test.md`](RESULTS_final_test.md): 72% → 80% P@5 from adding the National Gallery, on 30 new photos with one human labeler.

The earlier dev scores (38% deployed) used labels from before the written rule in `LABELING_RULE.md` and are superseded. They remain in `RESULTS_pre_nga.md`. A re-check found that only 25 of 36 old labels held under the rule, below the committed cutoff of 29, so old and new labels are not mixed.

### Dev images, AI-judged

Opus labeled every pair on 28 dev images blind under the rule. These are **AI-judged, dev-only** numbers, measured with the National Gallery present but before the 120 black-and-white reproductions were excluded.

| System | Before National Gallery | With National Gallery | Change (95% CI) |
|---|---|---|---|
| Histogram only (8x8x8) | 13.6% | 22.9% | +9.3 (+1.4 to +17.1) |
| Palette rerank, α=0 | 20.0% | 28.6% | +8.6 (+0.7 to +17.9) |
| **Deployed, α=0.5** | **20.0%** | **31.4%** | **+11.4 (+3.6 to +20.0)** |
| CIEDE2000 kL=2, α=0.5 | 23.6% | 32.1% | +8.6 (+0.7 to +17.1) |
| Hue/chroma, α=0.5 | 25.7% | 37.1% | +11.4 (+4.3 to +19.3) |
| Hue/chroma + chroma penalty, α=0.5 | 27.1% | 37.1% | +10.0 (+2.1 to +17.9) |

Opus kept 32 of 36 labels when re-judging, but agreed with the human labeler on only 63.6% of 209 shared pairs (kappa 0.28), and it is much stricter. Read the changes, not the levels. Labels are in `ai_labels_dev.json`.
