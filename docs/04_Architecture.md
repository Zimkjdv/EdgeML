# Architecture

```text
Vue UI -> FastAPI router -> PredictionService -> ModelCatalog -> BasePredictor plugin
                                            -> CSV validation

Vue UI -> FastAPI router -> DatasetService -> trusted CSV + profile metadata
                       -> TrainingService -> sklearn Pipeline artifact -> ModelCatalog publication
```

Routers only handle HTTP. `PredictionService` coordinates validation and prediction. `ModelCatalog` scans model folders and constructs a validated `ModelManifest`. `PredictorFactory` chooses a `BasePredictor` implementation from the manifest's `framework` field.

Each runtime adapter implements `load`, `predict`, `predict_proba`, `explain`, and `metadata`. v0.1 includes `SklearnPredictor`; XGBoost, LightGBM, CatBoost, ONNX, TensorFlow, and Torch are future plugins.

## Model package

```text
ml_models/HousePrice/
├─ model.pkl
├─ preprocess.pkl       # optional; prefer a single serialized sklearn Pipeline
├─ metadata.json
├─ requirements.txt     # documentation and build-time dependency declaration only
└─ README.md
```

Artifacts are trusted deployment inputs. Model packages are mounted or baked into an image by an operator; the API never accepts serialized models.

The executable development examples are built together with `python scripts/build_example_models.py`.

## Training module

The initial training module is regression-only. A user selects one numeric target and explicitly checks feature columns. `TrainingService` fits imputers and categorical encoders inside a sklearn `Pipeline`, so each cross-validation fold fits preprocessing only from its training partition. The pipeline is serialized as one artifact and published only after evaluation.

Training executes as a local background job. The job record persists queued/running/completed/failed status and stage progress so the UI can show real server-side progress rather than simulated client progress. This is intentionally a lightweight local implementation; a future multi-user deployment will replace it with a queue and worker service.

Model manifests use the actual pandas dtype of each selected feature. Prediction validation therefore knows which uploaded CSV columns must be numeric, while categorical columns continue through the fitted encoder.

XGBoost is used through `XGBRegressor` inside this trusted sklearn pipeline. The Prediction Server therefore uses the existing sklearn artifact adapter while retaining an XGBoost dependency in its runtime image.
