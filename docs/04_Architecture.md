# Architecture

```text
Vue UI -> FastAPI router -> PredictionService -> ModelCatalog -> BasePredictor plugin
                                            -> CSV validation
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
