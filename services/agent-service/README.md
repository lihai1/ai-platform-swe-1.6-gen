# Agent Service

Python FastAPI service for the agentic engineering platform. Handles chat interactions, NATS messaging, SSE streaming, and acts as the single entry point for all UI requests.

## Architecture

The agent-service is the **HTTP API and messaging layer** of the platform. It does **not** execute LangGraph workflows - that responsibility belongs to the agent-worker service.

**Responsibilities:**
- HTTP API for chat interactions
- Single entry point for all UI requests (proxy to control-plane)
- NATS message publishing (chat.start, run.start commands)
- NATS event subscription (worker state events)
- SSE streaming to the UI
- PostgreSQL thread/message store
- ChatKit protocol implementation
- Proxy endpoints for control-plane APIs (auth, projects, repositories)

**What it does NOT do:**
- LangGraph workflow execution (handled by agent-worker)
- Agent implementations (shared library in internal/agents/)
- Workspace operations (handled by agent-worker in containers)
- User/project/repository management (handled by control-plane, proxied via agent-service)

## Features

- **ChatKit Integration**: Custom ChatKit server with SSE streaming
- **AegisChatKitServer**: Async SSE streaming response for chat messages
- **NATS Bridge**: Subscribes to `agent.user.{uid}.events.{rid}.>` and yields ChatKit events
- **Event Streaming**: Real-time agent activity events via SSE
- **NATS Messaging**: Message-based communication with control plane and agent-worker
- **PostgreSQL Store**: Thread and message persistence

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
- `POST /api/chatkit/` - Chat endpoint with streaming
- `GET /api/chatkit/threads/{thread_id}` - Get thread history

### Control Plane Proxy Endpoints (Single Entry Point)
- `POST /api/auth/login` - Proxy to control-plane auth login
- `POST /api/auth/register` - Proxy to control-plane auth register
- `GET /api/auth/me` - Proxy to control-plane get current user
- `GET /api/projects` - Proxy to control-plane list projects
- `POST /api/projects` - Proxy to control-plane create project
- `GET /api/repositories` - Proxy to control-plane list repositories
- `POST /api/repositories` - Proxy to control-plane create repository
- `GET /api/ollama/models` - Proxy to control-plane Ollama models

**Note:** Agent run endpoints (POST /agent/runs, etc.) are now handled by the agent-worker service via NATS messaging. The agent-service only publishes NATS commands and streams events.

## NATS Integration

The agent service uses NATS JetStream with durable consumers for reliable message delivery:

### Streams
- **AGENT_CHAT**: Chat stream for worker output and user events (agent.user.*.chat.>)
- **AGENT_CONTROL**: Control stream for container orchestration (agent.control.>)
- **AGENT_EVENTS**: Event stream for agent state updates (agent.user.*.events.>)

### Subjects
- **agent.control.{run_id}.start**: Publishes container creation requests
- **agent.control.{run_id}.close**: Publishes container termination requests
- **agent.control.{run_id}.resume**: Publishes container resume requests
- **agent.user.{uid}.events.{rid}.state.{event_type}**: Subscribes to state events from worker
- **agent.user.{uid}.chat.{rid}.worker.events**: Subscribes to worker output events (final_answer, progress_update)
- **agent.user.{uid}.chat.{rid}.user.events**: Publishes user events (tool.allowed, tool.denied, user_input) to worker

### Message Flow

1. **Chat Request**: UI → Agent Service (`POST /api/chatkit/`)
2. **SSE Stream**: `AegisChatKitServer.respond()` yields `progress_update` and `thread.item.done` events
3. **Container Creation**: Agent Service → NATS (`agent.control.{run_id}.start`) → Control Plane
4. **Worker Auto-Start**: Container starts with environment variables, worker auto-starts workflow
5. **Workflow Execution**: Worker executes LangGraph workflow
6. **State Events**: Worker → NATS (`agent.user.{uid}.events.{rid}.state.{event_type}`) → Agent Service
7. **Worker Output**: Worker → NATS (`agent.user.{uid}.chat.{rid}.worker.events`) → Agent Service → UI

### First-Flow with mock-worker

For the E2E smoke test, the `mock-worker` container is used instead of a real agent worker:

1. Agent Service publishes `agent.control.{run_id}.start`
2. `mock-worker` receives the start signal and publishes `started`, `progress`, and `completed` events
3. Agent Service receives the events via global event stream and maps them to ChatKit protocol events
4. SSE stream returns the events to the UI

## Project Structure

```
agent-service/
├── app/                     # FastAPI application
├── internal/
│   ├── agent/              # Agent-related logic
│   ├── agents/             # Shared agent implementations
│   ├── chatkit/            # ChatKit protocol implementation
│   ├── handlers/           # HTTP request handlers
│   ├── messaging/          # NATS messaging layer
│   ├── skills/             # Skill definitions
│   └── tools/              # Tool implementations
├── migrations/             # Database migration files
├── tests/
│   ├── e2e/                # End-to-end tests
│   ├── fixtures/           # Test fixtures
│   ├── integration/        # Integration tests
│   └── security/           # Security tests
└── docs/
    ├── operations/         # Operational documentation
    └── threat-model/       # Security threat models
```

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

The system includes the following specialist agents (framework implemented, not yet tested end-to-end - considering CrewAI integration):

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

Run all tests:
```bash
uv run pytest
```

**Note:** E2E workflow tests have been removed from agent-service since workflow execution is now handled by agent-worker. Use agent-worker integration tests to test workflow execution.

## Implementation Status

✅ **Phase 2 Complete**: Angular UI + Python ChatKit
✅ **Phase 3 Complete**: LangGraph Workflow Skeleton (moved to agent-worker)
✅ **Phase 4 Complete**: Skills and Read-Only Agents
✅ **Phase 5 Complete**: Workspace Isolation
✅ **Phase 6 Complete**: Implementation Agents
✅ **Phase 7 Complete**: Testing, Review, Verification
✅ **Phase 8 Complete**: Human Approval
✅ **Phase 9 Complete**: Activity and Artifact UX
✅ **Phase 10 Complete**: NATS Worker Separation
✅ **Phase 11 Complete**: Hardening and Evaluation
✅ **Phase 12 Complete**: Agent Container Creation Flow
✅ **Phase 13 Complete**: Architecture Refactoring - Service Separation

See [PROGRESS.md](../../PROGRESS.md) for full implementation details.

## Current State & Goal for Personal Use

**Current state:** `make clean-start` starts the whole stack. This service proxies UI requests to the control-plane, handles ChatKit threads, publishes `agent.control.{run_id}.start`/`close` commands, and streams worker state events to the UI. The worker now clones the selected repository into `/workspace` before the workflow starts. A custom CrewAI wrapper worker type discovers available agent projects and surfaces them in the chat session, so the user can pick which multi-agent project to run. It is not production-ready for real repositories.

**First goal:** Enable secure remote control of isolated agent workflows through a single HTTP entry point, using a fully open-source stack and free local LLMs via Ollama.

**Personal-use goal:** Be the single HTTP entry point for a home deployment, so a single user can remotely chat, start a workflow, see progress, and approve or reject actions.

## Next Milestone

1. **Approval workflow:** Implement a `POST /api/chatkit/approvals/{run_id}/{decision}` endpoint and forward user decisions to `agent.user.{uid}.chat.{rid}.user.events`.
2. **Budget tracking:** Update `AgentRun` token/cost counters and expose them via the run context.
3. **End-to-end tests:** Add a test that sends a chat to `/api/chatkit/`, asserts the container is created, and verifies completed events in the event stream.

See main [README.md](../../README.md) for future goals and milestones.

## Current Limitations

- **Memory Checkpointer**: Using in-memory checkpointer instead of PostgreSQL (temporary workaround for LangGraph API issues)
- **Mock Responses**: ChatKit returns predefined responses in mock mode (no actual LLM calls)
- **Mock Docker Mode**: Workspace containers are simulated when MOCK_DOCKER=true
- **Approval Workflow**: Approval UI/dialogs exist but the workflow interrupt is not wired.
- **Budget/Cost Tracking**: `max_tokens`/`max_cost` fields are not enforced.
- **Real E2E Tests**: Only smoke testing exists; the full chat-to-run flow is not yet automated.

These limitations are acceptable for testing the message flow and can be addressed in future iterations.
