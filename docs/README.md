# Architecture Diagrams

This directory contains UML and sequence diagrams for the SWE-1.6 Agentic Engineering Platform.

## Component Diagrams

- **`architecture-component-diagram.mmd`** - High-level system architecture showing all components and their interactions
  - Client Layer (Angular Web UI - single entry point via Agent Service)
  - API Layer (Go Control Plane for resource management/container orchestration, Python Agent Service for proxy/auth/chatkit)
  - Worker Layer (Python Agent Worker with four variants: `specialist`, `single-agent`, `crewai`, `crewai-expert`)
  - Messaging Layer (NATS JetStream with durable consumers; separate control, state event, and chat/user event streams)
  - Data Layer (PostgreSQL)
  - Execution Layer (Docker Workspaces spawned by the Control Plane)
  - External Services (OpenAI, Anthropic, Ollama)

- **`architecture-simple-flow.mmd`** - Simplified flow diagram showing the core request/event flow between components
- **`crewai-expert-flow.mmd`** - Simplified `crewai-expert` flow showing UI → worker → CrewAI CLI command → worker run state → UI

## Sequence Diagrams

### Core Flows

- **`sequence-chat-lifecycle.mmd`** - Complete chat lifecycle flow
  - User starts chat from UI with optional GitHub repository
  - Python service publishes NATS agent.control.{run_id}.start message
  - Control plane creates agent container via NATS
  - Orchestrator agent executes sequence of specialist agents
  - Each agent publishes state updates via NATS
  - Python service updates chat state and streams to UI
  - User observes events until human intervention requested
  - Chat termination via NATS agent.control.{run_id}.close message

- **`sequence-chatkit-chat.mmd`** - ChatKit chat interaction flow
  - User message through Angular UI
  - Thread creation/retrieval
  - LLM streaming response
  - Message persistence

- **`sequence-workflow-trigger.mmd`** - Workflow trigger and execution flow
  - ChatKit triggering agent workflow
  - NATS-based container creation
  - Worker execution initiation
  - LangGraph checkpoint persistence
  - Agent state updates via NATS

### Workflow Execution

- **`sequence-langgraph-workflow.mmd`** - Complete LangGraph workflow execution
  - State transitions through all phases
  - Specialist agent execution (SCOUTING, PLANNING, DESIGNING)
  - Parallel implementation agents
  - Validation agents (TESTING, REVIEWING, VERIFYING)
  - Repair loop handling
  - Workspace lifecycle

### Approval & Cancellation

- **`sequence-human-approval.mmd`** - Human approval workflow
  - Protected action detection
  - LangGraph interrupt for approval
  - Approval dialog in Angular UI
  - Approval/rejection handling
  - Workflow resumption

- **`sequence-cancellation.mmd`** - Run cancellation flow
  - User cancellation request
  - Cancellation flag propagation
  - Node boundary checks
  - Workspace cleanup
  - Terminal state handling

### Infrastructure

- **`sequence-event-streaming.mmd`** - Event streaming and SSE
  - SSE connection establishment
  - Event publication from LangGraph
  - NATS event streaming with chat-based subjects
  - PostgreSQL event persistence
  - Browser reconnection with Last-Event-ID
  - LangSmith tracing integration

- **`sequence-nats-messaging.mmd`** - NATS JetStream messaging
  - Chat start/close message publishing and consumption
  - Agent command publishing and consumption
  - Event publishing and consumption
  - User-scoped subject patterns (agent.user.{uid}.chat.{rid}.*)
  - Durable consumer setup
  - Idempotency handling
  - Dead letter queue
  - Worker recovery and message redelivery

## Viewing Diagrams

These diagrams are written in Mermaid format. You can view them using:

1. **GitHub/GitLab** - Native Mermaid rendering in markdown files
2. **VS Code** - Install the "Mermaid Preview" extension
3. **Online** - Use [Mermaid Live Editor](https://mermaid.live/)
4. **CLI** - Use `mmdc` (Mermaid CLI) to render to PNG/SVG

## Architecture Overview

The platform follows a microservices architecture with a single entry point pattern:

- **Control Plane (Go)**: Manages users, organizations, projects, and repositories. Subscribes to NATS for chat lifecycle events (`agent.control.{run_id}.start/close/resume`) to create and terminate per-run Docker containers. Accessed internally via agent-service proxy for UI requests.
- **Agent Service (Python)**: FastAPI service that handles ChatKit interactions, NATS messaging, and acts as the single entry point for all UI requests. Stores chat threads and items in its own PostgreSQL schema, proxies control-plane APIs (auth, projects, repositories), and streams worker events to the UI via SSE.
- **Web UI (Angular)**: Provides the chat interface and workflow monitoring. All API requests are routed through the agent-service proxy; the UI uses a custom Angular SSE client for streaming events.
- **Agent Worker (Python)**: Runs inside ephemeral Docker containers created by the control plane. Four variants exist: `specialist` (multi-phase LangGraph), `single-agent` (simplified LangGraph), `crewai` (CrewAI project runner), and `crewai-expert` (CrewAI with dependency patching and approvals).
- **NATS JetStream with Durable Consumers**: Provides reliable messaging between services. Uses separate streams for control commands, state events, and chat/user events; user-scoped subject patterns route events per user/run.
- **PostgreSQL**: Persistent storage for application data, LangGraph checkpoints, events, and chat containers.
- **Docker Workspaces**: Isolated execution environments created by the control plane; the worker process runs inside them and clones the target repository into `/workspace`.
- **LangGraph / CrewAI**: Orchestrates workflows within agent containers depending on the selected worker variant.
- **LangSmith**: Distributed tracing for LLM operations (where configured).

## Current State & Roadmap

The architecture and components described above are implemented and runnable. `make clean-start` demonstrates the full chat-to-container flow, and the worker clones the selected repository into `/workspace` before the workflow starts. The UI lets the user pick one of four worker variants (`specialist`, `single-agent`, `crewai`, `crewai-expert`). CrewAI variants discover available agent projects and present them as cards, and `crewai-expert` adds dependency patching and approval workflows. The implementation is **demo-ready** rather than production-ready for personal projects.

### Development Mode

**Use this for testing changed code locally** - run specific services locally while others run in docker-compose using the `start-local` makefile target:

```bash
# Run web UI locally, other services in docker-compose
make start-local SERVICES=web

# Run web and agent-service locally, others in docker-compose
make start-local SERVICES=web,agent-service

# Run control-plane locally, others in docker-compose
make start-local SERVICES=control-plane
```

The target automatically starts the specified services locally in the background while docker-compose services run in containers. This provides faster development iteration with hot-reload for local services, making it ideal for testing code changes without rebuilding containers, while infrastructure services (PostgreSQL, NATS) continue running in containers.

**First goal:** Orchestrate agentic AI workflows in controlled isolated environments with secured remote controls, full open-source usage, and free local LLMs.

**Personal-use goal:** A single-user home instance that can run a real repository-based engineering workflow, show live progress, and wait for user approval before destructive actions.

**Next milestone:**
- Wire LangGraph interrupts for real human approval.
- Track and enforce LLM token/cost budgets.
- Add an automated end-to-end test that runs the full chat-to-completed flow.

**Future milestone:** The platform can **edit its own code**, **simulate fixes**, and **redeploy itself** — becoming a self-hosting, self-improving agentic engineering system.

**Future goal / Kubernetes milestone:** Add first-class Kubernetes deployment support alongside the existing `docker-compose` setup with Helm charts, worker pod orchestration, ingress, observability, and security hardening.

**Personal goal:** This repository is intended to be a strong, opinionated starter for building microservice systems. The architecture — containerized services, NATS event-driven messaging, control-plane/agent separation, proxy API, Angular UI, and isolated workers — provides a complete pattern that can be adapted for other projects.

## Key Design Patterns

- **NATS-Based Container Management**: Control plane subscribes to NATS `agent.control.{run_id}.start/close/resume` messages to create/terminate per-run Docker containers instead of HTTP endpoints.
- **User-Scoped Subject Routing**: NATS subjects use user-scoped patterns for per-user/per-run routing:
  - State events: `agent.user.{uid}.events.{rid}.state.{event_type}`
  - Worker chat events: `agent.user.{uid}.chat.{rid}.worker.events`
  - User chat events: `agent.user.{uid}.chat.{rid}.user.events`
- **Separate Command, State, and Chat Streams**: Control commands, workflow state events, and interactive chat events travel on distinct JetStream streams (`AGENT_CONTROL`, `AGENT_EVENTS`, `AGENT_CHAT`).
- **Worker Separation**: Agent-service (HTTP/NATS API layer) and agent-worker (execution layer) communicate only via NATS; workers run inside containers spawned by the control-plane.
- **Checkpoint Persistence**: LangGraph state persisted in PostgreSQL for recovery.
- **Event Streaming**: SSE for real-time UI updates; worker events are bridged from NATS to the SSE stream.
- **Workspace Isolation**: Docker containers with resource limits for safe execution; the control-plane creates the container and the worker clones the repo into `/workspace`.
- **Human-in-the-Loop**: LangGraph interrupts and CrewAI Expert approval nodes pause for user approval on sensitive operations.
- **Idempotency**: Message ID tracking to prevent duplicate processing.
- **Chat Lifecycle**: Complete lifecycle from chat start → container creation → agent execution → state/chat updates → chat termination.

## Diagram Source Files and Regeneration

### Source Files

The Mermaid source files are available in the `docs/` directory for editing:
- [architecture-component-diagram.mmd](architecture-component-diagram.mmd)
- [architecture-simple-flow.mmd](architecture-simple-flow.mmd)
- [sequence-chat-lifecycle.mmd](sequence-chat-lifecycle.mmd)
- [sequence-chatkit-chat.mmd](sequence-chatkit-chat.mmd)
- [sequence-workflow-trigger.mmd](sequence-workflow-trigger.mmd)
- [sequence-langgraph-workflow.mmd](sequence-langgraph-workflow.mmd)
- [sequence-nats-messaging.mmd](sequence-nats-messaging.mmd)
- [sequence-event-streaming.mmd](sequence-event-streaming.mmd)
- [sequence-human-approval.mmd](sequence-human-approval.mmd)
- [sequence-cancellation.mmd](sequence-cancellation.mmd)
- [sequence-crewai-services.mmd](sequence-crewai-services.mmd) - CrewAI container/service-level flow
- [sequence-crewai-worker-internals.mmd](sequence-crewai-worker-internals.mmd) - CrewAI worker internal components

### Regenerating Diagrams

To regenerate SVG images after modifying the Mermaid source files:

```bash
# Install mermaid-cli (first time only)
npx @mermaid-js/mermaid-cli --version

# Regenerate all diagrams
npx @mermaid-js/mermaid-cli -i architecture-component-diagram.mmd -o svg/architecture-component-diagram.svg
npx @mermaid-js/mermaid-cli -i architecture-simple-flow.mmd -o svg/architecture-simple-flow.svg
npx @mermaid-js/mermaid-cli -i crewai-expert-flow.mmd -o svg/crewai-expert-flow.svg
npx @mermaid-js/mermaid-cli -i sequence-chat-lifecycle.mmd -o svg/sequence-chat-lifecycle.svg
npx @mermaid-js/mermaid-cli -i sequence-chatkit-chat.mmd -o svg/sequence-chatkit-chat.svg
npx @mermaid-js/mermaid-cli -i sequence-workflow-trigger.mmd -o svg/sequence-workflow-trigger.svg
npx @mermaid-js/mermaid-cli -i sequence-langgraph-workflow.mmd -o svg/sequence-langgraph-workflow.svg
npx @mermaid-js/mermaid-cli -i sequence-nats-messaging.mmd -o svg/sequence-nats-messaging.svg
npx @mermaid-js/mermaid-cli -i sequence-event-streaming.mmd -o svg/sequence-event-streaming.svg
npx @mermaid-js/mermaid-cli -i sequence-human-approval.mmd -o svg/sequence-human-approval.svg
npx @mermaid-js/mermaid-cli -i sequence-cancellation.mmd -o svg/sequence-cancellation.svg
npx @mermaid-js/mermaid-cli -i sequence-crewai-services.mmd -o svg/sequence-crewai-services.svg
npx @mermaid-js/mermaid-cli -i sequence-crewai-worker-internals.mmd -o svg/sequence-crewai-worker-internals.svg
```
