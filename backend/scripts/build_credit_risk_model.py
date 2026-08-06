"""Build the deterministic CreditRisk classification artifact."""
from pathlib import Path

import joblib
import pandas as pd
from sklearn.linear_model import LogisticRegression

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "ml_models" / "CreditRisk" / "model.pkl"


def main() -> None:
    features = pd.DataFrame(
        {
            "Income": [28, 35, 42, 48, 55, 62, 70, 85, 95, 110],
            "DebtRatio": [0.72, 0.61, 0.55, 0.43, 0.39, 0.32, 0.28, 0.21, 0.18, 0.12],
            "CreditHistoryYears": [1, 2, 3, 5, 6, 8, 10, 12, 15, 20],
        }
    )
    # 1 = low risk / approved, 0 = high risk / declined.
    target = [0, 0, 0, 0, 1, 1, 1, 1, 1, 1]
    model = LogisticRegression(random_state=42).fit(features, target)
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    print(f"Wrote {MODEL_PATH}")


if __name__ == "__main__":
    main()

