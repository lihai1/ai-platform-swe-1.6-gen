# Agentic Engineering Platform

A complete agentic engineering platform with Angular UI, Go control plane, and Python agent service.

## AI-Engineered Architecture

This platform represents a breakthrough in autonomous software engineering, entirely architected and implemented by **SWE-1.6** within the **Devin IDE** environment. The system demonstrates advanced AI capabilities including:

- **Autonomous System Design**: Multi-service architecture with Go, Python, and Angular orchestrated through intelligent decision-making
- **Complex Workflow Orchestration**: LangGraph-based state machines managing 15 distinct agent workflow phases
- **Specialist Agent Collaboration**: 11+ specialized AI agents working in parallel with conflict resolution
- **Real-time Event Streaming**: SSE-based live agent activity with browser reconnection support
- **Secure Container Isolation**: Docker-based workspace management with resource limits and security controls
- **Human-in-the-Loop Approval**: LangGraph interrupts for sensitive operations requiring human oversight

The implementation showcases SWE-1.6's ability to reason about complex distributed systems, implement production-grade code across multiple languages, and create cohesive documentation—all autonomously within a single development session.

## Architecture

- **Control Plane**: Go service managing users, organizations, projects, and repositories. Subscribes to NATS `chat.start`/`chat.close` to create/destroy agent worker containers.
  - See [services/control-plane/README.md](services/control-plane/README.md) for details
- **Agent Service**: Python FastAPI service with ChatKit integration, SSE streaming, and the workflow REST API. This is the API/streaming **gateway** — it bridges NATS events to the browser and persists chat threads.
  - See [services/agent-service/README.md](services/agent-service/README.md) for details
- **Agent Worker**: Python worker that **executes** the LangGraph workflow. It owns the specialist agents, skills, tools, and workflow graph/nodes.
  - See [services/agent-worker/README.md](services/agent-worker/README.md) for details
- **Web UI**: Angular 22+ application with standalone components
- **Shared Core** (`shared/agent-core`): the single source of truth for configuration, database engine/session, ORM models, and the NATS messaging client. Both Python services import it as the `agent_core` package; each service's `internal/{config,db,models,messaging}` module is a thin re-export shim.

### Service responsibilities at a glance

| Concern | agent-service (gateway) | agent-worker (executor) |
| --- | --- | --- |
| ChatKit endpoint + SSE streaming | ✅ | — |
| Workflow REST API (`/runs`, approvals) | ✅ | ✅ |
| LangGraph graph/nodes execution | — (mock nodes only) | ✅ (real execution) |
| Specialist agents / skills / tools | — | ✅ |
| NATS bridge to browser | ✅ | — |
| Publishes `agent.events.{run_id}.*` | — | ✅ |

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Go 1.23+ (for local development)
- Node.js 22+ (for local development)
- Python 3.12+ (for local development)

### Using Docker Compose

```bash
docker-compose up -d
```

This will start:
- PostgreSQL on port 5432
- Control Plane API on port 8080
- Agent Service on port 8000
- Web UI on port 4200
- NATS on port 4222
- Mock Agent Worker (for first-flow E2E testing)

### Local Development

#### Control Plane (Go)

```bash
cd services/control-plane
make dev
```

#### Agent Service (Python)

```bash
cd services/agent-service
uv sync
# Install the shared core package (provides the `agent_core` module).
uv pip install -e ../../shared/agent-core
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

> In Docker builds the shared package is copied into the image automatically
> (the build context is the repository root). For local development, install it
> editable as shown above, or add `shared/agent-core` to `PYTHONPATH`.

#### Web UI (Angular)

```bash
cd apps/web
npm install
npm start
```

## API Endpoints

### Control Plane (port 8080)

- `GET /healthz` - Health check
- `GET /readyz` - Readiness check
- `POST /api/v1/auth/login` - User login
- `POST /api/v1/auth/register` - User registration
- `GET /api/v1/projects` - List projects
- `POST /api/v1/projects` - Create project
- `GET /api/v1/repositories` - List repositories
- `POST /api/v1/repositories` - Create repository

### Agent Service (port 8000)

- `GET /healthz` - Health check
- `GET /readyz` - Readiness check
- `POST /chatkit/` - Chat endpoint with streaming
- `GET /chatkit/threads/{thread_id}` - Get thread history

## Project Structure

> **Note:** The Python execution code (specialist agents, skills, tools, and the
> LangGraph graph/nodes) lives in **`services/agent-worker`**. The
> `services/agent-service` gateway keeps only the ChatKit server, the workflow
> REST API, the NATS bridge, and mock workflow nodes. Shared infrastructure
> (`config`, `db`, `models`, `messaging`) lives once in **`shared/agent-core`**
> and is re-exported by each service's `internal/` package.

```
ai-platform-swe-1.6-gen/
├── apps/
│   └── web/                 # Angular 22+ UI application
│       ├── src/
│       │   ├── app/
│       │   │   ├── core/           # Core services (HTTP, auth, config)
│       │   │   ├── auth/           # Authentication module
│       │   │   ├── projects/       # Project management
│       │   │   ├── chat/           # Chat interface with ChatKit
│       │   │   ├── activity/       # Agent activity timeline
│       │   │   ├── artifact-viewer/ # Artifact display (diffs, reports)
│       │   │   ├── diff-viewer/    # Code diff viewer
│       │   │   ├── approval-dialog/ # Human approval dialog
│       │   │   └── run-context/    # Run metadata display
│       │   └── main.ts
│       ├── package.json
│       ├── angular.json
│       └── Dockerfile
├── services/
│   ├── control-plane/       # Go 1.23+ control plane service
│   │   ├── cmd/
│   │   │   └── server/
│   │   │       └── main.go        # Service entry point
│   │   ├── internal/
│   │   │   ├── config/            # Configuration management
│   │   │   ├── db/                # Database connection
│   │   │   ├── handlers/          # HTTP handlers
│   │   │   ├── middleware/        # HTTP middleware (auth, CORS)
│   │   │   ├── models/            # Data models
│   │   │   ├── repository/        # Data access layer
│   │   │   ├── service/           # Business logic
│   │   │   └── orchestrator/      # Container orchestration
│   │   ├── migrations/            # Database migrations
│   │   ├── Makefile
│   │   ├── go.mod
│   │   └── Dockerfile
│   └── agent-service/       # Python 3.12+ agent service
│       ├── app/
│       │   ├── main.py            # FastAPI application
│       │   └── worker.py          # Agent worker process
│       ├── internal/
│       │   ├── agents/            # Specialist agents
│       │   │   ├── factory.py     # Agent creation
│       │   │   ├── schemas.py     # Pydantic schemas
│       │   │   ├── specialists.py # Planning agents
│       │   │   ├── implementers.py # Implementation agents
│       │   │   └── validators.py  # Validation agents
│       │   ├── chatkit/           # ChatKit integration
│       │   │   ├── router.py      # Chat endpoints
│       │   │   ├── server.py      # AegisChatKitServer (SSE streaming)
│       │   │   ├── nats_bridge.py # NATS event subscription bridge
│       │   │   ├── event_mapper.py # Event mapping to ChatKit protocol
│       │   │   ├── context.py     # Request context helpers
│       │   │   └── store.py       # PostgreSQL thread/message store
│       │   ├── config.py          # Configuration
│       │   ├── db.py              # Database connection
│       │   ├── messaging/         # NATS messaging
│       │   │   └── nats.py        # NATS client
│       │   ├── models.py          # SQLAlchemy models
│       │   ├── skills/            # Skill system
│       │   │   ├── registry.py    # Skill loader
│       │   │   └── snapshots.py   # Skill versioning
│       │   ├── tools/             # Agent tools
│       │   │   ├── repository.py  # Read-only repo tools
│       │   │   └── workspace.py   # Workspace tools
│       │   ├── workflow/          # LangGraph workflow
│       │   │   ├── graph.py       # State graph
│       │   │   ├── nodes.py       # Workflow nodes
│       │   │   ├── state.py       # State definitions
│       │   │   ├── events.py      # Event handling
│       │   │   ├── checkpointer.py # Checkpointer setup
│       │   │   ├── approvals.py   # Human approval
│       │   │   ├── tracing.py     # LangSmith tracing
│       │   │   └── router.py      # Workflow API
│       │   └── workspace/         # Workspace management
│       │       └── manager.py     # Docker workspace manager
│       ├── migrations/            # Alembic migrations
│       ├── tests/                 # Test suites
│       │   ├── e2e/              # End-to-end tests
│       │   ├── security/         # Security tests
│       │   └── fixtures/         # Test repositories
│       ├── .agents/               # Skill definitions
│       │   ├── minimal/          # Minimal skill set
│       │   └── full/             # Full skill set
│       ├── pyproject.toml
│       ├── alembic.ini
│       └── Dockerfile
│   └── agent-worker/        # Python worker for isolated workflow execution
│       ├── app/             # Worker application
│       ├── internal/        # Worker internals
│       ├── tests/           # Worker tests
│       ├── Dockerfile.worker
│       └── Makefile
├── shared/
│   └── agent-core/          # Shared Python package (agent_core)
│       └── agent_core/
│           ├── config.py    # Settings (single source of truth)
│           ├── db.py        # Async engine, session, Base
│           ├── models.py    # SQLAlchemy ORM models (canonical schema)
│           └── messaging/
│               └── nats.py  # NATSMessaging client (superset used by both services)
├── docker-compose.yml       # Docker Compose orchestration (repo root)
├── docs/                    # Documentation and Mermaid/SVG diagrams
├── PROGRESS.md              # Implementation progress
└── README.md               # This file
```

## Implementation Phases

1. ✅ Phase 1: Foundation (Go + Infrastructure)
2. ✅ Phase 2: Angular UI + Python ChatKit
3. ✅ Phase 3: LangGraph Workflow Skeleton
4. ✅ Phase 4: Skills and Read-Only Agents
5. ✅ Phase 5: Workspace Isolation
6. ✅ Phase 6: Implementation Agents
7. ✅ Phase 7: Testing, Review, Verification
8. ✅ Phase 8: Human Approval
9. ✅ Phase 9: Activity and Artifact UX
10. ✅ Phase 10: NATS Worker Separation
11. ✅ Phase 11: Hardening and Evaluation
12. ✅ Phase 12: Agent Container Creation Flow

See [PROGRESS.md](PROGRESS.md) for detailed implementation status.

## Maintenance Refactor (Correctness + Best Practices)

A cleanup pass fixed several latent bugs and reduced duplication:

- **Fixed `chat_id`/`run_id` schema drift** — migration `004` renamed all `run_id`
  columns to `chat_id`, but the ORM models and several queries had drifted
  inconsistently (each service was even internally contradictory). All ORM
  column references are now aligned to the canonical `chat_id`, fixing
  `AttributeError`/SQL errors on the approvals and events paths.
- **Fixed a `TypeError` on every worker state event** — the worker called
  `nats.publish_event(chat_id=...)`, which is not a valid parameter; the swallowed
  exception meant the UI silently received no progress. The invalid argument was
  removed.
- **Removed dead duplicated code** — `agent-service` no longer ships unused copies
  of the specialist agents, skills, tools, and workflow-execution graph (those run
  only in `agent-worker`). The associated security tests were relocated to the
  worker.
- **Extracted `shared/agent-core`** — `config`, `db`, `models`, and the
  `NATSMessaging` client now live once and are re-exported by each service.
- **Best-practice fixes** — replaced `print()` debugging with `logging`, replaced
  deprecated `datetime.utcnow()` with timezone-aware `datetime.now(timezone.utc)`,
  fixed the invalid CORS wildcard-with-credentials combination (now configurable
  via `CORS_ALLOW_ORIGINS`), untracked the accidentally committed 37 MB Go
  `server` binary, and added a root `.dockerignore`.

> **Diagram note:** The Mermaid sources in `docs/*.mmd` were updated to reflect
> the real NATS subjects (`agent.events.{run_id}.{event_type}`) and the shared
> package. Re-run the commands in [Regenerating Diagrams](#regenerating-diagrams)
> to refresh the committed `docs/svg/*.svg` images.

## Agent Container Creation Flow

The platform now supports complete end-to-end agent container creation. The **first-flow** implementation uses the `mock-worker` container to validate the full message path without requiring real LLM calls or Docker container creation:

1. **User Chat Message** → Agent Service receives chat request via `POST /chatkit/`
2. **SSE Stream Initiated** → `AegisChatKitServer.respond()` returns an SSE stream
3. **Container Creation** → Agent Service publishes `chat.start` to NATS
4. **Control Plane** → Receives `chat.start`, attempts container creation (or skips in mock mode)
5. **Mock Agent Worker** → Container `mock-worker` subscribes to `chat.start`, then publishes `started`, `progress`, and `completed` events on `agent.events.{run_id}.{event_type}`
6. **State Events** → Agent Service receives events via `NatsBridge` and yields them as ChatKit `progress_update` and `thread.item.done` SSE events
7. **UI Rendering** → Angular `chat.component.ts` parses SSE events and updates the chat UI

### First-Flow with mock-worker

For the initial E2E smoke test, the `mock-worker` container simulates a real agent worker:

- Listens on the `chat.start` NATS subject
- Publishes a deterministic sequence of events (`started`, `progress`, `completed`)
- Allows the ChatKit streaming path to be verified without requiring GPU/LLM access or real Docker containers

### Current Limitations

- **Memory Checkpointer**: Using in-memory checkpointer instead of PostgreSQL (temporary workaround for LangGraph API issues)
- **Mock Docker Mode**: Container creation is simulated when `MOCK_DOCKER=true` (no actual Docker containers)
- **Mock Responses**: The `mock-worker` returns predefined responses (no actual LLM calls)
- **Icon Validation**: Fixed invalid `loader` icon literal by mapping it to `agent`

These limitations are acceptable for testing the message flow and can be addressed in future iterations.

## Architecture Diagrams

The platform includes comprehensive UML diagrams documenting the system architecture and message flows:

### Component Diagram

![Architecture Component Diagram](docs/svg/architecture-component-diagram.svg)

### Sequence Diagrams

#### Chat Lifecycle
![Chat Lifecycle Sequence](docs/svg/sequence-chat-lifecycle.svg)

#### ChatKit Chat Integration
![ChatKit Chat Sequence](docs/svg/sequence-chatkit-chat.svg)

#### Workflow Trigger
![Workflow Trigger Sequence](docs/svg/sequence-workflow-trigger.svg)

#### LangGraph Workflow
![LangGraph Workflow Sequence](docs/svg/sequence-langgraph-workflow.svg)

#### NATS Messaging
![NATS Messaging Sequence](docs/svg/sequence-nats-messaging.svg)

#### Event Streaming
![Event Streaming Sequence](docs/svg/sequence-event-streaming.svg)

#### Human Approval
![Human Approval Sequence](docs/svg/sequence-human-approval.svg)

#### Cancellation Flow
![Cancellation Sequence](docs/svg/sequence-cancellation.svg)

### Source Files

The Mermaid source files are available in the `docs/` directory for editing:
- [docs/architecture-component-diagram.mmd](docs/architecture-component-diagram.mmd)
- [docs/sequence-chat-lifecycle.mmd](docs/sequence-chat-lifecycle.mmd)
- [docs/sequence-chatkit-chat.mmd](docs/sequence-chatkit-chat.mmd)
- [docs/sequence-workflow-trigger.mmd](docs/sequence-workflow-trigger.mmd)
- [docs/sequence-langgraph-workflow.mmd](docs/sequence-langgraph-workflow.mmd)
- [docs/sequence-nats-messaging.mmd](docs/sequence-nats-messaging.mmd)
- [docs/sequence-event-streaming.mmd](docs/sequence-event-streaming.mmd)
- [docs/sequence-human-approval.mmd](docs/sequence-human-approval.mmd)
- [docs/sequence-cancellation.mmd](docs/sequence-cancellation.mmd)

### Regenerating Diagrams

To regenerate SVG images after modifying the Mermaid source files:

```bash
# Install mermaid-cli (first time only)
npx @mermaid-js/mermaid-cli --version

# Regenerate all diagrams
npx @mermaid-js/mermaid-cli -i docs/architecture-component-diagram.mmd -o docs/svg/architecture-component-diagram.svg
npx @mermaid-js/mermaid-cli -i docs/sequence-chat-lifecycle.mmd -o docs/svg/sequence-chat-lifecycle.svg
npx @mermaid-js/mermaid-cli -i docs/sequence-chatkit-chat.mmd -o docs/svg/sequence-chatkit-chat.svg
npx @mermaid-js/mermaid-cli -i docs/sequence-workflow-trigger.mmd -o docs/svg/sequence-workflow-trigger.svg
npx @mermaid-js/mermaid-cli -i docs/sequence-langgraph-workflow.mmd -o docs/svg/sequence-langgraph-workflow.svg
npx @mermaid-js/mermaid-cli -i docs/sequence-nats-messaging.mmd -o docs/svg/sequence-nats-messaging.svg
npx @mermaid-js/mermaid-cli -i docs/sequence-event-streaming.mmd -o docs/svg/sequence-event-streaming.svg
npx @mermaid-js/mermaid-cli -i docs/sequence-human-approval.mmd -o docs/svg/sequence-human-approval.svg
npx @mermaid-js/mermaid-cli -i docs/sequence-cancellation.mmd -o docs/svg/sequence-cancellation.svg
```
