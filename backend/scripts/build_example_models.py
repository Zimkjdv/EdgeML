"""Build all deterministic artifacts that make the v0.1 sample executable."""
from build_credit_risk_model import main as build_credit_risk
from build_customer_churn_model import main as build_customer_churn
from build_example_model import main as build_house_price


if __name__ == "__main__":
    build_house_price()
    build_credit_risk()
    build_customer_churn()

