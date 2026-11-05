# Explanation code checks

Split: **test**. 25 saved explanations: 23 written by gemini-3-flash-preview, 2 with no sources (no model call).

These checks need no AI and only catch mechanical errors: numbers, quotes and wording against what the model was given. They don't show that a source supports a claim, so passing here is not a measure of faithfulness.

**7 of 23 explanations have at least one error.**

| Check | Severity | Explanations | Occurrences |
|---|---|---|---|
| `phantom_upload` | error | 5 | 6 |
| `quote_not_found` | error | 2 | 2 |
| `quote_altered` | error | 2 | 2 |
| `uncited_sentence` | warning | 23 | 52 |

## What was checked

- Hex codes: 114
- Matched pairs written with an arrow: 0
- ΔE values: 20
- Palette distances: 9
- Pixel shares next to a hex code: 8
- Quoted phrases: 154 (91 found in a cited source, 59 painting titles or artist names)
- Sentences: 231

## By group

| Kind | Text available | Explanations | With an error |
|---|---|---|---|
| edge_painting | one_sided | 4 | 3 |
| edge_painting | rich | 5 | 2 |
| edge_painting | wiki_only | 5 | 2 |
| edge_upload | upload | 4 | 0 |
| matches | upload | 5 | 0 |

## Errors

- `edge-rich-03` `quote_not_found`: "moon-faced" is in no retrieved source
- `edge-rich-09` `phantom_upload`: says "your image", but no image was uploaded
- `edge-wiki_only-03` `phantom_upload`: says "your image", but no image was uploaded
- `edge-wiki_only-09` `phantom_upload`: says "your image", but no image was uploaded
- `edge-wiki_only-09` `phantom_upload`: says "your image", but no image was uploaded
- `edge-one_sided-03` `quote_altered`: "fascination for light" is not verbatim; [2] says "fascination pour la"
- `edge-one_sided-03` `phantom_upload`: says "your image", but no image was uploaded
- `edge-one_sided-05` `quote_not_found`: "low-key" is in no retrieved source
- `edge-one_sided-07` `quote_altered`: "meticulous" is not verbatim; [1] says "meticulously"
- `edge-one_sided-07` `phantom_upload`: says "your image", but no image was uploaded
