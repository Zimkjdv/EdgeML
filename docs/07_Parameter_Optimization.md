# Parameter optimization simulation

This feature searches for input combinations X whose model-predicted Y is close to a user-specified numeric target. It does not invert or retrain the model. Several different inputs may produce the same output, and some targets cannot be reached within the chosen bounds.

## User workflow

1. Open **Parameter Optimization** and choose a model source: locally trained models (including drafts), or active registry models. Only regression models are available in this initial implementation.
2. Select the model and enter target Y, absolute tolerance, and 1–5 recommendations.
3. Check the features that may change. Every unchecked feature must have a fixed value.
4. For adjustable numeric features, enter minimum and maximum values and an optional step. A step is anchored at the minimum: `minimum + k * step`, never above the maximum. Integer features require integer bounds and steps (default step 1).
5. For adjustable categorical features, enter the allowed category labels and press Enter after each label. Use the same labels as the training data.
6. Optionally import fixed inputs from a CSV as described below, preview a data row, and apply it before simulation.
7. Run the simulation. Compare predicted Y, absolute target error, tolerance status, and only the selected adjustable features for each recommendation. Fixed inputs still participate in prediction and remain visible in the editor's Fixed filter; they are omitted from the result table.

Bounds and fixed values are prefilled from training statistics: numeric minima/maxima and medians, or categorical modes and up to 100 allowed labels. Integer defaults use the observed value nearest the median. All values remain editable. Constant numeric features are fixed initially. Columns without usable observations still require manual values. These independent column defaults may not describe a combination actually observed in training. Use actual operating values where available; training ranges are not safety limits. Predictions do not establish causal effects or guarantee production outcomes.

New training runs preserve `training_dataset_id` and `feature_defaults` in both `metadata.json` and the record manifest, so publication retains them and defaults survive dataset removal. Older models use `record.json -> settings.dataset_id` to find the original dataset, excluding rows missing the target and following the training drop-missing setting. Old registered models are linked back to their local training record by model ID. If neither a snapshot nor source data exists, the UI explicitly asks for manual input. Existing artifacts are not rewritten automatically.

`GET /api/optimization/models/{model_id}/defaults?source=trained` (or `registry`) returns `origin`, `dataset_id`, and per-feature defaults. The UI ignores stale responses when switching models. Open Optimization from the Predict & simulate group in the shared sidebar.

## Search behavior

High-priority review changes are recorded in [Optimization review](13_Optimization_Review.md). Enable baseline comparison to edit current values for adjustable inputs and compare baseline predicted Y and per-feature changes. Baselines default to training statistics and must be checked against actual operating values. Invalid fields are reported immediately with click-to-locate navigation.

### Importing fixed inputs from CSV

Select the adjustable features first, then use **Import fixed features from CSV**. The file must be UTF-8 (a UTF-8 BOM is accepted), include feature names in its header, and contain at least one data row. Header matching is case-sensitive after trimming surrounding whitespace. Include every currently fixed feature. Adjustable feature columns and unrelated columns (for example the target Y) are ignored; they do not change search bounds or the requested target.

For example, if `Speed` is adjustable and `Weight` and `Grade` are fixed:

```csv
Weight,Grade
225,A
230,B
```

Choose data row 1 or 2 (the header is not counted), optionally expand the fixed-value preview, then select **Apply to fixed features**. All fixed inputs come from that single row, not per-column averages. Files may also contain the full model feature set. Multi-row files do not start multiple simulations automatically.

Import validates all fixed values before applying any changes. Missing fixed headers, empty fixed values, invalid/nonfinite numeric values, fractional or unsafe integer values, duplicate/empty headers, malformed quotes, and inconsistent row widths are rejected. Numeric values support decimal/scientific notation; categorical strings retain leading zeros. Surrounding value whitespace is trimmed. Quoted commas, escaped quotes, quoted newlines, CRLF, and blank lines are supported.

Limits are 5 MB, 10,000 data rows, 512 columns, and 1,000 characters per cell. Parsing occurs locally in the browser; the file is not uploaded to Dataset Management or stored on the server. The applied fixed values are included in the next normal simulation request. Changing the selected CSV row only updates the preview until Apply is clicked. Clearing the file keeps already-applied fixed values. Restoring training defaults clears the import state and resets values; changing models clears the file as well. Fixed values remain manually editable after import.

The API still returns complete input combinations for reproducibility and integration compatibility; only the UI result table omits fixed features. Run `npm run test:csv` in `frontend` (Node 22.6+ with type stripping) for parser and import-validation tests.

### Feature editor controls

The editor separates model selection, target settings, and feature selection. Search by feature name and switch between All, Adjustable, and Fixed views. Filtering changes only visibility; every feature remains in the simulation request. Adjustable rows are highlighted, with explicit minimum/maximum/step labels. The compact table scrolls within a bounded height.

Restore training defaults resets all feature values, bounds, steps, and category choices while preserving the selected adjustable features; target settings are unchanged. It is unavailable when no defaults could be loaded. Detailed guidance and the random seed are in expandable sections. The sticky action bar shows total adjustable/fixed counts and requested recommendations; enter a target and select at least one adjustable feature to enable simulation.

The shared bilingual navigation uses a collapsible grouped sidebar with consistent typography and selected-page styling. The language switch stays at the right of the compact toolbar. See [Workspace navigation](08_Workspace_Navigation.md) for responsive and keyboard behavior.

The service uses seeded mixed-variable population search, with global random exploration and mutations around better candidates. Default limits are 256 candidates per iteration and 12 iterations (at most 3,072 distinct model evaluations). Configure `EDGEML_OPTIMIZATION_POPULATION` (16–512) and `EDGEML_OPTIMIZATION_ITERATIONS` (1–20) in the backend environment. Launchers currently read only the API token from the root `.env`; export other settings explicitly for local execution or add them to the Compose backend environment.

The objective is absolute error `abs(predicted_y - target_y)`. In-tolerance candidates are selected before out-of-tolerance candidates. Within each group, recommendations prefer differences of more than 3% of at least one adjustable numeric range, or a different category, then fill with distinct candidates at smaller distances. Diversity cannot displace available in-tolerance candidates with misses. Results are sorted by target error. Fewer recommendations are returned when not enough distinct candidates were found. Unreachable targets return the nearest candidates found with `within_tolerance: false`; global optimality is not guaranteed. Decimal steps are anchored at the minimum; the maximum is included only when aligned to that grid.

The seed makes a search repeatable for the same deterministic model, constraints, and runtime. Results and iteration history are returned directly and not persisted. Simulation does not create prediction-history entries. Requests run synchronously with bounded work; large models may take longer, and production-wide concurrency control is a follow-up.

## API

Both endpoints require the existing API authentication when enabled:

- `GET /api/optimization/models?source=trained`: regression model metadata and required features. Use `source=registry` for active registered models.
- `POST /api/optimization/simulate?source=trained`: simulate against the chosen model source. `source` is a query parameter, not a body field.

Example body (replace names and model ID with the selected model's metadata):

```json
{
  "model_id": "your-trained-model-id",
  "target": 11.58,
  "tolerance": 0.05,
  "count": 3,
  "seed": 42,
  "parameters": [
    {"name": "Speed", "optimize": true, "minimum": 410, "maximum": 520, "step": 1},
    {"name": "Weight", "optimize": false, "value": 331},
    {"name": "Grade", "optimize": true, "choices": ["A", "B"]}
  ]
}
```

Provide exactly one rule per model feature. Unknown/duplicate features, missing fixed values, invalid ranges, nonfinite values, empty category choices, classification models, or requests for more than five combinations are rejected. A nonexistent model returns 404; invalid request constraints return 422.

The response contains the model identity, target, tolerance, seed, number of evaluated candidates, best error by iteration, and `recommendations`. Each recommendation includes `parameters`, `prediction`, `absolute_error`, and `within_tolerance`.

## Architecture and follow-up

Routers translate HTTP only. `OptimizationService` depends on `ModelCatalog` and a predictor-provider protocol. `TrainedModelCatalog` exposes trusted training artifacts without publishing them; registered models use the existing registry boundary. No model artifacts are accepted through this API.

The supplied reference screenshots also describe capabilities outside this initial scope: multiple weighted models/targets, target intervals, classification objectives, cross-feature constraints, anomaly penalties, configurable diversity, calibrated confidence intervals, saved simulation history, CSV export, and queued cancellable simulations. These remain follow-up work. No confidence interval is fabricated from point predictions.
