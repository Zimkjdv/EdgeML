# Project

## Vision

EdgeML is an enterprise-oriented, internally deployable machine-learning prediction platform for tabular datasets. During the early milestones, a focused regression-training workflow is integrated into the same application to validate the complete dataset-to-prediction experience. The long-term architecture will separate training into a dedicated AutoML platform while EdgeML remains focused on model deployment and prediction.

## Roadmap

| Version | Scope |
| --- | --- |
| v0.1 | CSV dataset profiling, regression training and evaluation, draft-to-published model lifecycle, and stateless batch prediction |
| v0.2 | Prediction history and durable job metadata |
| v0.3 (in progress) | Classification training for the supported ensemble algorithms and Logistic Regression; Ridge and richer feature controls remain planned |
| v0.4 (deferred) | SHAP explainability and prediction insights |
| v0.5 (completed) | Model registry and expanded model lifecycle management, including the registry management UI |
| v0.6 | REST API tokens and access control |
| v0.7.1 (completed) | Structured logs, request tracing, metrics, and health/readiness checks |
| v0.7.2 (completed) | Queue-backed training workers for long-running concurrent training; Docker runtime flow verified end to end |
| v0.7.3 (in progress) | Backend bounded retries, dead-letter routing, and graceful worker shutdown; Queue Operations UI, worker capacity controls, and runtime integration tests remain |
| v0.8 (planned) | Frontend observability dashboard for health, jobs, predictions, and operational errors |
| v1.0 | Separate the integrated training workflow into a standalone AutoML platform with production orchestration and experiment tracking |

## Principles

Plugin first, SOLID, dependency injection, configuration-driven design, API first, stateless requests, and container-ready delivery. Production-ready by design, incrementally delivered.

## Included executable examples

v0.1 provides a regression example (`HousePrice`) and two classification examples (`CreditRisk` and `CustomerChurn`). Each is a separate model package, manifest, build script, and input CSV, exercising the same plugin and API boundary.
