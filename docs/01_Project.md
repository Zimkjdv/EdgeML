# Project

## Vision

EdgeML is an enterprise-oriented, internally deployable machine-learning prediction platform for tabular datasets. During the early milestones, a focused regression-training workflow is integrated into the same application to validate the complete dataset-to-prediction experience. The long-term architecture will separate training into a dedicated AutoML platform while EdgeML remains focused on model deployment and prediction.

## Roadmap

| Version | Scope |
| --- | --- |
| v0.1 | CSV dataset profiling, regression training and evaluation, draft-to-published model lifecycle, and stateless batch prediction |
| v0.2 | Prediction history and durable job metadata |
| v0.3 | Classification training, Ridge regression, additional algorithms, and richer feature controls |
| v0.4 (deferred) | SHAP explainability and prediction insights |
| v0.5 (in progress) | Model registry and expanded model lifecycle management |
| v0.6 | REST API tokens and access control |
| v0.7 | Monitoring, structured observability, and queue-backed training workers |
| v1.0 | Separate the integrated training workflow into a standalone AutoML platform with production orchestration and experiment tracking |

## Principles

Plugin first, SOLID, dependency injection, configuration-driven design, API first, stateless requests, and container-ready delivery. Production-ready by design, incrementally delivered.

## Included executable examples

v0.1 provides a regression example (`HousePrice`) and two classification examples (`CreditRisk` and `CustomerChurn`). Each is a separate model package, manifest, build script, and input CSV, exercising the same plugin and API boundary.
