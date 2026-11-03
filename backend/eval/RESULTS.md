# Retrieval evaluation

Automatic test set: 200 queries made from 100 collection paintings (a 40–70% crop and a photo-like copy of each), searched against all 1850 paintings. Ground truth is the source painting. Configs were tuned on the dev half; numbers below are the held-out **test** half (100 queries). Exact cosine search, in memory.

| System | Hit@1 | Hit@5 | Hit@10 | MRR | Hit@5 crop | Hit@5 photo |
|---|---|---|---|---|---|---|
| Histogram only (stage 1, 8x8x8) | 79% | 90% | 94% | 0.840 | 100% | 80% |
| Histogram + palette rerank, α=0 (initial design) | 79% | 91% | 96% | 0.849 | 96% | 86% |
| **Histogram + palette rerank, α=0.5 (deployed)** | 86% | 93% | 96% | 0.896 | 98% | 88% |
| Histogram only, best on dev (12x12x12) | 80% | 91% | 93% | 0.852 | 100% | 82% |
| Histogram + rerank, best on dev (12x12x12, k=6, 50 cand., α=0.5) | 90% | 94% | 96% | 0.920 | 100% | 88% |

With 100 test queries, one query is 1 point of Hit@k, so gaps of a few points are within noise. Every config and split is in `results.csv`.
