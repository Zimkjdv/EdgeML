FROM edgeml-ml-base:latest

WORKDIR /app
COPY . .
RUN python scripts/build_example_models.py
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
