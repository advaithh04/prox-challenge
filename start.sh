#!/bin/bash

# Vulcan OmniPro 220 Assistant - Startup Script
# This script starts both the backend and frontend servers

set -e

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║        Vulcan OmniPro 220 AI Assistant                        ║"
echo "║        Starting services...                                   ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

# Check for .env file
if [ ! -f ".env" ]; then
    echo "⚠️  No .env file found. Creating from .env.example..."
    cp .env.example .env
    echo "📝 Please edit .env and add your API key"
    echo ""
fi

# Create knowledge directory if it doesn't exist
mkdir -p knowledge

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "🛑 Shutting down services..."
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM

# Start backend
echo "🔧 Starting backend server..."
cd backend

# Check if virtual environment exists, create if not
if [ ! -d "venv" ]; then
    echo "   Creating Python virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies if needed
if [ ! -f "venv/.installed" ]; then
    echo "   Installing Python dependencies..."
    pip install -r requirements.txt -q
    touch venv/.installed
fi

# Run knowledge extraction if needed
if [ ! -f "../knowledge/knowledge_index.json" ]; then
    echo "   Extracting knowledge from PDFs..."
    python knowledge_extractor.py
fi

# Start the backend server
echo "   Starting FastAPI server on port 8000..."
uvicorn main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
cd ..

# Wait for backend to be ready
echo "   Waiting for backend to be ready..."
sleep 3

# Start frontend
echo ""
echo "🎨 Starting frontend server..."
cd frontend

# Install npm dependencies if needed
if [ ! -d "node_modules" ]; then
    echo "   Installing npm dependencies..."
    npm install --silent
fi

# Start the frontend server
echo "   Starting Next.js server on port 3000..."
npm run dev &
FRONTEND_PID=$!
cd ..

# Wait for frontend to be ready
sleep 5

echo ""
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║  ✅ All services started successfully!                        ║"
echo "║                                                               ║"
echo "║  🌐 Frontend:  http://localhost:3000                          ║"
echo "║  🔌 Backend:   http://localhost:8000                          ║"
echo "║  📚 API Docs:  http://localhost:8000/docs                     ║"
echo "║                                                               ║"
echo "║  Press Ctrl+C to stop all services                            ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

# Wait for processes
wait
