# plinth-server repo: build context is this directory (repo root on Render).
#   docker build -t plinth-sip-api .
#
# plinth-sip monorepo: build from backend/ with the same Dockerfile; mount
#   ../configs at /configs in docker-compose for live config edits.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

ENV GDAL_CONFIG=/usr/bin/gdal-config
ENV CONFIGS_DIR=/configs

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Municipality JSON configs (committed under configs/municipalities/)
COPY configs/ /configs

EXPOSE 8000

# Migrations create tables + PostGIS (001_initial_schema). Re-runs are no-ops.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
