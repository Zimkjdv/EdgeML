import pandas as pd

from app.domain.training_schemas import TrainingRequest
from app.services.dataset_service import DatasetService
from app.services.training_service import TrainingService


def make_service(tmp_path):
    datasets = DatasetService(tmp_path / "datasets")
    return datasets, TrainingService(datasets, tmp_path / "trained", tmp_path / "models")


def test_logistic_regression_training(tmp_path) -> None:
    datasets, service = make_service(tmp_path)
    frame = pd.DataFrame({"feature": range(12), "target": ["low" if value < 6 else "high" for value in range(12)]})
    dataset = datasets.upload("logistic.csv", frame.to_csv(index=False).encode())

    result = service.train(TrainingRequest(
        dataset_id=dataset.id,
        model_name="Logistic Regression Test",
        problem_type="classification",
        target_column="target",
        feature_columns=["feature"],
        algorithm="logistic_regression",
        cv_folds=3,
        hyperparameters={"penalty": "l2", "solver": "lbfgs", "C": 1.0},
    ))

    assert result.problem_type == "classification"
    assert result.algorithm == "logistic_regression"
    assert result.validation_metrics["accuracy"] >= 0.5


def test_classification_training(tmp_path) -> None:
    datasets, service = make_service(tmp_path)
    frame = pd.DataFrame({
        "feature": list(range(20)),
        "segment": ["A", "B"] * 10,
        "target": ["low", "high"] * 10,
    })
    dataset = datasets.upload("classification.csv", frame.to_csv(index=False).encode())

    result = service.train(TrainingRequest(
        dataset_id=dataset.id,
        model_name="Classification Test",
        problem_type="classification",
        target_column="target",
        feature_columns=["feature", "segment"],
        algorithm="random_forest_classifier",
        cv_folds=3,
    ))

    assert result.problem_type == "classification"
    assert result.algorithm == "random_forest_classifier"
    assert result.validation_metrics["accuracy"] >= 0.5
    assert result.validation_rmse is None
