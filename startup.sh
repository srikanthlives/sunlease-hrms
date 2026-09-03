#!/bin/bash
# Single entrypoint for both local dev and the Docker image.
#
# - Inside a container (Dockerfile has already installed deps and built the
#   frontend), this just execs uvicorn.
# - On bare metal, it also creates the venv, installs deps, and builds the
#   frontend first.

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "======================================="
echo "Starting HRMS - Employee Data Management"
echo "======================================="

if [ -n "$HRMS_RUNNING_IN_DOCKER" ] || [ -f /.dockerenv ]; then
    cd /app
    echo "Starting FastAPI..."
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000
fi

#########################################
# Backend (bare-metal dev)
#########################################

cd "$ROOT_DIR/backend"

if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate
pip install -q -r requirements.txt

#########################################
# Frontend
#########################################

cd "$ROOT_DIR/frontend"

if [ ! -d "node_modules" ]; then
    npm install
fi

echo "Building React application..."
npm run build

#########################################
# Start FastAPI
#########################################

cd "$ROOT_DIR/backend"

echo "Starting FastAPI..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
