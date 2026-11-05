# Explanation code checks

Split: **dev**. 25 saved explanations: 22 written by gemini-3-flash-preview, 3 with no sources (no model call).

These checks need no AI and only catch mechanical errors: numbers, quotes and wording against what the model was given. They don't show that a source supports a claim, so passing here is not a measure of faithfulness.

**10 of 22 explanations have at least one error.**

| Check | Severity | Explanations | Occurrences |
|---|---|---|---|
| `phantom_upload` | error | 8 | 11 |
| `quote_altered` | error | 3 | 5 |
| `quote_wrong_source` | error | 1 | 1 |
| `uncited_sentence` | warning | 21 | 49 |

## What was checked

- Hex codes: 121
- Matched pairs written with an arrow: 0
- ΔE values: 17
- Palette distances: 11
- Pixel shares next to a hex code: 6
- Quoted phrases: 157 (106 found in a cited source, 45 painting titles or artist names)
- Sentences: 224

## By group

| Kind | Text available | Explanations | With an error |
|---|---|---|---|
| edge_painting | one_sided | 4 | 1 |
| edge_painting | rich | 5 | 4 |
| edge_painting | wiki_only | 5 | 4 |
| edge_upload | upload | 3 | 0 |
| matches | upload | 5 | 1 |

## Errors

- `edge-rich-00` `phantom_upload`: says "your image", but no image was uploaded
- `edge-rich-02` `quote_altered`: "splendour of color" is not verbatim; [5] says "splendour of its color"
- `edge-rich-02` `quote_altered`: "vigorous" is not verbatim; [5] says "vigorously"
- `edge-rich-04` `phantom_upload`: says "your image", but no image was uploaded
- `edge-rich-08` `phantom_upload`: says "your image", but no image was uploaded
- `edge-wiki_only-00` `phantom_upload`: says "your image", but no image was uploaded
- `edge-wiki_only-02` `quote_wrong_source`: "Ferrara school" cites [4] but is in [6]
- `edge-wiki_only-02` `phantom_upload`: says "your image", but no image was uploaded
- `edge-wiki_only-04` `phantom_upload`: says "your image", but no image was uploaded
- `edge-wiki_only-04` `phantom_upload`: says "your image", but no image was uploaded
- `edge-wiki_only-06` `quote_altered`: "as a negative under the action of chemicals" is not verbatim; [4] says "as a negative under the action of the chemicals"
- `edge-wiki_only-06` `phantom_upload`: says "your image", but no image was uploaded
- `edge-wiki_only-06` `phantom_upload`: says "your image", but no image was uploaded
- `edge-one_sided-06` `phantom_upload`: says "your image", but no image was uploaded
- `edge-one_sided-06` `phantom_upload`: says "your image", but no image was uploaded
- `matches-16` `quote_altered`: "paint the smell of the earth" is not verbatim; [3] says "paints the smell of the earth"
- `matches-16` `quote_altered`: "unkept" is not verbatim; [1] says "unkempt"
