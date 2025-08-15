#!/bin/bash

# Quick start script for Mock AVI Server

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    print_warning "Python3 not found. Installing dependencies via Docker instead."
    USE_DOCKER=true
else
    USE_DOCKER=false
fi

print_info "🚀 Starting Mock AVI Controller Server"

if [ "$USE_DOCKER" = true ]; then
    # Use Docker method
    print_info "Using Docker Compose for mock server..."
    docker-compose -f docker-compose.testing.yml up --build -d mock-avi
    
    print_info "Waiting for mock server to start..."
    sleep 10
    
    print_success "Mock AVI server is running in Docker!"
    print_info "🔗 Access at: https://localhost:8443"
    print_info "👤 Credentials: admin:admin123"
    print_info "📋 Test with: make mock-test"
    print_info "🛑 Stop with: docker-compose -f docker-compose.testing.yml down"
    
else
    # Use Python directly
    print_info "Installing Python dependencies..."
    if [ ! -d "venv" ]; then
        python3 -m venv venv
        print_info "Created Python virtual environment"
    fi
    
    source venv/bin/activate
    pip install -q -r requirements.txt
    
    print_info "Starting mock server..."
    print_success "Mock AVI server is running!"
    print_info "🔗 Access at: https://localhost:8443"
    print_info "👤 Credentials: admin:admin123"
    print_info "📋 Test with: ./test-mock-avi.py"
    print_info "🛑 Stop with: Ctrl+C"
    print_info ""
    print_info "Server output:"
    
    python3 mock-avi-server.py
fi
