#!/bin/bash

# Configuration validation script for AVI to Kentik integration

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}============================================${NC}"
    echo -e "${BLUE}  AVI to Kentik Telegraf Configuration${NC}"
    echo -e "${BLUE}============================================${NC}"
}

print_section() {
    echo -e "\n${BLUE}[$1]${NC}"
}

print_success() {
    echo -e "  ${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "  ${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "  ${RED}✗${NC} $1"
}

check_file_exists() {
    if [ -f "$1" ]; then
        print_success "$1 exists"
        return 0
    else
        print_error "$1 not found"
        return 1
    fi
}

validate_env_var() {
    local var_name=$1
    local var_value=$2
    local default_value=$3
    
    if [ -z "$var_value" ]; then
        print_error "$var_name is not set"
        return 1
    elif [ "$var_value" = "$default_value" ]; then
        print_warning "$var_name still has default value"
        return 1
    else
        print_success "$var_name is configured"
        return 0
    fi
}

main() {
    print_header
    
    local errors=0
    
    # Check required files
    print_section "Required Files"
    
    check_file_exists "telegraf.conf" || ((errors++))
    check_file_exists "docker-compose.yml" || ((errors++))
    check_file_exists ".env.example" || ((errors++))
    
    if [ -f ".env" ]; then
        print_success ".env file exists"
        
        # Load environment variables
        source .env
        
        # Validate environment variables
        print_section "Environment Variables"
        
        validate_env_var "AVI_CONTROLLER_IP" "$AVI_CONTROLLER_IP" "your-avi-controller-ip" || ((errors++))
        validate_env_var "AVI_USERNAME" "$AVI_USERNAME" "your-avi-username" || ((errors++))
        validate_env_var "AVI_PASSWORD" "$AVI_PASSWORD" "your-avi-password" || ((errors++))
        validate_env_var "KENTIK_API_TOKEN" "$KENTIK_API_TOKEN" "your-kentik-api-token-here" || ((errors++))
        validate_env_var "KENTIK_API_EMAIL" "$KENTIK_API_EMAIL" "your-kentik-email@company.com" || ((errors++))
        
        # Optional variables
        if [ -n "$ENVIRONMENT" ] && [ "$ENVIRONMENT" != "production" ]; then
            print_success "ENVIRONMENT is set to: $ENVIRONMENT"
        else
            print_warning "ENVIRONMENT using default: production"
        fi
        
        if [ -n "$LOCATION" ] && [ "$LOCATION" != "your-datacenter-location" ]; then
            print_success "LOCATION is set to: $LOCATION"
        else
            print_warning "LOCATION using default value"
        fi
        
    else
        print_error ".env file not found"
        print_warning "Copy .env.example to .env and configure your settings"
        ((errors++))
    fi
    
    # Check Docker
    print_section "Docker Environment"
    
    if command -v docker &> /dev/null; then
        print_success "Docker is installed"
        
        # Check if Docker daemon is running
        if docker info &> /dev/null; then
            print_success "Docker daemon is running"
        else
            print_error "Docker daemon is not running"
            ((errors++))
        fi
    else
        print_error "Docker is not installed"
        ((errors++))
    fi
    
    if command -v docker-compose &> /dev/null; then
        print_success "Docker Compose is installed"
    else
        print_error "Docker Compose is not installed"
        ((errors++))
    fi
    
    # Check logs directory
    print_section "Directory Structure"
    
    if [ -d "logs" ]; then
        print_success "logs directory exists"
    else
        print_warning "logs directory not found (will be created automatically)"
    fi
    
    # Network connectivity check (if .env exists and is configured)
    if [ -f ".env" ] && [ "$errors" -eq 0 ]; then
        print_section "Network Connectivity"
        
        # Test AVI Controller connectivity
        if timeout 5 nc -z "$AVI_CONTROLLER_IP" 443 2>/dev/null; then
            print_success "AVI Controller ($AVI_CONTROLLER_IP:443) is reachable"
        else
            print_warning "Cannot reach AVI Controller at $AVI_CONTROLLER_IP:443"
        fi
        
        # Test Kentik endpoint connectivity
        if timeout 5 nc -z grpc.api.kentik.com 443 2>/dev/null; then
            print_success "Kentik API endpoint is reachable"
        else
            print_warning "Cannot reach Kentik API endpoint"
        fi
    fi
    
    # Summary
    print_section "Summary"
    
    if [ $errors -eq 0 ]; then
        print_success "Configuration validation passed!"
        echo -e "\n${GREEN}Ready to deploy. Run: ./deploy.sh start${NC}\n"
        exit 0
    else
        print_error "Found $errors configuration issues"
        echo -e "\n${RED}Please fix the issues above before deploying${NC}\n"
        exit 1
    fi
}

main "$@"
