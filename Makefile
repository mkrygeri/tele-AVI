# Makefile for AVI to Kentik Telegraf Integration

.PHONY: help validate start stop restart status logs clean test setup mock-start mock-stop mock-test test-all

# Default target
help:
	@echo "Available commands:"
	@echo "  setup      - Initial setup (copy .env.example to .env)"
	@echo "  validate   - Validate configuration"
	@echo "  test       - Test connectivity to AVI Controller and Kentik"
	@echo "  start      - Start the Telegraf container"
	@echo "  stop       - Stop the Telegraf container"
	@echo "  restart    - Restart the Telegraf container"
	@echo "  status     - Show container status"
	@echo "  logs       - Show container logs"
	@echo "  clean      - Stop and remove containers, networks, and volumes"
	@echo ""
	@echo "Mock Testing Commands:"
	@echo "  mock-start - Start mock AVI server and Telegraf for testing"
	@echo "  mock-stop  - Stop mock testing environment"
	@echo "  mock-test  - Test mock AVI server endpoints"
	@echo "  test-all   - Complete end-to-end testing with mock server"
	@echo ""
	@echo "  help       - Show this help message"

# Initial setup
setup:
	@echo "Setting up AVI to Kentik integration..."
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env file from template"; \
		echo "Please edit .env with your configuration"; \
	else \
		echo ".env file already exists"; \
	fi
	@mkdir -p logs
	@echo "Created logs directory"
	@chmod +x deploy.sh validate-config.sh
	@echo "Made scripts executable"
	@echo "Setup complete! Next steps:"
	@echo "  1. Edit .env file with your configuration"
	@echo "  2. Run 'make validate' to check configuration"
	@echo "  3. Run 'make start' to deploy"

# Validate configuration
validate:
	@./validate-config.sh

# Test connectivity
test:
	@./deploy.sh test

# Start services
start:
	@./deploy.sh start

# Stop services
stop:
	@./deploy.sh stop

# Restart services
restart:
	@./deploy.sh restart

# Show status
status:
	@./deploy.sh status

# Show logs
logs:
	@./deploy.sh logs

# Clean up everything
clean:
	@echo "Cleaning up..."
	@docker-compose down -v --remove-orphans 2>/dev/null || true
	@docker system prune -f
	@echo "Cleanup complete"

# Advanced: Pull latest images
update:
	@echo "Updating Telegraf image..."
	@docker-compose pull
	@echo "Update complete. Run 'make restart' to use new image"

# Development: Check configuration syntax
check-config:
	@echo "Checking Telegraf configuration syntax..."
	@docker run --rm -v "$(PWD)/telegraf.conf:/etc/telegraf/telegraf.conf:ro" \
		telegraf:1.29-alpine telegraf --config /etc/telegraf/telegraf.conf --test

# Development: Generate sample data
sample:
	@echo "This would generate sample metrics for testing..."
	@echo "Not implemented yet"

# Mock server testing commands
mock-start:
	@echo "Starting mock AVI server and Telegraf for testing..."
	@docker-compose -f docker-compose.testing.yml up --build -d
	@echo "Waiting for services to start..."
	@sleep 10
	@echo "Mock environment started!"
	@echo "Mock AVI API: https://localhost:8443"
	@echo "Credentials: admin:admin123"

mock-stop:
	@echo "Stopping mock testing environment..."
	@docker-compose -f docker-compose.testing.yml down -v
	@echo "Mock environment stopped"

mock-test:
	@echo "Testing mock AVI server..."
	@python3 test-mock-avi.py

mock-logs:
	@echo "Mock AVI server logs:"
	@docker-compose -f docker-compose.testing.yml logs mock-avi
	@echo ""
	@echo "Telegraf logs:"
	@docker-compose -f docker-compose.testing.yml logs telegraf

test-all: mock-start
	@echo "Running complete end-to-end test..."
	@sleep 5
	@make mock-test
	@echo ""
	@echo "Testing Telegraf data collection..."
	@docker-compose -f docker-compose.testing.yml logs --tail=20 telegraf
	@echo ""
	@echo "✅ End-to-end testing complete!"
	@echo "To stop the test environment: make mock-stop"
