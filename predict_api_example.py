"""Example client for the EdgeML JSON prediction API."""

from __future__ import annotations

from urllib.parse import quote

import requests

API_ROOT = "http://localhost:8000/api"
PREDICT_API_URL = f"{API_ROOT}/predict/json"


def get_model_id_by_name(model_name: str) -> str:
    """Resolve a model display name through GET /api/models/by-name/{model_name}."""
    encoded_name = quote(model_name, safe="")
    response = requests.get(f"{API_ROOT}/models/by-name/{encoded_name}", timeout=30)
    if not response.ok:
        print(f"Model lookup failed ({response.status_code}): {response.text}")
        response.raise_for_status()
    return response.json()["id"]


def main() -> None:
    model_id = get_model_id_by_name("HousePrice")
    payload = {
        "model_id": model_id,
        "data": [
            {"Area": 80, "Room": 2, "Age": 15},
            {"Area": 120, "Room": 3, "Age": 8},
        ],
    }

    response = requests.post(PREDICT_API_URL, json=payload, timeout=60)
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
