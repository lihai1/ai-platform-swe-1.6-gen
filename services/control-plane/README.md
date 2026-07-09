# Control Plane Service

Go control plane service for the agentic engineering platform. Manages users, organizations, projects, repositories, and agent container orchestration.

## Features

- **User Management**: Authentication and authorization with JWT tokens
- **Organization & Project Management**: Multi-tenant resource organization
- **Repository Management**: Git repository metadata and configuration
- **Container Orchestration**: Docker container creation for agent workspaces
- **Docker Bind Orchestrator**: Direct Docker socket/HTTP container lifecycle management
- **NATS Integration**: Message-based communication with agent service
- **Mock Docker Mode**: Simulated container creation for testing (set `MOCK_DOCKER=true`)

## Quick Start

### Prerequisites
- Go 1.23+
- Docker and Docker Compose
- golang-migrate CLI

### Development

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

- **chat.start**: Triggers container creation for a run session
- **chat.close**: Triggers container termination for a run session

### Message Flow

1. Agent Service publishes `chat.start` message with run_id and repository_id
2. Control Plane receives message and creates Docker container
3. If `MOCK_DOCKER=true`, the container creation is simulated and the flow continues immediately
4. Control Plane publishes `agent.chat.{run_id}.worker.ready` to signal readiness
5. Agent worker receives signal and begins workflow execution

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
- NATS subscription to `chat.start` and `chat.close` messages
- Container lifecycle via NATS agent start messages
- Orchestrator command reception and container creation
- Worker ready signal handling

### Linting

```bash
make lint
```

### Formatting

```bash
make fmt
```

## Database Schema

The control plane uses the following schema:
- `app.users` - User accounts
- `app.organizations` - Organization entities
- `app.projects` - Project entities
- `app.repositories` - Git repository metadata

## Implementation Status

✅ **Phase 1 Complete**: Foundation (Go + Infrastructure)
✅ **Phase 12 Complete**: Agent Container Creation Flow

See [PROGRESS.md](../../PROGRESS.md) for full implementation details.
