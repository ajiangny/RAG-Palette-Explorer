# Final test

30 new images, labeled in one sitting with both systems' top 5 pooled and shuffled. Comparison and decision rule were committed first (`FINAL_TEST_PROTOCOL.md`).

| System | P@5 |
|---|---|
| Deployed, before the National Gallery | 72% |
| Deployed, with the National Gallery | 80% |

Difference: +8.0 points (95% CI +2.7 to +13.3, paired bootstrap); better on 11, worse on 2, tied on 17 images.

Decision rule: met (lower bound of the CI must be above 0).

This is one human labeler, on stock-style photos only, with no designs or screenshots. The collection as tested had 7,735 searchable paintings. 120 black-and-white reproductions were excluded afterward, leaving 7,615, and that collection has not been re-tested here.

## AI second rater

Opus labeled the same 206 pairs blind under the same rule (`ai_labels_final.json`).

| Labeler | Images | Before | After | Change (95% CI) |
|---|---|---|---|---|
| Human (primary) | 30 | 72.0% | 80.0% | +8.0 (+2.7 to +13.3) |
| Opus | 30 | 31.3% | 38.7% | +7.3 (+0.7 to +13.3) |

The two labelers agreed on 53.4% of pairs (kappa 0.18): the human marked 153 good and Opus 75. Both see a similar gain, so the gain is better supported than the level.

## Side check, not part of the committed test

Two images (`palette-final-18.jpg`, `palette-final-23.jpg`) are fully grayscale. The labeler questioned them before seeing any score. Without them, the human result is 70.0% → 78.6% (+8.6, +2.9 to +14.3) and the Opus result is 27.1% → 35.0% (+7.9, +1.4 to +14.3).
