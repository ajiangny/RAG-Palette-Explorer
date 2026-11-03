# Held-out human test

24 new images, labeled in one sitting with both systems' top 5 pooled and shuffled. Challenger and decision rule were committed first (`TEST_PROTOCOL.md`).

| System | P@5 |
|---|---|
| Histogram + palette rerank, α=0.5 (deployed) | 65% |
| Finalist: hue/chroma EMD, α=0.5 | 66% |

Difference: +0.8 points (95% CI -7.5 to +9.2, paired bootstrap); better on 7, worse on 6, tied on 11 images.

Decision rule: NOT met (lower bound of the CI must be above 0).
