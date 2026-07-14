# Architecture Diagrams

This directory contains UML and sequence diagrams for the SWE-1.6 Agentic Engineering Platform.

## Component Diagrams

- **`architecture-component-diagram.mmd`** - High-level system architecture showing all components and their interactions
  - Client Layer (Angular Web UI - single entry point via Agent Service)
  - API Layer (Go Control Plane for resource management/container orchestration, Python Agent Service for proxy/auth/chatkit)
  - Worker Layer (CrewAI-based Python Agent Worker)
  - Messaging Layer (NATS JetStream with durable consumers)
  - Data Layer (PostgreSQL)
  - Execution Layer (Docker Workspaces)
  - External Services (OpenAI, Anthropic, Ollama)

- **`architecture-simple-flow.mmd`** - Simplified flow diagram showing the core request/event flow between components

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

- **Control Plane (Go)**: Manages users, organizations, projects, and repositories. Subscribes to NATS for chat lifecycle events (agent.control.{run_id}.start, agent.control.{run_id}.close) to manage agent containers. Accessed internally via agent-service proxy for UI requests.
- **Agent Service (Python)**: Handles ChatKit interactions, NATS messaging, and acts as single entry point for all UI requests. Provides proxy endpoints for control-plane APIs (auth, projects, repositories). Publishes NATS messages for chat start/close and subscribes to agent state events to update chat records.
- **Web UI (Angular)**: Provides user interface for chat and workflow monitoring. All API requests routed through agent-service proxy configuration.
- **NATS JetStream with Durable Consumers**: Provides reliable messaging between services. Uses user-scoped subject patterns for per-user routing and durable consumers for message persistence and recovery.
- **PostgreSQL**: Persistent storage for application data, checkpoints, events, and chat containers.
- **Docker Workspaces**: Isolated execution environments for agent operations, managed by control plane via NATS.
- **LangGraph**: Orchestrates the multi-phase engineering workflow within agent containers.
- **LangSmith**: Distributed tracing for LLM operations.

## Current State & Roadmap

The architecture and components described above are implemented and runnable. `make clean-start` demonstrates the full chat-to-container flow, and the worker now clones the selected repository into `/workspace` before the workflow starts. A custom CrewAI wrapper worker type discovers available agent projects and surfaces them in the chat session, so the user can pick which multi-agent project to run. The implementation is **demo-ready** rather than production-ready for personal projects.

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

- **NATS-Based Container Management**: Control plane subscribes to NATS agent.control.{run_id}.start/close messages to manage agent containers instead of HTTP endpoints.
- **User-Scoped Subject Routing**: NATS subjects use user-scoped patterns (agent.user.{uid}.chat.{rid}.*) for per-user message routing.
- **Worker Separation**: API and worker processes communicate via NATS for scalability.
- **Checkpoint Persistence**: LangGraph state persisted in PostgreSQL for recovery.
- **Event Streaming**: SSE for real-time UI updates with replay support.
- **Workspace Isolation**: Docker containers with resource limits for safe execution.
- **Human-in-the-Loop**: LangGraph interrupts for approval of sensitive operations.
- **Idempotency**: Message ID tracking to prevent duplicate processing.
- **Chat Lifecycle**: Complete lifecycle from chat start → container creation → agent execution → state updates → chat termination.

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
