# Agent Worker

Multi-agent worker process for isolated agent workflow execution. Runs in isolated containers with git access, communicating only via NATS. Supports both LangGraph workflows (single-agent and specialist-agent) and CrewAI project execution.

## Purpose

The agent worker is the **workflow execution layer** of the platform. It is responsible for:
- Executing LangGraph workflows in isolated containers (single-agent and specialist-agent modes)
- Running CrewAI projects with pexpect-based process execution
- Running real specialist agents with LLM integration
- Cloning git repositories to `/workspace`
- Subscribing to NATS commands (run.start, user events)
- Publishing state events back to NATS
- Workspace file operations and git commands
- Recursive workspace scanning for CrewAI project discovery

## Architecture

The agent-worker contains the **complete LangGraph workflow implementation** with real agent executions, plus a CrewAI execution layer. The agent-service (HTTP API layer) does NOT execute workflows - it only publishes NATS commands and streams events.

### Workflow Modes

The worker supports three execution modes:

1. **Single-Agent Mode**: Simplified LangGraph workflow with a single reasoning node that performs the entire task in one step
2. **Specialist-Agent Mode**: Full LangGraph workflow with specialist agents (skills-lead, repo-scout, solution-planner, implementers, validators)
3. **CrewAI Mode**: Executes external CrewAI projects using pexpect-based process runner with real-time output streaming

## Current State & Goal for Personal Use

**Current state:** The worker runs the full LangGraph graph inside a container, publishes state events, and can execute workspace tools (write/read files, git, tests) with the fake LLM provider. It now clones the selected repository into `/workspace` before the workflow starts. A custom CrewAI wrapper worker type discovers available agent projects and surfaces them in the UI chat session, so the user can pick which multi-agent project to run. It is **demo-ready** but not production-ready for real repositories.

**First goal:** Execute agentic AI workflows inside controlled, isolated containers, using a fully open-source stack and free local LLMs via Ollama.

**Personal-use goal:** Execute repository-based engineering tasks in an isolated container, so a single user can ask for changes, review them, and approve or reject them before the workflow finishes.

## Next Milestone

1. **Approval workflow:** Wire `waiting_approval_node` to a real LangGraph interrupt, emit `approval_required` events, and resume on `tool.allowed`/`tool.denied` user events.
2. **Budget tracking:** Accumulate token/cost usage in `model_factory.py` and enforce `max_tokens`/`max_cost` in the graph.
3. **End-to-end tests:** Add an integration test that starts a container, runs a workflow, and asserts `completed` is reached.

See main [README.md](../../README.md) for future goals and milestones.

**Responsibilities:**
- LangGraph workflow execution (single-agent and specialist-agent modes)
- CrewAI project execution with pexpect-based process runner
- Real specialist agent implementations (skills-lead, repo-scout, solution-planner, implementers, validators) - framework implemented, not yet tested end-to-end
- Workspace operations (read/write files, git commands, test execution)
- NATS event publishing (agent.user.{uid}.events.{rid}.state.{event_type}, agent.user.{uid}.chat.{rid}.events)
- CrewAI project discovery and workspace scanning
- Interactive input prompt handling for CrewAI processes

**What it does NOT do:**
- HTTP API endpoints (handled by agent-service)
- PostgreSQL thread/message store (handled by agent-service)
- ChatKit protocol implementation (handled by agent-service)

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

## Project Structure

```
agent-worker/
├── internal/
│   ├── agents/             # Agent framework implementations
│   │   ├── crewai/         # CrewAI integration
│   │   ├── single-agent/   # Single-agent mode
│   │   └── specialist/     # Specialist agent workflow
│   ├── handlers/           # NATS message handlers
│   ├── messaging/          # NATS messaging layer
│   ├── skills/             # Skill definitions
│   ├── tools/              # Tool implementations
│   ├── workflow/           # LangGraph workflow definitions
│   └── workspace/          # Workspace operations
├── scripts/                # Container startup scripts
└── tests/
    └── integration/         # Integration tests
```

## Environment Variables

- `RUN_ID`: Run ID for the worker
- `REPOSITORY_URL`: Git repository URL to clone
- `BRANCH`: Git branch to checkout (default: main)
- `GIT_USERNAME`: Git username for authentication (optional)
- `GIT_TOKEN`: Git token for authentication (optional)
- `NATS_URL`: NATS server URL (default: nats://localhost:4222)
- `MOCK_MODE`: Enable mock mode for testing (default: false)
- `LLM_PROVIDER`: LLM provider to use (ollama, openai, anthropic, fake)
- `AGENT_TYPE`: Agent type to execute (single-agent, specialist, crewai)

## Container Startup

The container runs `scripts/container-start.sh` which:
1. Clones the repository to `/workspace` (or creates mock structure)
2. Configures git credentials if provided
3. Starts the worker process with `python -m app.worker --run-id $RUN_ID`

## NATS Integration

The worker uses NATS JetStream with durable consumers. It publishes to:
- `agent.user.{uid}.events.{rid}.state.{event_type}` - State events (created, planning, implementing, completed, etc.)
- `agent.user.{uid}.chat.{rid}.worker.events` - Worker output events (final_answer, progress_update)
- `agent.control.worker.{rid}.ready` - Worker ready signal

The worker subscribes to:
- `agent.user.{uid}.chat.{rid}.user.events` - User events (tool.allowed, tool.denied, user_input) from agent-service
- `agent.control.worker.{rid}.close` - Control close signal for cancellation

For CrewAI execution, additional NATS subjects are used:
- `agent.user.{uid}.chat.{rid}.events` - CrewAI state and chat events
- `agent.user.{uid}.chat.{rid}.user.events` - CrewAI user input events

The worker auto-starts from environment variables and subscribes to user events for tool approval handling and interactive input prompts.

## Dependencies

See `pyproject.toml` for full dependencies. Key dependencies:
- `langgraph` - Workflow execution
- `langchain-*` - LLM integration
- `nats-py` - NATS messaging
- `docker` - Docker API access
- `pexpect` - Process spawning and output streaming for CrewAI
- `crewai` - CrewAI framework support

## Architecture

```
NATS Command → Worker → LangGraph Workflow → NATS Events
                      ↓
                /workspace
                (git repo)

NATS Command → Worker → CrewAI ProcessRunner → NATS Events
                      ↓
                /workspace
                (CrewAI project)
```

### CrewAI Components

The CrewAI integration includes:

- **ProcessRunner** (`internal/agents/crewai/src/agent_worker/runner.py`): pexpect-based process runner that spawns CrewAI projects, streams output in real-time, and handles interactive input prompts
- **Bootstrap** (`internal/agents/crewai/src/agent_worker/bootstrap.py`): Workspace resolution, command detection, and recursive CrewAI project discovery
- **CrewAINatsClient** (`internal/agents/crewai/src/agent_worker/nats_client.py`): NATS client tailored for CrewAI worker messaging with state and chat event publishing
- **Events** (`internal/agents/crewai/src/agent_worker/events.py`): Event payload builders for CrewAI state and chat events
- **NATS Handler Integration** (`internal/handlers/nats.py`): NATS message handler that detects CrewAI projects and routes to CrewAI execution

## Separation from Agent Service

- **Agent Service**: HTTP API layer (`services/agent-service`)
  - Exposes REST endpoints
  - Manages ChatKit database records
  - Publishes commands to NATS
  - Handles ChatKit protocol
  
- **Agent Worker**: Workflow execution layer (`services/agent-worker`)
  - Runs in isolated containers
  - Executes LangGraph workflows (single-agent and specialist-agent)
  - Executes CrewAI projects via ProcessRunner
  - Subscribes to NATS commands
  - Scans workspace for CrewAI projects

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
- Workflow execution and state event publishing
- Event publishing to agent.user.{uid}.events.{rid}.state.* and agent.user.{uid}.chat.{rid}.worker.events subjects
