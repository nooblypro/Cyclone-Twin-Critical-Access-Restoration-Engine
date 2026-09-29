# ==============================================================================
# CYCLONE TWIN — GOOGLE CLOUD RUN PRODUCTION DOCKERFILE
# FastAPI + NetworkX + GeoPandas + GCP SDK Infrastructure Container
# ==============================================================================

FROM python:3.13-slim as base

# Prevent Python from writing .pyc files & enable unbuffered stdout/stderr
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

# Install system dependencies for C-extensions (Shapely, GeoPandas, PyPROJ)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgdal-dev \
    libproj-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first to leverage Docker layer caching
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source code and package data
COPY cyclone_twin/ ./cyclone_twin/

# Create a non-privileged user for runtime security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

# Cloud Run injects $PORT (default 8080); uvicorn binds to 0.0.0.0
CMD exec uvicorn cyclone_twin.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 2
