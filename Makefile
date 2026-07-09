.PHONY: compose-up compose-down clean-start test-ui help

# Default target
help:
	@echo "Available targets:"
	@echo "  make compose-up     - Build containers manually and start services"
	@echo "  make compose-down   - Stop and remove all containers"
	@echo "  make clean-start    - Stop deployment, clean volumes, and start fresh"
	@echo "  make test-ui        - Run UI e2e tests"
	@echo "  make help           - Show this help message"

# Terminate deployment, clean volumes
clean:
	@echo "Stopping deployment and Cleaning volumes..."
	docker-compose down -v --remove-orphans

# Build containers manually and start services
compose-up: build-containers
	@echo "Starting services..."
	docker-compose up -d
	@echo "Services started successfully"

# Stop and remove all containers
compose-down:
	@echo "Stopping and removing all containers..."
	docker-compose down
	@echo "Deployment stopped"

# Terminate deployment, clean volumes, and start fresh
clean-start: clean build-containers
	@echo "Starting services..."
	docker-compose up -d
	@echo "Clean start completed successfully"

# Terminate deployment, clean volumes, and start fresh
build-containers:
	@echo "Building containers manually..."
	docker build -t ai-platform-swe-16-gen-control-plane ./services/control-plane
	docker build -t ai-platform-swe-16-gen-agent-service ./services/agent-service
	docker build -t ai-platform-swe-16-gen-agent-worker ./services/agent-worker -f ./services/agent-worker/Dockerfile.worker
	docker build -t ai-platform-swe-16-gen-web ./apps/web
	@echo "All containers built successfully"

# Run UI e2e tests
test-ui:
	@echo "Running UI e2e tests..."
	cd apps/web && npm run test:e2e
	@echo "UI e2e tests completed"
