"""Build the deterministic CustomerChurn classification artifact."""
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "ml_models" / "CustomerChurn" / "model.pkl"


def main() -> None:
    features = pd.DataFrame(
        {
            "TenureMonths": [1, 2, 4, 6, 9, 12, 18, 24, 36, 48, 60, 72],
            "MonthlySpend": [80, 75, 72, 68, 62, 58, 55, 50, 45, 42, 40, 38],
            "SupportTickets": [6, 5, 5, 4, 4, 3, 2, 2, 1, 1, 0, 0],
        }
    )
    # 1 = likely to churn, 0 = likely to remain.
    target = [1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0]
    model = RandomForestClassifier(n_estimators=50, random_state=42).fit(features, target)
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    print(f"Wrote {MODEL_PATH}")


if __name__ == "__main__":
    main()

