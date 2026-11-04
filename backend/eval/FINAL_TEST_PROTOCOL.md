# Final test protocol

Committed before any painting was retrieved or judged for these images.

**Question:** does adding the National Gallery of Art give the deployed system better palette matches on images it was not tuned on?

- **Before:** deployed ranking (8x8x8 histogram, top 100 candidates, CIEDE2000 palette EMD, k=6, α=0.5), searching without National Gallery paintings.
- **After:** the same ranking, searching the whole collection.

No other system is compared here, and nothing is re-tuned on these images.

**Images:** the first 30 usable images from Lorem Picsum at `https://picsum.photos/seed/palette-final-NN/1000/750`, in seed order. Images were dropped only if corrupt, blank, or byte-identical to another image. Limitation: these are all stock-style photos, with no designs or screenshots, so results may not generalize to those.

**Labeling:** `LABELING_RULE.md`. Both systems' top 5 are pooled and shuffled per image, with no indication of which system found which painting, and paintings are shown uncropped.

**Metric:** mean P@5 per image. **Uncertainty:** 95% paired bootstrap over images.

**Decision rule:** the gain counts as supported only if the lower bound of the CI on (after − before) is above 0. Results are reported as measured either way.

**Labelers:** Opus labels every pair blind, with a check code on each sheet. A person may label the same pairs on `labeling_final.html`. Results are always reported by labeler. AI labels are never described as human-judged, and a human result, if any, is the primary one. If both exist, their agreement is reported beside the scores.
