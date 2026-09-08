#!/usr/bin/env bash
# Starts both the Django API (:8000) and the Vite frontend (:5173).
# Ctrl+C stops both.
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -d "$ROOT_DIR/backend/venv" ]; then
  echo "backend/venv not found — run:"
  echo "  cd backend && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

if [ ! -d "$ROOT_DIR/frontend/node_modules" ]; then
  echo "frontend/node_modules not found — run:"
  echo "  cd frontend && npm install"
  exit 1
fi

cleanup() {
  echo ""
  echo "Stopping servers..."
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
  wait "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

(
  cd "$ROOT_DIR/backend"
  source venv/bin/activate
  python manage.py runserver 0.0.0.0:8000
) &
BACKEND_PID=$!

(
  cd "$ROOT_DIR/frontend"
  npm run dev -- --host 0.0.0.0 --port 5173
) &
FRONTEND_PID=$!

echo "API:      http://localhost:8000/api/"
echo "Frontend: http://localhost:5173/"
echo "Press Ctrl+C to stop both."

wait "$BACKEND_PID" "$FRONTEND_PID"
