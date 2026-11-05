# Explanation code checks

Split: **dev**. 25 saved explanations: 22 written by gemini-3-flash-preview, 3 with no sources (no model call).

These checks need no AI and only catch mechanical errors: numbers, quotes and wording against what the model was given. They don't show that a source supports a claim, so passing here is not a measure of faithfulness.

**5 of 22 explanations have at least one error.**

| Check | Severity | Explanations | Occurrences |
|---|---|---|---|
| `quote_altered` | error | 4 | 6 |
| `quote_wrong_source` | error | 1 | 1 |
| `uncited_sentence` | warning | 21 | 47 |

## What was checked

- Hex codes: 115
- Matched pairs written with an arrow: 1
- ΔE values: 23
- Palette distances: 14
- Pixel shares next to a hex code: 2
- Quoted phrases: 186 (114 found in a cited source, 65 painting titles or artist names)
- Sentences: 213

## By group

| Kind | Text available | Explanations | With an error |
|---|---|---|---|
| edge_painting | one_sided | 4 | 2 |
| edge_painting | rich | 5 | 1 |
| edge_painting | wiki_only | 5 | 1 |
| edge_upload | upload | 3 | 0 |
| matches | upload | 5 | 1 |

## Errors

- `edge-rich-02` `quote_altered`: "splendour of color" is not verbatim; [5] says "splendour of its color"
- `edge-rich-02` `quote_altered`: "vigorous" is not verbatim; [5] says "vigorously"
- `edge-wiki_only-00` `quote_altered`: "renew German art" is not verbatim; [5] says "renewing german art"
- `edge-one_sided-00` `quote_altered`: "weave the forms into a harmonious whole," is not verbatim; [2] says "weaves the forms into a harmonious whole"
- `edge-one_sided-06` `quote_altered`: "reckless" is not verbatim; [2] says "recklessness"
- `edge-one_sided-06` `quote_altered`: "random" is not verbatim; [2] says "randomly"
- `matches-16` `quote_wrong_source`: "ethereal" cites [8] but is in [7]
