# Regression evaluation

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
