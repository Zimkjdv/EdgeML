# Parameter optimization method

## Overview

EdgeML currently uses model-based reverse search for Parameter Optimization. The system does not retrain the model and does not attempt to derive a mathematical inverse. It searches for input combinations `X` whose prediction from the existing model is close to the requested target `Y`.

The objective is:

```text
absolute_error = abs(predicted_y - target_y)
```

## How the simulation works

1. The user enters a numeric target `Y`, tolerance, and requested number of recommendations (up to five).
2. The user marks which features may be recommended. Unchecked features remain fixed using training-derived defaults such as the median, mode, an explicit value, or a user-selected CSV data row matched by feature-name headers. CSV import updates only fixed inputs after validating the complete row; adjustable search bounds remain unchanged.
3. Numeric bounds come from training-data minimums and maximums. Integer features support a discrete step. Categorical features use observed category choices.
4. The service creates a mixed population of numeric and categorical candidates. It combines global random exploration with mutations around better candidates from the previous iteration.
5. Every candidate is sent through the existing predictor and preprocessing pipeline in feature order.
6. Candidates are ranked by absolute target error. The result selector prefers distinct combinations so that recommendations are not duplicates of one another.
7. The API returns the recommendations, predicted values, errors, tolerance status, evaluation count, and best error observed per iteration. The UI comparison table shows only selected adjustable feature combinations plus prediction metrics. The API retains complete inputs, including fixed values. See [CSV import workflow](07_Parameter_Optimization.md#importing-fixed-inputs-from-csv).

The default bounded search uses 256 candidates per iteration and 12 iterations (at most 3,072 model evaluations). A fixed seed (`42` by default) makes repeated runs reproducible for the same model, constraints, and runtime.

## Why use model-based reverse search?

This approach is the best fit for the current platform for several reasons:

- **It works with the existing trained model.** The user wants to ask “which inputs would produce this output?” The model can be queried directly without changing its learned behavior or creating another training job.
- **It supports mixed feature types.** Real training data can contain numeric, integer, and categorical features. A population search can handle all of them, while common gradient-based optimizers require continuous, differentiable inputs.
- **It respects preprocessing and model boundaries.** Candidates pass through the same trusted predictor interface used by normal prediction, so imputation, encoding, scaling, and model-specific details remain inside the existing runtime.
- **It supports black-box models.** Tree ensembles and pipelines are not reliably differentiable. Reverse search only needs predictions, so it can support XGBoost, Ridge, and future predictor implementations through `BasePredictor`.
- **It can return multiple alternatives.** The objective is often not one mathematically unique answer. Diversity selection can present several different combinations with similarly good predicted values.
- **It is bounded and auditable.** Explicit ranges, categories, iteration limits, evaluation counts, and a seed make the work predictable and easier to explain than unconstrained brute force.

## Why not the alternatives yet?

- **Gradient descent / differentiable optimization:** unsuitable for categorical inputs and non-differentiable tree models; it also requires careful handling of preprocessing and bounds.
- **Analytical inversion:** most models and preprocessing pipelines do not have a stable or meaningful inverse. Multiple X combinations may map to the same Y, and some targets are unreachable.
- **Exhaustive grid search:** quickly becomes impractical as the number of features or categories grows.
- **Retraining for every request:** slow, expensive, and changes the model instead of finding inputs for the selected model.

## Interpretation and limitations

The result is a model-consistent recommendation, not proof of a causal relationship. Training ranges are statistical bounds, not safety or operating limits. Independent per-feature defaults may form a combination that was never observed in the source data. A target may be unreachable, and the search does not guarantee a global optimum. Results are currently returned synchronously and are not persisted as prediction-history entries.

Future improvements may add cross-feature constraints, weighted objectives, classification support, uncertainty estimates, persisted simulation history, and queued asynchronous execution.

## Improvement opportunities

The current reverse search is useful for bounded, model-consistent recommendations, but the following improvements would make it more reliable in production:

1. **Cross-feature constraints (highest priority).** Support rules such as `A + B <= limit`, valid category/value pairings, ratios, and features that must change together. Independent column bounds can otherwise produce combinations that are statistically or operationally invalid.
2. **Stronger training-data grounding.** Use a real training row close to the requested conditions as the fixed-value baseline, show feature distributions, and indicate whether a recommendation resembles observed data. This is safer than relying only on independent medians and modes.
3. **Recommendation confidence and extrapolation warnings.** Report distance to nearby training rows, whether values are near a bound, whether the combination lies in a sparse region, and (when available) prediction uncertainty. A low target error alone does not make a recommendation trustworthy.
4. **More objective functions.** Add target intervals, minimize/maximize objectives, multiple targets, and weighted penalties for cost, energy, or constraint violations. A composite objective can balance target error with operating cost.
5. **Search efficiency and operations.** Add early stopping, prediction caching, feature-importance-guided exploration, asynchronous queue execution for large searches, progress reporting, and cancellation. These reduce latency without changing the model boundary.
6. **Sensitivity explanations.** Show which features most affect the predicted Y and how changing each feature moves the result. This helps users understand why a combination was recommended.
7. **Result presentation and export.** Improve result cards with ranking, parameter-difference indicators, copy actions, explanation text, and CSV/JSON export. The current table remains the canonical result view.
8. **Classification objectives.** For classification models, support a target class or minimum probability and return combinations with their predicted class probabilities. This is a larger extension after constraints and confidence are in place.

### Recommended order

Implement cross-feature constraints first, followed by training-data grounding and confidence/extrapolation signals. Then add early stopping, caching, and queued execution; add target intervals and cost penalties after that. Classification support should follow these reliability improvements. This order prioritizes preventing invalid recommendations before optimizing speed or expanding model types.
