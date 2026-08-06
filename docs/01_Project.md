# Project

## Vision

EdgeML is an enterprise-oriented, internally deployable machine-learning edge prediction platform. It starts with dependable batch prediction and evolves only when each new capability is needed.

## Roadmap

| Version | Scope |
| --- | --- |
| v0.1 | Prediction server |
| v0.2 | Prediction history |
| v0.3 | SHAP explainability |
| v0.4 | Model management |
| v0.5 | REST API tokens |
| v0.6 | Monitoring |
| v1.0 | Training platform |

## Principles

Plugin first, SOLID, dependency injection, configuration-driven design, API first, stateless requests, and container-ready delivery. Production-ready by design, incrementally delivered.

## Included executable examples

v0.1 provides a regression example (`HousePrice`) and two classification examples (`CreditRisk` and `CustomerChurn`). Each is a separate model package, manifest, build script, and input CSV, exercising the same plugin and API boundary.
