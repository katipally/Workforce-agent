#!/bin/bash
# Production-ready startup script for Workforce AI Agent

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get project root
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "════════════════════════════════════════════════════════════════════════════════"
echo "                    WORKFORCE AI AGENT - STARTUP SCRIPT"
echo "════════════════════════════════════════════════════════════════════════════════"
echo ""
echo "📁 Project root: $PROJECT_ROOT"
echo ""

# ==============================================================================
# 1. CHECK PREREQUISITES
# ==============================================================================
echo -e "${BLUE}🔍 Checking prerequisites...${NC}"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}✗ Python 3 not found${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python 3:${NC} $(python3 --version)"

# Check Node
if ! command -v node &> /dev/null; then
    echo -e "${RED}✗ Node.js not found${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Node.js:${NC} $(node --version)"

# Check npm
if ! command -v npm &> /dev/null; then
    echo -e "${RED}✗ npm not found${NC}"
    exit 1
fi
echo -e "${GREEN}✓ npm:${NC} $(npm --version)"

# Check .env
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    echo -e "${RED}✗ .env file not found${NC}"
    exit 1
fi
echo -e "${GREEN}✓ .env file exists${NC}"

echo ""

# ==============================================================================
# 2. KILL EXISTING PROCESSES ON PORTS
# ==============================================================================
echo -e "${BLUE}🛑 Checking for existing processes on ports 8000 and 5173...${NC}"

# Function to kill process on port
kill_port() {
    local PORT=$1
    local PIDS=$(lsof -ti:$PORT 2>/dev/null)
    
    if [ -n "$PIDS" ]; then
        echo -e "  Killing processes on port $PORT: $PIDS"
        echo "$PIDS" | xargs kill -9 2>/dev/null || true
        sleep 1
        
        # Verify killed
        if lsof -ti:$PORT > /dev/null 2>&1; then
            echo -e "${RED}  ✗ Failed to kill process on port $PORT${NC}"
            return 1
        else
            echo -e "${GREEN}  ✓ Port $PORT cleared${NC}"
        fi
    else
        echo -e "  Port $PORT is free"
    fi
}

# Kill backend port
kill_port 8000

# Kill frontend port
kill_port 5173

echo ""

# ==============================================================================
# 3. CREATE LOGS DIRECTORY
# ==============================================================================
mkdir -p "$PROJECT_ROOT/logs"

# ==============================================================================
# 4. START BACKEND
# ==============================================================================
echo -e "${BLUE}🚀 Starting backend server...${NC}"

cd "$PROJECT_ROOT/backend"

# Start backend in background, redirect to log
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload > "$PROJECT_ROOT/logs/backend.log" 2>&1 &
BACKEND_PID=$!

echo "  Backend PID: $BACKEND_PID"
echo "  Log: tail -f logs/backend.log"

# Wait for backend to be ready
echo "  Waiting for backend to start..."
for i in {1..60}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        HEALTH=$(curl -s http://localhost:8000/health)
        echo -e "${GREEN}✓ Backend ready: $HEALTH${NC}"
        break
    fi
    
    # Check if process died
    if ! kill -0 $BACKEND_PID 2>/dev/null; then
        echo -e "${RED}✗ Backend process died. Check logs:${NC}"
        tail -20 "$PROJECT_ROOT/logs/backend.log"
        exit 1
    fi
    
    if [ $i -eq 60 ]; then
        echo -e "${RED}✗ Backend timeout. Last 20 lines of log:${NC}"
        tail -20 "$PROJECT_ROOT/logs/backend.log"
        exit 1
    fi
    
    sleep 1
done

echo ""

# ==============================================================================
# 5. START FRONTEND
# ==============================================================================
echo -e "${BLUE}🎨 Starting frontend server...${NC}"

cd "$PROJECT_ROOT/frontend"

# Start frontend in background
npm run dev > "$PROJECT_ROOT/logs/frontend.log" 2>&1 &
FRONTEND_PID=$!

echo "  Frontend PID: $FRONTEND_PID"
echo "  Log: tail -f logs/frontend.log"

# Wait for frontend to be ready
echo "  Waiting for frontend to start..."
for i in {1..60}; do
    if curl -s http://localhost:5173 > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Frontend ready${NC}"
        break
    fi
    
    # Check if process died
    if ! kill -0 $FRONTEND_PID 2>/dev/null; then
        echo -e "${RED}✗ Frontend process died. Check logs:${NC}"
        tail -20 "$PROJECT_ROOT/logs/frontend.log"
        exit 1
    fi
    
    if [ $i -eq 60 ]; then
        echo -e "${RED}✗ Frontend timeout. Last 20 lines of log:${NC}"
        tail -20 "$PROJECT_ROOT/logs/frontend.log"
        exit 1
    fi
    
    sleep 1
done

echo ""

# ==============================================================================
# 6. SAVE PIDs
# ==============================================================================
echo "$BACKEND_PID" > "$PROJECT_ROOT/logs/backend.pid"
echo "$FRONTEND_PID" > "$PROJECT_ROOT/logs/frontend.pid"

# ==============================================================================
# 7. FINAL STATUS
# ==============================================================================
echo "════════════════════════════════════════════════════════════════════════════════"
echo -e "                           ${GREEN}✅ ALL SERVERS RUNNING${NC}"
echo "════════════════════════════════════════════════════════════════════════════════"
echo ""
echo -e "${BLUE}📊 Server Status:${NC}"
echo "  Backend:  http://localhost:8000 (PID: $BACKEND_PID)"
echo "            http://localhost:8000/docs"
echo "            http://localhost:8000/health"
echo ""
echo "  Frontend: http://localhost:5173 (PID: $FRONTEND_PID)"
echo ""
echo -e "${BLUE}📝 Logs:${NC}"
echo "  tail -f logs/backend.log"
echo "  tail -f logs/frontend.log"
echo ""
echo -e "${BLUE}🛑 To stop:${NC}"
echo "  ./STOP_SERVERS.sh"
echo ""
echo "════════════════════════════════════════════════════════════════════════════════"
echo ""

# Open browser (macOS)
if command -v open &> /dev/null; then
    sleep 2
    open http://localhost:5173 2>/dev/null || true
fi
