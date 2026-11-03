# Labeling rule

Committed before any painting in this round was labeled. Written without looking at the dev images.

A good match is a painting you could show as an example of an artist working with the same colors as the uploaded image.

## Rule

Compare the images side by side. Mark a painting **good only if all three are true**:

1. **Same main colors:** the colors covering most of the uploaded image also cover much of the painting, in roughly similar proportions. The same color family is enough; the exact shade doesn't have to match.
2. **Same overall feel:** both have a similar light or dark level, and both are similarly muted or vivid.
3. **Nothing important clashes:** the painting has no large area in a color the image lacks. If a small accent is what catches your eye in the image, the painting needs something similar.

**Ignore:** subject, style, layout, quality, and whether you like the painting.

**Judge the colors you can see:** don't mentally correct for yellowed varnish, and don't judge from the swatches.

**If you're still unsure after a few seconds, mark it poor.**

## Committed decision

`build --recheck 36` mixes 36 already-judged paintings into the page, unmarked. If fewer than 29 of the 36 (80%) keep their original label, the old and new labels are not comparable, and the whole dev pool is relabeled under this rule before any dev score is reported. The 80% cutoff is a judgment call, not a published standard.

The rule draws on related research (choosing color themes, judging palette differences), but it has not been validated for matching paintings to images.
