#!/bin/bash
# Stop all Workforce AI Agent servers

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "🛑 Stopping Workforce AI Agent servers..."
echo ""

# Stop by PID if available
if [ -f "$PROJECT_ROOT/logs/backend.pid" ]; then
    BACKEND_PID=$(cat "$PROJECT_ROOT/logs/backend.pid")
    if kill -0 $BACKEND_PID 2>/dev/null; then
        echo "  Stopping backend (PID: $BACKEND_PID)..."
        kill -9 $BACKEND_PID 2>/dev/null || true
    fi
    rm "$PROJECT_ROOT/logs/backend.pid"
fi

if [ -f "$PROJECT_ROOT/logs/frontend.pid" ]; then
    FRONTEND_PID=$(cat "$PROJECT_ROOT/logs/frontend.pid")
    if kill -0 $FRONTEND_PID 2>/dev/null; then
        echo "  Stopping frontend (PID: $FRONTEND_PID)..."
        kill -9 $FRONTEND_PID 2>/dev/null || true
    fi
    rm "$PROJECT_ROOT/logs/frontend.pid"
fi

# Also kill by port (backup)
if lsof -ti:8000 > /dev/null 2>&1; then
    echo "  Cleaning up port 8000..."
    lsof -ti:8000 | xargs kill -9 2>/dev/null || true
fi

if lsof -ti:5173 > /dev/null 2>&1; then
    echo "  Cleaning up port 5173..."
    lsof -ti:5173 | xargs kill -9 2>/dev/null || true
fi

sleep 1

echo ""
echo "✅ All servers stopped"
echo ""
