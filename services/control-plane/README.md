# Control Plane Service

Go control plane service for the agentic engineering platform. Manages users, organizations, projects, repositories, and agent container orchestration. Accessed internally via agent-service proxy for UI requests.

## Features

- **User Management**: Authentication and authorization with JWT tokens
- **Organization & Project Management**: Multi-tenant resource organization
- **Repository Management**: Git repository metadata and configuration
- **Container Orchestration**: Docker container creation for agent workspaces
- **Docker Bind Orchestrator**: Direct Docker socket/HTTP container lifecycle management
- **NATS Integration**: Message-based communication with agent service using NATS JetStream with durable consumers
- **Mock Docker Mode**: Simulated container creation for testing (set `MOCK_DOCKER=true`)

## Quick Start

### Prerequisites
- Go 1.26+
- Docker and Docker Compose
- golang-migrate CLI

### Development

#### Local Development (with docker-compose services)

**Use this for testing changed code locally** - run the control-plane locally while other services run in docker-compose:

```bash
# From the project root, this starts control-plane locally and other services in docker-compose
make start-local SERVICES=control-plane
```

The control-plane will automatically start in the background with hot-reload enabled, making it ideal for testing code changes without rebuilding containers.

#### Standalone Development

1. Start PostgreSQL:
```bash
docker-compose up -d postgres
```

2. Run migrations:
```bash
make migrate-up
```

3. Run the service:
```bash
make run
```

Or use the combined command:
```bash
make dev
```

### Docker Compose

Start all services including NATS:
```bash
docker-compose up -d
```

Start with control plane profile:
```bash
docker-compose --profile full up -d control-plane
```

## API Endpoints

### Health & Readiness
- `GET /healthz` - Health check
- `GET /readyz` - Readiness check

### Authentication
- `POST /api/v1/auth/login` - User login
- `POST /api/v1/auth/register` - User registration

### Projects
- `GET /api/v1/projects` - List projects
- `POST /api/v1/projects` - Create project

### Repositories
- `GET /api/v1/repositories` - List repositories
- `POST /api/v1/repositories` - Create repository
- `GET /api/v1/repositories/{id}` - Get repository details

## NATS Integration

The control plane subscribes to NATS subjects for container orchestration:

- **agent.control.{run_id}.start**: Triggers container creation for a run session
- **agent.control.{run_id}.close**: Triggers container termination for a run session

### Message Flow

1. Agent Service publishes `agent.control.{run_id}.start` message with run_id and repository_id
2. Control Plane receives message and creates Docker container
3. If `MOCK_DOCKER=true`, the container creation is simulated and the flow continues immediately
4. Container starts with environment variables, worker auto-starts workflow

### Mock Mode

Set `MOCK_DOCKER=true` to bypass real Docker container creation. This is used for the first-flow E2E test with the `mock-worker` container, where the worker itself simulates the agent execution.

## Configuration

Environment variables:
- `DATABASE_URL`: PostgreSQL connection string
- `JWT_SECRET`: Secret for JWT token signing
- `PORT`: HTTP server port (default: 8080)
- `NATS_URL`: NATS server URL (default: nats://localhost:4222)
- `MOCK_DOCKER`: Enable mock Docker mode (default: false)
- `DOCKER_HOST`: Docker daemon URL (default: http://host.docker.internal:2375)
- `DISABLE_AUTH`: Disable authentication for testing (default: false)

## Testing

Run unit tests with ginkgo:
```bash
make test
```

### Integration Tests

Start development environment (PostgreSQL + NATS):
```bash
make dev-env
```

Stop development environment:
```bash
make dev-env-down
```

Run integration tests:
```bash
make test-integration
```

Integration tests require PostgreSQL and NATS to be running locally. The tests verify:
- NATS subscription to `agent.control.>` messages
- Container lifecycle via NATS agent start/close messages
- Orchestrator command reception and container creation

### Linting

```bash
make lint
```

### Formatting

```bash
make fmt
```

## Project Structure

```
control-plane/
├── cmd/
│   └── server/              # Application entry point
├── internal/
│   ├── config/              # Configuration management
│   ├── db/                  # Database connection and setup
│   ├── handlers/            # HTTP request handlers
│   ├── middleware/          # HTTP middleware (auth, logging, etc.)
│   ├── models/              # Data models and DTOs
│   ├── orchestrator/        # Docker container orchestration
│   ├── repository/          # Repository pattern implementations
│   └── service/             # Business logic layer
├── migrations/              # Database migration files
└── tests/
    └── integration/         # Integration tests
```

## Database Schema

The control plane uses the following schema:
- `app.users` - User accounts
- `app.organizations` - Organization entities
- `app.projects` - Project entities
- `app.repositories` - Git repository metadata

## Current State & Goal for Personal Use

**Current state:** The control-plane provides CRUD APIs for users, organizations, projects, and repositories, and it creates/terminates agent containers on NATS `agent.control.{run_id}.start`/`close` messages. The worker now clones the selected repository into `/workspace` before the workflow starts. A custom CrewAI wrapper worker type discovers available agent projects and surfaces them in the chat session, so the user can pick which multi-agent project to run. It is **demo-ready** but not production-ready for real repositories.

**First goal:** Orchestrate agentic AI workflows in controlled isolated environments with secured remote controls, full open-source usage, and free local LLMs.

**Personal-use goal:** Provide the small-scale resource management and container orchestration layer for a single-user home deployment, so a user can register, create projects, attach repositories, and run isolated agent experiment workflows without risks.

## Next Milestone

1. **Approval workflow:** Add NATS subscription or API endpoint to receive approval decisions and propagate them to the worker.
2. **Budget tracking:** Persist and expose `max_tokens`/`max_cost` for runs and update `cost_incurred`/`tokens_used` from worker events.
3. **End-to-end tests:** Extend integration tests to verify the full `start` → container creation → `completed` event flow.

See main [README.md](../../README.md) for future goals and milestones.

## Implementation Status

✅ **Phase 1 Complete**: Foundation (Go + Infrastructure)
✅ **Phase 12 Complete**: Agent Container Creation Flow

See [PROGRESS.md](../../PROGRESS.md) for full implementation details.
