#!/bin/bash

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "======================================="
echo "Starting Payroll Management System"
echo "======================================="

#########################################
# Backend
#########################################

cd "$ROOT_DIR/backend"

# Create virtual environment if missing
if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

# Install/update dependencies
pip install -r requirements.txt

#########################################
# Frontend
#########################################

cd "$ROOT_DIR/frontend"

# Install dependencies only once
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

exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000
