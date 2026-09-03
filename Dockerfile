# Multi-stage build for optimized final image
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm install --legacy-peer-deps

COPY frontend/ ./
RUN npm run build

# Python backend image
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app

# Copy built frontend dist from builder stage
COPY --from=frontend-builder /app/frontend/dist ./frontend_dist

# Shared entrypoint (also used for bare-metal dev - see README.md)
COPY startup.sh ./startup.sh
RUN chmod +x ./startup.sh

# Create data directory for the database (kept outside the app code dir so
# it survives image rebuilds when mounted as a volume, e.g. Railway's
# volume mount path of /data)
RUN mkdir -p /data

# Default DB location if not overridden by the deployment platform
ENV HRMS_DATABASE_URL=sqlite:////data/hrms.db

# Tells startup.sh it's running inside this image (deps/frontend already
# built) rather than bare metal - more reliable than checking /.dockerenv,
# which some container platforms (e.g. Railway) don't create.
ENV HRMS_RUNNING_IN_DOCKER=1

HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD ["./startup.sh"]
