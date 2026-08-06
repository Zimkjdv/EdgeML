"""Build the deterministic HousePrice artifact used by the v0.1 example."""
from pathlib import Path
import sys

import joblib
import pandas as pd
from sklearn.linear_model import LinearRegression

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MODEL_PATH = ROOT / "ml_models" / "HousePrice" / "model.pkl"


def main() -> None:
    features = pd.DataFrame(
        {
            "Area": [45, 60, 75, 90, 110, 130, 150],
            "Room": [1, 2, 2, 3, 3, 4, 5],
            "Age": [35, 28, 20, 15, 10, 5, 2],
        }
    )
    target = [210, 290, 355, 430, 525, 635, 745]
    model = LinearRegression().fit(features, target)
    joblib.dump(model, MODEL_PATH)
    print(f"Wrote {MODEL_PATH}")


if __name__ == "__main__":
    main()
