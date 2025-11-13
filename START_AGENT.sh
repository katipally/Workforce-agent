#!/bin/bash

# Workforce AI Agent - Quick Start Script
# Starts both backend and frontend servers

echo "🚀 Starting Workforce AI Agent..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}⚠️  Warning: .env file not found${NC}"
    echo "   Copy .env.example to .env and fill in your API keys"
    echo ""
fi

# Start backend
echo -e "${BLUE}📦 Starting Backend Server...${NC}"
cd backend
python -m uvicorn api.main:app --reload --port 8000 &
BACKEND_PID=$!
echo "   Backend PID: $BACKEND_PID"
cd ..

# Wait a moment for backend to start
sleep 3

# Start frontend  
echo ""
echo -e "${BLUE}🎨 Starting Frontend Server...${NC}"
cd frontend
npm run dev &
FRONTEND_PID=$!
echo "   Frontend PID: $FRONTEND_PID"
cd ..

echo ""
echo -e "${GREEN}✅ Servers Started!${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📍 Access your agent at:"
echo "   Frontend: http://localhost:5173"
echo "   Backend:  http://localhost:8000"
echo "   API Docs: http://localhost:8000/docs"
echo ""
echo "🎯 Try these commands:"
echo '   "Track the Q4 Dashboard project"'
echo '   "List all Slack channels"'
echo '   "Search for emails from ivan@datasaur.ai"'
echo '   "Update Notion page abc123 with project status"'
echo ""
echo "Press Ctrl+C to stop all servers"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Wait for user interrupt
trap "echo ''; echo '🛑 Stopping servers...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo '✅ Servers stopped'; exit 0" INT

wait
