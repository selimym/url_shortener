FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY shortener_app ./shortener_app
COPY alembic ./alembic
COPY alembic.ini .

# Expose port
EXPOSE 8000

# Run migrations then start server
CMD ["sh", "-c", "alembic upgrade head && uvicorn shortener_app.main:app --host 0.0.0.0 --port 8000"]
