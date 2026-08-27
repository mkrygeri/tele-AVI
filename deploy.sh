#!/bin/bash

# AVI to Kentik Telegraf Deployment Script

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is installed
check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    print_status "Docker and Docker Compose are installed"
}

# Check if .env file exists
check_env_file() {
    if [ ! -f ".env" ]; then
        print_warning ".env file not found. Creating from template..."
        if [ -f ".env.example" ]; then
            cp .env.example .env
            print_warning "Please edit .env file with your configuration before running the container"
            return 1
        else
            print_error ".env.example file not found"
            exit 1
        fi
    fi
    print_status ".env file found"
    return 0
}

# Validate environment variables
validate_config() {
    source .env
    
    # Check AVI configuration
    if [ -z "$AVI_CONTROLLER_IP" ] || [ "$AVI_CONTROLLER_IP" = "your-avi-controller-ip" ]; then
        print_error "AVI_CONTROLLER_IP not configured in .env file"
        return 1
    fi
    
    if [ -z "$AVI_USERNAME" ] || [ "$AVI_USERNAME" = "your-avi-username" ]; then
        print_error "AVI_USERNAME not configured in .env file"
        return 1
    fi
    
    if [ -z "$AVI_PASSWORD" ] || [ "$AVI_PASSWORD" = "your-avi-password" ]; then
        print_error "AVI_PASSWORD not configured in .env file"
        return 1
    fi
    
    if [ -z "$AVI_DEVICE_NAME" ] || [ "$AVI_DEVICE_NAME" = "your-avi-device-name" ]; then
        print_error "AVI_DEVICE_NAME not configured in .env file"
        return 1
    fi
    
    # Check Kentik configuration
    if [ -z "$KENTIK_API_TOKEN" ] || [ "$KENTIK_API_TOKEN" = "your-kentik-api-token-here" ]; then
        print_error "KENTIK_API_TOKEN not configured in .env file"
        return 1
    fi
    
    if [ -z "$KENTIK_API_EMAIL" ] || [ "$KENTIK_API_EMAIL" = "your-kentik-email@company.com" ]; then
        print_error "KENTIK_API_EMAIL not configured in .env file"
        return 1
    fi
    
    print_status "Configuration validation passed"
    return 0
}

# Create logs directory
create_logs_dir() {
    if [ ! -d "logs" ]; then
        mkdir -p logs
        print_status "Created logs directory"
    fi
}

# Test AVI Controller connectivity
test_avi_connectivity() {
    source .env
    
    print_status "Testing connectivity to AVI Controller at $AVI_CONTROLLER_IP..."
    
    # Test basic connectivity
    if timeout 10 nc -z "$AVI_CONTROLLER_IP" 443 2>/dev/null; then
        print_status "Successfully connected to AVI Controller on port 443"
    else
        print_warning "Could not connect to AVI Controller on port 443"
        print_warning "Please check network connectivity and firewall rules"
    fi
    
    # Test API endpoint (optional, requires curl)
    if command -v curl &> /dev/null; then
        print_status "Testing AVI API session login..."
        
        # AVI uses session login (POST /login), not HTTP Basic Auth
        response=$(curl -k -s -w "%{http_code}" -o /dev/null \
            --max-time 10 \
            -X POST \
            -H "Content-Type: application/json" \
            -d "{\"username\":\"$AVI_USERNAME\",\"password\":\"$AVI_PASSWORD\"}" \
            "https://$AVI_CONTROLLER_IP/login" 2>/dev/null || echo "000")
        
        if [ "$response" = "200" ]; then
            print_status "AVI API session login successful"
        elif [ "$response" = "401" ]; then
            print_error "AVI API login failed - check username/password"
        elif [ "$response" = "000" ]; then
            print_warning "Could not reach AVI API endpoint"
        else
            print_warning "AVI API returned HTTP status: $response"
        fi
    fi
}

# Start services
start_services() {
    print_status "Starting Telegraf container..."
    
    # Pull latest image
    docker-compose pull
    
    # Start services
    docker-compose up -d
    
    # Wait a moment for container to start
    sleep 5
    
    # Check container status
    if docker-compose ps | grep -q "Up"; then
        print_status "Telegraf container started successfully"
        
        # Show logs
        print_status "Container logs (last 20 lines):"
        docker-compose logs --tail=20 telegraf
        
        print_status "To monitor logs in real-time, run: docker-compose logs -f telegraf"
        print_status "To check container status, run: docker-compose ps"
        print_status "To stop the service, run: docker-compose down"
        
    else
        print_error "Failed to start Telegraf container"
        print_error "Container logs:"
        docker-compose logs telegraf
        exit 1
    fi
}

# Stop services
stop_services() {
    print_status "Stopping Telegraf container..."
    docker-compose down
    print_status "Services stopped"
}

# Show status
show_status() {
    print_status "Container status:"
    docker-compose ps
    
    print_status "Recent logs:"
    docker-compose logs --tail=10 telegraf
}

# Show logs
show_logs() {
    docker-compose logs -f telegraf
}

# Main script logic
case "${1:-}" in
    "start")
        check_docker
        if check_env_file && validate_config; then
            create_logs_dir
            test_avi_connectivity
            start_services
        else
            print_error "Configuration validation failed. Please check .env file."
            exit 1
        fi
        ;;
    "stop")
        stop_services
        ;;
    "restart")
        stop_services
        sleep 2
        $0 start
        ;;
    "status")
        show_status
        ;;
    "logs")
        show_logs
        ;;
    "test")
        check_docker
        if check_env_file && validate_config; then
            test_avi_connectivity
        fi
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs|test}"
        echo ""
        echo "Commands:"
        echo "  start   - Start the Telegraf container"
        echo "  stop    - Stop the Telegraf container"
        echo "  restart - Restart the Telegraf container"
        echo "  status  - Show container status and recent logs"
        echo "  logs    - Follow container logs"
        echo "  test    - Test configuration and connectivity"
        echo ""
        exit 1
        ;;
esac
