# Claim labeling rule

Committed before any sentence in this round was labeled.

You see one sentence from an explanation, in its paragraph, beside the sources Gemini was given. The question is whether **those sources** back up what the sentence says, not whether the sentence is true.

## Verdicts

Choose one for the whole sentence. If parts differ, the weakest part decides.

1. **Supported:** a cited source says this. A fair paraphrase counts. Exact wording isn't needed.
2. **Stretched:** a cited source says something related, but the sentence goes further: broader, stronger, more certain, or about a different thing.
3. **Miscited:** a source Gemini was given supports it, but not the one cited. Also use this if the sentence has no citation and a source supports it.
4. **Unsupported:** none of the sources given support it.
5. **No sourced claim:** the sentence only describes the computed colors or introduces the next point, and says nothing about an artist, a work, a technique or history.

## How to decide

- Check the cited sources first. Look through the others only if those don't support it.
- **Ignore outside knowledge.** A true statement no source makes is unsupported.
- **Colors:** hex codes, shares and color names for them don't need a source. Anything added about why, such as "to capture rural light", does.
- **Intent and comparisons:** "He used it to convey calm" needs a source that says so. A comparison needs support for each side, and the comparison itself has to follow fairly from them.
- **Quotation marks:** judge the meaning. Code checks whether the wording is exact.
- **Still unsure after about a minute:** choose the weaker verdict you were considering.

## Limits

This is one labeler. The rule hasn't been validated elsewhere. Sentences can contain several claims, so a single stretched phrase marks the whole sentence.

## Consistency check

15 sentences appear twice, unmarked. Second answers measure consistency and never replace first answers.
