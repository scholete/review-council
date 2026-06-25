#!/bin/bash

# Review Council - Start script

echo "=== Review Council ==="
echo ""

# Check .env
if [ ! -f .env ]; then
  echo "WARNING: No .env file found. Copy .env.example and fill in your API keys."
  echo ""
fi

# Start backend
echo "Starting backend on http://localhost:8001..."
uv run python -m backend.main &
BACKEND_PID=$!

# Wait a moment for backend to start
sleep 2

# Start frontend
echo "Starting frontend on http://localhost:5173..."
cd frontend
npm run dev &
FRONTEND_PID=$!

echo ""
echo "✓ Review Council is running!"
echo "  Backend:  http://localhost:8001"
echo "  Frontend: http://localhost:5173"
echo "  API docs: http://localhost:8001/docs"
echo ""
echo "Submit a PR or paste a diff for council review."
echo ""
echo "Press Ctrl+C to stop both servers"

# Wait for Ctrl+C
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" SIGINT SIGTERM
wait
