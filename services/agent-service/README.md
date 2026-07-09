# Agent Service

Python FastAPI service for the agentic engineering platform. Handles chat interactions, agent workflows, and task execution.

## Features

- **ChatKit Integration**: Custom ChatKit server with SSE streaming
- **AegisChatKitServer**: Async SSE streaming response for chat messages
- **NATS Bridge**: Subscribes to `agent.events.{run_id}.>` and yields ChatKit events
- **Mock Worker**: `mock_worker.py` for first-flow E2E testing without real LLMs
- **LangGraph Workflows**: State machine-based agent execution
- **Specialist Agents**: Skills-based agent system with structured outputs
- **Workspace Isolation**: Docker-based isolated execution environments
- **NATS Messaging**: Message-based communication with control plane
- **Event Streaming**: Real-time agent activity events via SSE
- **Human Approval**: LangGraph interrupts for sensitive operations
- **Artifact Management**: Code diffs, test reports, and verification results

## Quick Start

### Prerequisites
- Python 3.12+
- uv (Python package manager)
- Docker and Docker Compose
- PostgreSQL

### Development

1. Install dependencies:
```bash
uv sync
```

2. Run migrations:
```bash
uv run alembic upgrade head
```

3. Run the service:
```bash
uv run uvicorn app.main:app --reload
```

### Docker Compose

Start all services including NATS:
```bash
docker-compose up -d
```

Start agent service only:
```bash
docker-compose up -d agent-service
```

Start with the mock worker for first-flow E2E testing:
```bash
docker-compose up -d agent-service mock-worker
```

### Worker Process

Run the agent worker for a specific run:
```bash
uv run python -m app.worker --run-id <run_id> --nats-url nats://localhost:4222
```

Run the mock worker for first-flow E2E testing:
```bash
uv run python mock_worker.py
```

## API Endpoints

### Health & Readiness
- `GET /healthz` - Health check
- `GET /readyz` - Readiness check

### ChatKit
- `POST /chatkit/` - Chat endpoint with streaming
- `GET /chatkit/threads/{thread_id}` - Get thread history

### Agent Runs
- `POST /agent/v1/runs` - Create a new agent run
- `GET /agent/v1/runs/{run_id}` - Get run details
- `GET /agent/v1/runs/{run_id}/events` - SSE event stream
- `POST /agent/v1/runs/{run_id}/cancel` - Cancel a run

### Approvals
- `POST /agent/v1/runs/{run_id}/approvals/{approval_id}/approve` - Approve an action
- `POST /agent/v1/runs/{run_id}/approvals/{approval_id}/reject` - Reject an action

## NATS Integration

The agent service uses NATS JetStream for reliable message delivery:

### Streams
- **AGENT_COMMANDS**: Command stream for agent worker (agent.chat.>)
- **AGENT_EVENTS**: Event stream for agent state updates (agent.events.>)

### Subjects
- **chat.start**: Publishes container creation requests
- **chat.close**: Publishes container termination requests
- **agent.chat.{run_id}.user.events**: Publishes run.start commands to worker
- **agent.events.{run_id}.>**: Subscribes to all state events for a run
- **agent.events.{run_id}.{event_type}**: Publishes state events

### Message Flow

1. **Chat Request**: UI → Agent Service (`POST /api/chatkit/`)
2. **SSE Stream**: `AegisChatKitServer.respond()` yields `progress_update` and `thread.item.done` events
3. **Container Creation**: Agent Service → NATS (`chat.start`) → Control Plane
4. **Agent Start**: Agent Service → NATS (`agent.chat.{run_id}.user.events` with `run.start`) → Worker
5. **Workflow Execution**: Worker processes `run.start` command and executes LangGraph
6. **State Events**: Worker → NATS (`agent.events.{run_id}.{event_type}`) → Agent Service

### First-Flow with mock-worker

For the E2E smoke test, the `mock-worker` container is used instead of a real agent worker:

1. Agent Service publishes `chat.start`
2. `mock-worker` receives the chat start and publishes `started`, `progress`, and `completed` events
3. Agent Service `NatsBridge` receives the events and maps them to ChatKit protocol events
4. SSE stream returns the events to the UI

## Configuration

Environment variables:
- `DATABASE_URL`: PostgreSQL connection string (postgresql+asyncpg://...)
- `NATS_URL`: NATS server URL (default: nats://localhost:4222)
- `DISABLE_AUTH`: Disable authentication for testing (default: false)
- `MOCK_MODE`: Enable mock responses for testing (default: false)
- `LANGCHAIN_API_KEY`: LangSmith API key for tracing
- `LANGCHAIN_PROJECT`: LangSmith project name

## Database Schema

The agent service uses the following schema:
- `agent.chatkit_threads` - ChatKit thread persistence
- `agent.chatkit_items` - ChatKit message items
- `agent_runs` - Agent run metadata
- `agent_steps` - Individual agent steps
- `agent_events` - Agent state events
- `agent_artifacts` - Generated artifacts (diffs, reports)
- `agent_approvals` - Human approval records
- `agent.skill_snapshots` - Skill version tracking
- `agent.workspace_leases` - Workspace container tracking

## Agent Workflow Phases

The LangGraph workflow implements the following phases:

1. **CREATED**: Initial state
2. **PREPARING_WORKSPACE**: Setting up isolated container
3. **SCOUTING**: Repository analysis by repo-scout agent
4. **PLANNING**: Implementation planning by solution-planner agent
5. **DESIGNING**: Architecture design (if applicable)
6. **IMPLEMENTING**: Code implementation by specialist agents
7. **TESTING**: Test execution by test engineer agents
8. **REVIEWING**: Code review by code reviewer agent
9. **VERIFYING**: Completion verification by completion verifier agent
10. **REPAIRING**: Fixing issues (up to max_repair_count)
11. **WAITING_APPROVAL**: Paused for human approval
12. **COMPLETED**: Successful completion
13. **FAILED**: Failed with no repair attempts remaining
14. **CANCELLED**: User-initiated cancellation
15. **BUDGET_EXCEEDED**: Cost/token limits exceeded

## Specialist Agents

> **Note:** The specialist agents and the LangGraph workflow are **executed by
> `services/agent-worker`**, not by this service. The agent-service is the
> API/streaming gateway: it exposes the ChatKit endpoint, bridges NATS events to
> the browser over SSE, and hosts the workflow REST API. Shared infrastructure
> (`config`, `db`, `models`, `messaging`) is provided by the `agent_core`
> package in `shared/agent-core`.

The platform includes the following specialist agents (implemented in the worker):

### Planning Agents
- **skills-lead**: Selects appropriate specialists based on task
- **repo-scout**: Analyzes repository structure and metadata
- **solution-planner**: Creates implementation plans

### Implementation Agents
- **go-developer**: Implements Go code changes
- **angular-developer**: Implements Angular component changes
- **angular-ui-developer**: Implements Angular UI changes
- **devops-developer**: Implements DevOps configuration changes

### Validation Agents
- **backend-test-engineer**: Tests backend code
- **angular-test-engineer**: Tests Angular code
- **code-reviewer**: Reviews code changes
- **completion-verifier**: Verifies acceptance criteria

## Testing

Run unit tests with pytest:
```bash
uv run pytest
```

Run specific test suites:
```bash
uv run pytest tests/e2e/
uv run pytest tests/security/
```

### Integration Tests

Start development environment (PostgreSQL + NATS):
```bash
uv run dev-env
```

Stop development environment:
```bash
uv run dev-env-down
```

Run integration tests:
```bash
uv run test-integration
```

Integration tests require PostgreSQL and NATS to be running locally. The tests verify:
- NATS publishing to `chat.start`, `chat.close`, and `run.start` subjects
- Event handling from NATS state events
- Full chat lifecycle via HTTP + NATS messaging

## Implementation Status

✅ **Phase 2 Complete**: Angular UI + Python ChatKit
✅ **Phase 3 Complete**: LangGraph Workflow Skeleton
✅ **Phase 4 Complete**: Skills and Read-Only Agents
✅ **Phase 5 Complete**: Workspace Isolation
✅ **Phase 6 Complete**: Implementation Agents
✅ **Phase 7 Complete**: Testing, Review, Verification
✅ **Phase 8 Complete**: Human Approval
✅ **Phase 9 Complete**: Activity and Artifact UX
✅ **Phase 10 Complete**: NATS Worker Separation
✅ **Phase 11 Complete**: Hardening and Evaluation
✅ **Phase 12 Complete**: Agent Container Creation Flow

See [PROGRESS.md](../../PROGRESS.md) for full implementation details.

## Current Limitations

- **Memory Checkpointer**: Using in-memory checkpointer instead of PostgreSQL (temporary workaround for LangGraph API issues)
- **Mock Responses**: ChatKit returns predefined responses in mock mode (no actual LLM calls)
- **Mock Docker Mode**: Workspace containers are simulated when MOCK_DOCKER=true

These limitations are acceptable for testing the message flow and can be addressed in future iterations.
