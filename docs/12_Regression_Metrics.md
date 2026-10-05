# Regression evaluation

## Evaluate an already trained model

The model detail/evaluation card includes **Additional test evaluation**, with **Upload test CSV** and **Use existing dataset** options. Draft and Published models both support evaluation; no training worker or retraining is needed. CSV columns must include every training feature and the saved target as Ground Truth. Uploaded test CSVs are processed in memory and are not saved as datasets.

The model's saved missing-value policy applies: missing targets are removed; `numeric_imputer=drop` also removes missing selected features, while other policies use the saved preprocessor. Success updates only test metrics/summary scores and saves `test_evaluation` provenance (source, filename or dataset name/ID, input/evaluated/dropped row counts, evaluation time). The most recent successful test replaces previous test scores. Existing validation metrics and the fitted artifact are preserved. Errors leave previous test results intact. Details and list scores update immediately; provenance remains visible after reload.

Each fold now fits the full preprocessing/estimator pipeline once and uses that same estimator for fold scores, OOF predictions and (for binary classification) probabilities. The final artifact is then trained once on all usable rows. Five folds therefore require six fits, versus the previous eleven for regression or sixteen for binary classification. Scores retain their existing definitions. The training progress reports completed folds. Time/group classification rejects training folds that lack any target class rather than silently misaligning probability columns.

## Validation strategy

Training accepts `validation_strategy: random | time | group` (default `random`). `time` and `group` require `validation_column`, separate from the target. Time values must be finite numbers or valid datetimes; batch/time identifiers cannot be missing after row cleaning. Group validation requires at least as many distinct batches as folds.

Time validation sorts rows, splits distinct timestamps with an expanding training window, and keeps equal timestamps together. `time_gap` excludes that many distinct timestamps between training and validation, default zero. Initial warm-up rows are trained on but are not scored. Group validation keeps every batch entirely on one side of each fold. Preprocessing remains fitted only on each training fold. The final deployable model is fitted on all usable rows.

`validation_context` records strategy, total/evaluated/excluded row counts and the split column. The detail page prominently distinguishes legacy versus current evaluation and shows coverage. Legacy artifacts remain unchanged. Choose the split that matches actual use: random folds alone may overestimate performance for adjacent industrial measurements or repeated batches.

New trained records use `evaluation_version: oof-v2`. Validation metrics are calculated from all out-of-fold (OOF) predictions, paired with actual values by row position, including after missing rows are removed. External tests and prediction Ground Truth evaluation use the same metric function.

For actual values y and predictions p:

| Metric | Definition |
| --- | --- |
| MAE | mean(abs(y - p)) |
| RMSE | sqrt(mean((y - p)^2)) |
| MAPE (%) | 100 * mean(abs((y - p) / y)) |
| NRMSE | RMSE / (max(y) - min(y)); dimensionless, not percent |
| Maximum error | max(abs(y - p)) |
| Target mean | mean(y) |
| Pearson R | Pearson correlation of positionally paired y and p |
| R² | 1 - sum((y - p)^2) / sum((y - mean(y))^2) |

MAPE is null if any actual value is zero; rows are not silently excluded and denominators are not replaced by epsilon. Near-zero values can still produce very large MAPE. Use MAE/RMSE when percentage errors are unsuitable.

NRMSE and R² are null for constant targets. R² also requires at least two rows. Pearson R is null for fewer than two rows or when either vector is constant. Nonfinite metric results become JSON null, displayed as an em dash. R² can be negative. High Pearson R does not imply small prediction error; fixed R² thresholds do not establish usefulness across all domains.

`cv_rmse_mean`, `cv_mae_mean`, and `cv_r2_mean` retain the separate fold-averaged scores. `rmse_std` is the population standard deviation (ddof=0) of fold RMSE, not NRMSE. Fold R² follows scikit-learn scoring conventions; it is not the headline OOF R².

Existing artifacts are not rewritten. Old validation scores require retraining with the original data and settings to produce the new OOF scores. Re-running external evaluation updates test scores only. The UI identifies records without the new evaluation version as legacy.

The trained-model detail card displays validation and test metrics together after selecting a model. Card visibility is controlled by Vue state, not CSS sibling positions: feature-importance and classification cards can change the order. The obsolete positional hiding rules were removed to restore the detail/rename cards without changing stored metrics or formulas.
