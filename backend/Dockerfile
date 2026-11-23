FROM python:3.12-slim-bookworm

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Expose default port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD sh -c "curl -f http://localhost:${PORT:-8000}/api/v1/ping || exit 1"

# Run pending database migrations up to the target revision before starting the application server
CMD ["sh", "-c", "alembic upgrade \"${ALEMBIC_TARGET_REVISION:-head}\" && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
