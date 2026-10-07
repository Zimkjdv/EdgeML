# Feature importance ranking

New training runs calculate and save `feature_importance.json` beside `model.pkl` and `record.json`. On completion, the UI selects the trained model and displays a descending horizontal bar chart, repeat standard deviations, and a Download ranking CSV button. Select another model in Trained Models to view its report. Labels support Traditional Chinese and English.

The card fills the available page width, aligning its left and right edges with the Model details and evaluation card below. The scrolling chart is capped at 360 px high, and bars are 12 px high with compact rows. It shows the top 10 features by default and provides a Show all / Show top 10 toggle plus a visible count. Long Chinese names wrap; narrow screens place bars below their labels. Switching views preserves the same zero axis and scale, including negative importance. JSON and CSV always contain the complete ranking, independent of the UI toggle.

## Method and interpretation

EdgeML uses permutation importance on original input columns through the fitted prediction pipeline. It works with numeric and categorical features, including pipelines with one-hot encoding or Truncated SVD. Each feature is shuffled independently while the other inputs are held unchanged. The model is not retrained for each shuffle.

- Regression: importance is shuffled RMSE minus baseline RMSE, in target units.
- Classification: importance is baseline accuracy minus shuffled accuracy, on a 0–1 accuracy scale (a drop of 0.10 means ten percentage points).
- Values are sorted descending without clipping negative importance. Ties retain original feature order. Zero indicates no measured change in this experiment; a negative value indicates improvement after shuffling.
- The standard deviation uses the repeat distribution (population standard deviation). It is not a confidence interval. Correlated inputs can share/mask importance; shuffling can create unrealistic combinations. These are model performance effects, not causal effects or percentages of contribution.

The source is the external test dataset selected during training, if present; otherwise the cleaned training dataset is used and marked as such in the UI/report. This is not out-of-fold importance. Training-data importance may be optimistic. Later external evaluation calls do not silently replace the importance source. Inspect the recorded dataset ID, source, sample count, baseline, metric, seed, and timestamp when interpreting a report.

The default uses at most 500 randomly sampled rows without replacement, three permutations per feature, and seed 42. Predictions are made once for the baseline and once per feature/repeat. Missing targets are removed; the training drop-missing setting is honored. At least two usable rows are required. Sampling is deterministic for unchanged data order/model/runtime. Configurable server settings are `EDGEML_IMPORTANCE_MAX_SAMPLES` (2–2000, default 500) and `EDGEML_IMPORTANCE_REPEATS` (1–10, default 3). Export them in the worker/backend environment; root batch `.env` parsing does not load these optional settings automatically.

Automatic calculation runs in the existing training job before completion and adds prediction work proportional to feature count. Reports are written atomically. Saved reports can be read after source datasets are removed, without reloading the predictor. Publishing copies the report with the model package. The `/api/models` endpoint reads this published snapshot, independently of any retained training record or dataset; the `/api/trained-models` endpoints read the training package.

## Existing models

Models trained before this feature show a Compute feature importance button. Computation uses the saved training settings and trusted artifact, without retraining. It requires the referenced original training or external test dataset. The button also allows retrying after an error. A missing dataset is reported rather than silently switching to a different dataset. Backfill runs synchronously; for large models it can take time. It does not enqueue a separate job in this version.

After computing or recomputing a report, explicitly publish the model again to update the prediction package's snapshot. Republishing atomically refreshes the report without replacing the existing `model.pkl`. Until then, `/api/models` returns the previous published report (or 409 if none was included). It never falls back to a mutable trained-model report. If neither a published report nor retained source data exists, this API cannot reconstruct a permutation ranking from the artifact alone.

## API

| Method and endpoint | Result |
| --- | --- |
| `GET /api/models/{model_id}/feature-importance` | Complete saved JSON ranking for an active Prediction model |
| `GET /api/models/{model_id}/feature-importance?format=csv` | Complete published ranking as a UTF-8 BOM CSV attachment |
| `GET /api/trained-models/{model_id}/feature-importance` | Saved JSON ranking and method metadata |
| `GET /api/trained-models/{model_id}/feature-importance?format=csv` | UTF-8 BOM CSV attachment |
| `POST /api/trained-models/{model_id}/feature-importance` | Compute/recompute, save, and return JSON; no request body |

GET returns 409 if the report is missing, unreadable, or invalid (including nonfinite ranking values); it never starts expensive computation implicitly. Unknown models return 404; the published endpoint also returns 404 for disabled models. Invalid format values return 422. Missing source data on POST returns 404; invalid feature/target data returns 422. Existing API-token and browser-session/CSRF rules apply. Direct integrations use a token with API access. The published endpoint is GET-only: recomputation belongs to the trained-model POST and explicit publication workflow.

For `/api/models`, use the `id` from `GET /api/models`, `/api/models/ids`, `/api/models/by-name/{model_name}`, or the registry's copy-ID button. This is the same `model_id` accepted by Prediction, **not** the package directory or display name. `model_id` and `model_name` in the response are resolved from the current catalog so renamed models retain their canonical identity.

Windows CMD examples (replace `MODEL_ID` with the trained-model UUID and set `EDGEML_API_TOKEN` in the terminal):

```bat
curl "http://localhost:8000/api/models/MODEL_ID/feature-importance" -H "Authorization: Bearer %EDGEML_API_TOKEN%"
curl --fail "http://localhost:8000/api/models/MODEL_ID/feature-importance?format=csv" -H "Authorization: Bearer %EDGEML_API_TOKEN%" -o published_feature_importance.csv
curl "http://localhost:8000/api/trained-models/MODEL_ID/feature-importance" -H "Authorization: Bearer %EDGEML_API_TOKEN%"
curl --fail "http://localhost:8000/api/trained-models/MODEL_ID/feature-importance?format=csv" -H "Authorization: Bearer %EDGEML_API_TOKEN%" -o feature_importance.csv
curl -X POST "http://localhost:8000/api/trained-models/MODEL_ID/feature-importance" -H "Authorization: Bearer %EDGEML_API_TOKEN%"
```

Use port 8010 for the default Docker backend. JSON includes `model_id`, `model_name`, `method`, `metric`, `baseline_score`, `data_source`, `dataset_id`, `sample_count`, `total_rows`, `repeats`, `seed`, `computed_at`, and `rankings`. Each ranked item has `rank`, `feature`, `importance`, and `std`. The CSV includes ranking values and method/source metadata on each row, in the same order and precision as JSON. Formula-like text cells are prefixed with an apostrophe for spreadsheet safety; JSON retains original names.

Python example (uses `requests`; do not hard-code tokens in source files):

```python
import os
import requests

model_id = "YOUR_MODEL_ID"
response = requests.get(
    f"http://localhost:8000/api/models/{model_id}/feature-importance",
    headers={"Authorization": f"Bearer {os.environ['EDGEML_API_TOKEN']}"},
    timeout=30,
)
response.raise_for_status()
for item in response.json()["rankings"]:
    print(item["rank"], item["feature"], item["importance"], item["std"])
```

## Verification and follow-up

Tests cover informative versus constant features, categorical classification, negative importance, repeatability, sample limits, automatic persistence, report reading after dataset removal, legacy backfill, path boundaries, JSON/CSV agreement, API authentication, canonical Prediction ID lookup, disabled/missing models, invalid reports, read-only access without model loading, and report refresh on explicit republication. Frontend tests verify top-10/all behavior, full-report preservation and compact/responsive layout constraints. Run `python -m pytest tests/test_feature_importance.py tests/test_training_algorithms.py -q` in backend, and `node --experimental-strip-types --test tests/*.test.mjs` plus `npm.cmd run build` in frontend.

For development-only visual checks with synthetic data, open `http://localhost:5173/tests/fixtures/featureImportance.preview.html` while Vite is running. It mounts the real component without authenticating, accessing source data, or running inference. It supports the top-10/all toggle and Chinese/English switch; this fixture is not included in the production build.

Held-out or cross-validated importance without an external test dataset, grouped correlated-feature analysis, and queued/cancellable backfill are future enhancements. No SHAP runtime or additional model training is introduced by this report.
