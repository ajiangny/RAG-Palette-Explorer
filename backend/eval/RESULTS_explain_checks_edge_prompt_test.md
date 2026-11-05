# Explanation code checks

Split: **test**. 25 saved explanations: 23 written by gemini-3-flash-preview, 2 with no sources (no model call).

These checks need no AI and only catch mechanical errors: numbers, quotes and wording against what the model was given. They don't show that a source supports a claim, so passing here is not a measure of faithfulness.

**3 of 23 explanations have at least one error.**

| Check | Severity | Explanations | Occurrences |
|---|---|---|---|
| `quote_altered` | error | 2 | 2 |
| `quote_wrong_source` | error | 1 | 1 |
| `uncited_sentence` | warning | 21 | 47 |

## What was checked

- Hex codes: 113
- Matched pairs written with an arrow: 0
- ΔE values: 18
- Palette distances: 13
- Pixel shares next to a hex code: 2
- Quoted phrases: 137 (75 found in a cited source, 59 painting titles or artist names)
- Sentences: 219

## By group

| Kind | Text available | Explanations | With an error |
|---|---|---|---|
| edge_painting | one_sided | 4 | 0 |
| edge_painting | rich | 5 | 0 |
| edge_painting | wiki_only | 5 | 0 |
| edge_upload | upload | 4 | 2 |
| matches | upload | 5 | 1 |

## Errors

- `edge-upload-01` `quote_wrong_source`: "restricted color range" cites [2, 3] but is in [1]
- `edge-upload-05` `quote_altered`: "fierce form" is not verbatim; [1] says "fierce forms"
- `matches-19` `quote_altered`: "subtle colours" is not verbatim; [4] says "subdued colors"
