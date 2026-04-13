FROM python:3.13-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements_mcp.txt .
RUN pip install --no-cache-dir -r requirements_mcp.txt

# ---------- Admin frontend build stage ----------
FROM node:22-slim AS frontend-build

WORKDIR /frontend
COPY admin/frontend/package.json admin/frontend/package-lock.json* ./
RUN npm ci --ignore-scripts 2>/dev/null || npm install --ignore-scripts
COPY admin/frontend/ .
RUN npm run build

# ---------- Runtime ----------
FROM base AS runtime

COPY gateway/ ./gateway/
COPY admin/ ./admin/
COPY alembic/ ./alembic/
COPY alembic.ini .
COPY mcp_secure_gateway.py .
COPY seed_policies.py .
COPY migrate_security.py .
COPY policies.json .
COPY entrypoint.sh .

COPY --from=frontend-build /frontend/dist ./admin/frontend/dist/

RUN chmod +x entrypoint.sh

RUN useradd --create-home --shell /bin/bash appuser
USER appuser

ENV HOST=0.0.0.0
ENV PORT=8000
EXPOSE 8000 8001

ENTRYPOINT ["./entrypoint.sh"]
