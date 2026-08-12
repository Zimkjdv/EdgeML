"""Example client for the EdgeML JSON prediction API."""

from __future__ import annotations

import requests


API_URL = "http://localhost:8000/api/predict/json"


def main() -> None:
    payload = {
        "model_id": "house-price-v1",
        "source_name": "sales-service",
        "data": [
            {"Area": 80, "Room": 2, "Age": 15},
            {"Area": 120, "Room": 3, "Age": 8},
        ],
    }

    response = requests.post(API_URL, json=payload, timeout=60)
    if not response.ok:
        print(f"API request failed ({response.status_code}): {response.text}")
        response.raise_for_status()
    result = response.json()

    print(f"Model: {result['model_name']}")
    print(f"Prediction column: {result['prediction_column']}")
    print(f"Dropped rows: {result['dropped_rows']}")
    print("Predictions:")
    for row in result["records"]:
        print(row)


if __name__ == "__main__":
    main()
