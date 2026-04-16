# ============================================================
# Vault 33 — Production Docker Image
# ============================================================
# Build:   docker build -t vadertech/vault33:latest .
# Run:     docker-compose up -d
# CLI:     docker exec -it vault33 python vault33_cli.py stats
# ============================================================

FROM python:3.11-slim

LABEL maintainer="Vader Technologies"
LABEL description="Vault 33 — Encrypted, deduplicated, Merkle-verified storage engine"
LABEL version="2.0"

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Python deps
RUN pip install --no-cache-dir \
    cryptography \
    flask \
    flask-cors \
    gunicorn \
    tqdm

WORKDIR /app

# Copy source
COPY vault33_production.py .
COPY vault33_cli.py .
COPY vault33_api.py .

# Vault data directory (mount this as a volume in production)
RUN mkdir -p /vault_data && chmod 755 /vault_data

# Environment defaults (override in docker-compose or -e flags)
ENV VAULT33_DIR=/vault_data
ENV VAULT33_KEY=""
ENV VAULT33_PORT=8033
ENV VAULT33_CHUNK_MB=64
ENV VAULT33_WORKERS=4

# Expose API + dashboard port
EXPOSE 8033

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8033/health')"

CMD ["python", "vault33_api.py"]
