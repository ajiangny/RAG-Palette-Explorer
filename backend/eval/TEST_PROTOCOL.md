# Held-out test protocol

Committed before any test image was scored.

**Question:** does the challenger rank better palette matches than the deployed system on images it was not tuned on?

- **Deployed:** 8x8x8 histogram, top 100 candidates, CIEDE2000 palette EMD, palette k=6, α=0.5.
- **Challenger:** identical, except the palette EMD uses a,b distance only (no lightness).
- **Chosen on dev because:** it beat the deployed system on the 28 dev images while costing 3 points of crop/photo Hit@1 (79% vs 82%). The chroma-penalty variant scored 5 points higher on dev but cost 11 points of Hit@1.
- **Dev caveat:** dev labels came from three sessions with rising good-rates (31%, 46%, 74%), so the dev lift (56% vs 38%) is probably inflated.

**Test set:** about 30 images in `data/eval_human_test/`, none used in tuning, none byte-identical to a dev image.

**Labeling:** one sitting. Both systems' top 5 are pooled and shuffled per image, with no indication of which system found which painting.

**Metric:** mean P@5 per image. **Uncertainty:** 95% paired bootstrap over images.

**Decision rule:** switch to the challenger only if the lower bound of the CI on (challenger − deployed) is above 0. Otherwise keep the deployed system. Either way the result is reported as measured, and the challenger is not re-tuned on these images.

**Exclusion, made before any test labeling:** `download (1).png` was removed because it is 100% transparent and has no visible pixels. Test set: 24 images (about 30 were planned).
