# Retrieval evaluation

Automatic test set: 200 queries made from 100 collection paintings (a 40–70% crop and a photo-like copy of each), searched against all 4831 paintings. Ground truth is the source painting. Configs were tuned on the dev half; numbers below are the held-out **test** half (100 queries). Exact cosine search, in memory.

| System | Hit@1 | Hit@5 | Hit@10 | MRR | Hit@5 crop | Hit@5 photo |
|---|---|---|---|---|---|---|
| Histogram only (stage 1, 8x8x8) | 76% | 86% | 92% | 0.814 | 100% | 72% |
| Histogram + palette rerank, α=0 (initial design) | 75% | 87% | 92% | 0.807 | 92% | 82% |
| **Histogram + palette rerank, α=0.5 (deployed)** | 81% | 90% | 94% | 0.859 | 98% | 82% |
| Histogram only, best on dev (12x12x12) | 80% | 89% | 91% | 0.838 | 100% | 78% |
| Histogram + rerank, best on dev (12x12x12, k=6, 100 cand., α=0.5) | 84% | 92% | 94% | 0.877 | 100% | 84% |

With 100 test queries, one query is 1 point of Hit@k, so gaps of a few points are within noise. Every config and split is in `results.csv`.

## Human-judged precision@5

28 outside images (photos, designs). The top 5 of every system were pooled and shuffled, then labeled as good / poor palette matches without showing which system found which.

| System | P@5 |
|---|---|
| Histogram only (stage 1, 8x8x8) | 39% |
| Histogram + palette rerank, α=0 (initial design) | 37% |
| Histogram + palette rerank, α=0.5 (deployed) | 38% |
| Finalist: CIEDE2000 with kL=2, α=0.5 | 46% |
| Finalist: hue/chroma EMD, α=0.5 | 56% |
| Finalist: hue/chroma EMD + chroma penalty, α=0.5 | 61% |

Difference from *Histogram only (stage 1, 8x8x8)* (paired bootstrap over images, 95% CI):

- Histogram + palette rerank, α=0 (initial design): -1.4 points (-10.7 to +8.6); better on 7, worse on 13, tied on 8 images
- Histogram + palette rerank, α=0.5 (deployed): -0.7 points (-8.6 to +7.1); better on 9, worse on 10, tied on 9 images
- Finalist: CIEDE2000 with kL=2, α=0.5: +7.9 points (+1.4 to +14.3); better on 11, worse on 4, tied on 13 images
- Finalist: hue/chroma EMD, α=0.5: +17.1 points (+6.4 to +27.9); better on 16, worse on 4, tied on 8 images
- Finalist: hue/chroma EMD + chroma penalty, α=0.5: +22.1 points (+11.4 to +32.9); better on 19, worse on 4, tied on 5 images

Good matches per image among the ~13 pooled paintings: median 7 (min 2, max 14). A perfect reordering of the pooled set would score 89% P@5, which is the headroom available to better ranking.

Adding the Cleveland collection, deployed system: 34% → 38% P@5, +3.6 points (-3.6 to +10.7, paired bootstrap); better on 10, worse on 6, tied on 12 images. Paintings new to the pool were labeled in a second session, knowing they were new, so labeler drift could account for some of this.

The finalists above were selected on these same images, so their lift is not a validated result. The held-out test of the chosen finalist is in `RESULTS_human_test.md`.
