# Quote rule test

Tested a prompt rule: quote a source only when copying it exactly, otherwise paraphrase without quotation marks. Success rule, set before the runs: quote errors per explanation must fall, with a confidence interval excluding zero.

**Not met, so the rule was not adopted.** The model quoted more under the rule (603 to 822 quotes other than titles and artist names), with 32 errors on each side.

Before: `explain_runs_before_quote_rule.jsonl` (150 runs). After: `explain_runs_quote_rule.jsonl` (150 runs).

Errors per explanation, averaged over repeats. 95% paired bootstrap over items.

| Errors | Before | After | Change (95% CI) |
|---|---|---|---|
| All errors | 0.24 | 0.24 | +0.00 (-0.16 to +0.16) |
| All quote errors | 0.24 | 0.24 | +0.00 (-0.16 to +0.16) |
| `quote_altered` | 0.20 | 0.13 | -0.07 (-0.19 to +0.04) |
| `quote_not_found` | 0.03 | 0.04 | +0.01 (-0.04 to +0.05) |
| `quote_uncited` | 0.00 | 0.04 | +0.04 (+0.01 to +0.10) |
| `quote_wrong_source` | 0.01 | 0.03 | +0.02 (+0.00 to +0.05) |

45 items compared.
