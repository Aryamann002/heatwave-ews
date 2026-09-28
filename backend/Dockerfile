FROM python:3.13.5-slim

WORKDIR /app
COPY backend/requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
COPY backend/ .
COPY config/ ./config/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
