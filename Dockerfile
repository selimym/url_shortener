# --- builder: install deps into an isolated venv ---
FROM python:3.12-slim AS builder
WORKDIR /app
RUN python -m venv /venv
COPY requirements.txt .
RUN /venv/bin/pip install --no-cache-dir --upgrade pip && \
    /venv/bin/pip install --no-cache-dir -r requirements.txt

# --- final: copy only the venv and app code ---
FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /venv /venv
ENV PATH="/venv/bin:$PATH"
COPY shortener_app ./shortener_app
COPY alembic ./alembic
COPY alembic.ini .

# Cloud Run injects PORT; default to 8000 for local docker-compose use
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn shortener_app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
