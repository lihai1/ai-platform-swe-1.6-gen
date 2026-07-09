.PHONY: dev-env dev-env-down test-integration help

# Default target
help:
	@echo "Available targets:"
	@echo "  make dev-env         - Start development environment"
	@echo "  make dev-env-down    - Stop development environment"
	@echo "  make test-integration - Run integration tests"
	@echo "  make help            - Show this help message"

# Start development environment
dev-env:
	docker-compose -f docker-compose-dev.yml up -d

# Stop development environment
dev-env-down:
	docker-compose -f docker-compose-dev.yml down

# Run integration tests
test-integration:
	pytest tests/integration/ -v
