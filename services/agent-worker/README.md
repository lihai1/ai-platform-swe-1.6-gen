# Agent Worker

Python worker process for isolated agent workflow execution. Runs in Docker-in-Docker containers with git and Docker CLI access.

## Purpose

The agent worker is responsible for:
- Executing LangGraph workflows in isolated containers
- Cloning git repositories to `/workspace`
- Subscribing to NATS commands (run.start)
- Publishing state events back to NATS
- Running specialist agents with workspace access

## Quick Start

### Build Docker Image

```bash
docker build -f Dockerfile.worker -t agentic-agent-worker:latest .
```

### Run Worker Manually

```bash
uv run python -m app.worker --run-id <run_id> --nats-url nats://localhost:4222
```

### Run in Docker

```bash
docker run -e RUN_ID=<run_id> \
           -e REPOSITORY_URL=<repo_url> \
           -e BRANCH=<branch> \
           -e NATS_URL=nats://localhost:4222 \
           agentic-agent-worker:latest
```

### Development Environment

Start the development environment (NATS only):
```bash
make dev-env
```

Stop the development environment:
```bash
make dev-env-down
```

Run integration tests:
```bash
make test-integration
```

For the first-flow E2E test, the `mock-worker` container in the root `docker-compose.yml` simulates a worker by publishing `started`, `progress`, and `completed` events.

## Environment Variables

- `RUN_ID`: Run ID for the worker
- `REPOSITORY_URL`: Git repository URL to clone
- `BRANCH`: Git branch to checkout (default: main)
- `GIT_USERNAME`: Git username for authentication (optional)
- `GIT_TOKEN`: Git token for authentication (optional)
- `NATS_URL`: NATS server URL (default: nats://localhost:4222)
- `MOCK_MODE`: Enable mock mode for testing (default: false)

## Container Startup

The container runs `scripts/container-start.sh` which:
1. Clones the repository to `/workspace` (or creates mock structure)
2. Configures git credentials if provided
3. Starts the worker process with `python -m app.worker --run-id $RUN_ID`

## NATS Integration

The worker subscribes to:
- `agent.chat.{run_id}.user.events` - Receives run.start commands

The worker publishes to:
- `agent.events.{run_id}.{event_type}` - State events
- `agent.chat.{run_id}.user.events` - Final answers and progress updates

## Dependencies

See `pyproject.toml` for full dependencies. Key dependencies:
- `langgraph` - Workflow execution
- `langchain-*` - LLM integration
- `nats-py` - NATS messaging
- `docker` - Docker API access

## Architecture

```
NATS Command → Worker → LangGraph Workflow → NATS Events
                      ↓
                /workspace
                (git repo)
```

## Separation from Agent Service

- **Agent Service**: HTTP API layer (`services/agent-service`)
  - Exposes REST endpoints
  - Manages database records
  - Publishes commands to NATS
  
- **Agent Worker**: Workflow execution layer (`services/agent-worker`)
  - Runs in isolated containers
  - Executes LangGraph workflows
  - Subscribes to NATS commands

## Testing

### Integration Tests

Start development environment (NATS only):
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

Integration tests require NATS to be running locally. The tests verify:
- NATS subscription to `agent.chat.{run_id}.user.events`
- Command handling for `run.start` commands
- Workflow execution and state event publishing
- Full workflow flow from command to events
