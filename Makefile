.PHONY: start compose-up compose-down clean-start test-ui help clean build-containers mock-llm-start start-local stop-local

# Default target
help:
	@echo "Available targets:"
	@echo "  make start          - Build containers and start all services"
	@echo "  make compose-up     - Build containers manually and start services"
	@echo "  make compose-down   - Stop and remove all containers"
	@echo "  make clean-start    - Stop deployment, clean volumes, and start fresh (destructive)"
	@echo "  make mock-llm-start  - Clean and start with mock LLM (LLM_PROVIDER=fake)"
	@echo "  make test-ui        - Run UI e2e tests"
	@echo "  make start-local SERVICES=web - Run specified services locally, others in docker-compose"
	@echo "  make stop-local SERVICES=web  - Stop local services (specified in SERVICES parameter)"
	@echo "  make help           - Show this help message"

# Terminate deployment, clean volumes
clean:
	@echo "Stopping deployment and Cleaning volumes..."
	docker-compose down -v --remove-orphans || true
	docker ps -q | xargs -r docker kill || true

# Build and start all services
start:
	@echo "Starting services..."
	docker-compose up
	@echo "Services started successfully"
	
restart: compose-down build-containers start
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

# Clean and start with mock LLM (LLM_PROVIDER=fake)
mock-llm-start: clean build-containers
	@echo "Starting services with mock LLM..."
	LLM_PROVIDER=fake docker-compose up -d
	@echo "Mock LLM start completed successfully"

# Terminate deployment, clean volumes, and start fresh
build-containers:
	@echo "Building containers manually..."
	docker build -t agentic-agents-platform-control-plane ./services/control-plane
	docker build -t agentic-agents-platform-agent-service . -f ./services/agent-service/Dockerfile
	docker build -t agentic-agents-platform-agent-worker-base-builder:latest . -f ./services/agent-worker/Dockerfile.base-builder
	docker build -t agentic-agents-platform-agent-worker-specialist:latest . -f ./services/agent-worker/Dockerfile.specialist
	docker build -t agentic-agents-platform-agent-worker-single-agent:latest . -f ./services/agent-worker/Dockerfile.single-agent
	docker build -t agentic-agents-platform-agent-worker-crewai:latest . -f ./services/agent-worker/Dockerfile.crewai
	docker build -t agentic-agents-platform-web ./apps/web
	@echo "All containers built successfully"

# Run UI e2e tests
test-ui:
	@echo "Running UI e2e tests..."
	cd apps/web && npm run test:e2e
	@echo "UI e2e tests completed"

# use this to test localy 1 service under development localy
# Start services with specified ones running locally
start-local: 
	@echo "Starting docker-compose services (excluding: $(SERVICES))..."
	@if [ -z "$(SERVICES)" ]; then \
		echo "Error: SERVICES parameter is required. Example: make start-local SERVICES=web"; \
		exit 1; \
	fi
	docker-compose up -d $$(docker-compose config --services | grep -vE "$(SERVICES)")
	@echo ""
	@echo "Docker-compose services started."
	@echo ""
	@echo "To run the following services locally, execute these commands in separate terminals:"
	@for service in $$(echo "$(SERVICES)" | tr ',' ' '); do \
		case $$service in \
			web) \
				cd apps/web && npm install && npm start; \
				;; \
			agent-service) \
				cd services/agent-service && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && python -m internal.chatkit.server; \
				;; \
			control-plane) \
				cd services/control-plane && go run .; \
				;; \
			*) \
				echo "  # Unknown service: $$service"; \
				;; \
		esac; \
	done
	@echo ""

# Stop local services (specified in SERVICES parameter)
stop-local:
	@echo "Stopping local services: $(SERVICES)..."
	@if [ -z "$(SERVICES)" ]; then \
		echo "Error: SERVICES parameter is required. Example: make stop-local SERVICES=web"; \
		exit 1; \
	fi
	@for service in $$(echo "$(SERVICES)" | tr ',' ' '); do \
		case $$service in \
			web) \
				echo "Stopping web service"; \
				lsof +D apps/web -t 2>/dev/null | xargs -r kill || true; \
				;; \
			agent-service) \
				echo "Stopping agent-service"; \
				lsof +D services/agent-service -t 2>/dev/null | xargs -r kill || true; \
				;; \
			control-plane) \
				echo "Stopping control-plane"; \
				lsof +D services/control-plane -t 2>/dev/null | xargs -r kill || true; \
				;; \
			*) \
				echo "  # Unknown service: $$service"; \
				;; \
		esac; \
	done
	@echo "Local services stopped."
