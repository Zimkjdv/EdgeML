# Parameter optimization review and changes

## High-priority changes implemented

| Finding | Change | Verification |
| --- | --- | --- |
| Diversity could displace achievable recommendations | Select all required distinct in-tolerance candidates before considering misses; prefer diversity within each group | Clustered in-tolerance search test |
| Invalid fields reported only after submission | Immediate bilingual field errors, error summary with field navigation, and disabled submission; server validation retained | Frontend validation tests and TypeScript build |
| No operating baseline comparison | Optional baseline mode exposes adjustable current values, predicts the full baseline, and shows baseline Y/error and parameter deltas | Baseline prediction and unchanged search reproducibility tests |
| Binary floating point could omit aligned endpoints | Decimal step-index calculation and reconstruction anchored at the minimum | Positive, negative, aligned and unaligned decimal boundary tests |

## Baseline contract

`POST /api/optimization/simulate` accepts optional `compare_baseline` (default false). When true, every feature must have a valid `value`, including adjustable features. These values form the baseline; the fixed feature values also remain fixed in the search. Baseline values may lie outside the search bounds: bounds constrain recommendations, not the current operating state.

The response adds nullable `baseline`, with `parameters`, `prediction`, `absolute_error`, and `within_tolerance`. Baseline prediction is separate from `evaluated` and does not change the random search sequence. No automatic baseline is inserted into candidate selection.

The UI initially uses training defaults where available. These are statistical reference values, not observed current plant conditions. Users should enter actual values before treating the comparison as a current-state comparison. Existing CSV import continues to update fixed features only; adjustable baseline values are edited in the baseline column. Numeric deltas are recommendation minus baseline; categories show before/after values. Changing inputs invalidates the displayed result.

## Remaining review items

| Priority | Follow-up |
| --- | --- |
| Medium | Elapsed time, real job progress and cancellation (requires backend job support) |
| Medium | Target-interval summary, achieved recommendation counts, and status colors |
| Medium | Tooltips for candidate counts, step and random seed |
| Medium | Convergence chart from best_error_by_iteration |
| Medium | More accurate missing-default and truncated-category notices |
| Later | CSV/JSON result export with full reproduction settings |
| Later | Retry a duplicate-only iteration and enumerate small discrete search spaces |
| Later | Cross-feature operating constraints and joint-data plausibility checks |

Search remains bounded and heuristic. Being within tolerance is a model prediction, not a measured outcome or proof of a global optimum. Decimal grids still reach the model as floating-point inputs.
