# Complete Chat-to-Agent Flow Documentation

## Overview
This document describes the complete flow from UI start page to agent execution, including all NATS messages, service interactions, and state transitions.

## Architecture Components

### Services
1. **Angular UI** (port 4200) - User interface with a custom SSE client
2. **Python Agent Service** (port 8000) - FastAPI ChatKit server, NATS bridge, SSE streaming, and control-plane proxy. Persists chat threads/items in its local PostgreSQL schema.
3. **Go Control Plane** (port 8080) - Container management and repository/project access
4. **NATS JetStream** (port 4222) - Message broker with durable consumers
5. **PostgreSQL** (host port 5433, container port 5432) - Data persistence for control-plane, agent-service, and LangGraph checkpoints
6. **Agent Worker** - Executes the selected workflow inside a Docker container created by the control-plane. Variants:
   - `specialist` — multi-phase LangGraph workflow
   - `single-agent` — simplified single-agent LangGraph workflow
   - `crewai` — CrewAI project runner with project discovery
   - `crewai-expert` — CrewAI with dependency patching and approval workflow

### Key Tables
- `agent.chatkit_threads` - Chat thread persistence (agent-service)
- `agent.chatkit_items` - Chat messages (agent-service)
- `app.chat_containers` - Container lifecycle tracking (control-plane)
- `agent.agent_runs` - Workflow execution tracking
- `agent.agent_events` - Event history

## Complete Flow

### Step 1: User Starts New Project
**Location:** `apps/web/src/app/projects/projects.component.ts`

1. User navigates to `/` (projects page)
2. UI loads projects from agent-service (proxied to control-plane): `GET /api/projects`
3. User clicks "New Project" or selects existing project
4. User optionally selects GitHub repository (or none)
5. User clicks "Start Chat"

**Navigation:** `router.navigate(['/chat'], { queryParams: { project_id, repository_id } })`

### Step 2: Chat Window Opens
**Location:** `apps/web/src/app/chat/chat.component.ts` and `apps/web/src/app/chat-config/chat-config.component.ts`

1. Angular navigates to `/chat?project_id=X&repository_id=Y`
2. `ChatConfigComponent` prompts the user to choose:
   - **Agent type**: `specialist`, `single-agent`, `crewai`, or `crewai-expert`
   - **LLM provider**: `ollama`, `openai`, `anthropic`, or `fake`
   - **Model name** and **API key** (when required)
   - **Mock mode** toggle
3. Selected configuration is persisted in `localStorage` and passed with every message.
4. `ChatComponent` initializes a custom Angular chat UI and opens an SSE connection to the agent-service for streaming responses.

### Step 3: User Sends First Message
**Location:** `apps/web/src/app/chat/chat.component.ts` → `services/agent-service/internal/chatkit/router.py`

1. User types a message and clicks **Send**.
2. `ChatComponent` posts to `POST /api/chatkit/` with the configuration selected in Step 2:
   ```json
   {
     "message": "Add a login feature",
     "repository_id": "repo-123",
     "project_id": "proj-456",
     "run_id": "run-...",
     "trigger_workflow": true,
     "mock_mode": false,
     "llm_provider": "ollama",
     "model_name": "qwen3.5:9b",
     "agent_type": "specialist",
     "api_key": ""
   }
   ```

### Step 4: Python Service Starts Chat
**Location:** `services/agent-service/internal/chatkit/router.py` and `services/agent-service/internal/chatkit/server.py`

**Actions:**
1. Reuse an existing thread/run ID if one exists for the project, otherwise create a new `run-{uuid}` thread ID and persist it in the agent-service PostgreSQL schema.
2. Save the user message to `agent.chatkit_items`.
3. Build agent metadata from the request context.
4. Publish the run start command via `NatsBridge.publish_agent_start`, which delegates to `NATSMessaging.publish_chat_start`.

**NATS Message 1 - Run Start:**
```python
# Subject: agent.control.{run_id}.start
await nats_bridge.publish_agent_start(
    run_id=run_id,
    conversation_id=run_id,
    user_subject=user_id,
    prompt=message,
    metadata={
        "repository_id": repository_id,
        "project_id": project_id,
        "mock_mode": False,
        "agent_type": "specialist",  # or single-agent / crewai / crewai-expert
        "llm_provider": "ollama",
        "model_name": "qwen3.5:9b",
        "api_key": "",
        "max_tokens": 0,
        "max_cost": 0.0,
        "max_repair_count": 2,
    },
)
```

**Log Output:**
```
[NATS PUBLISH] Publishing chat start {message_id} to subject: agent.control.{run_id}.start
[NATS PUBLISH] Chat start payload: {...}
```

5. `AegisChatKitServer.respond()` creates an in-memory event stream (`internal/event_streams.py`) and returns a `StreamingResponse` to the UI.
6. The agent-service subscribes to the global event stream `agent.user.*.events.>` for worker state events and to `agent.user.*.chat.*.worker.events` for worker chat output events.

### Step 5: Control Plane Creates Container
**Location:** `services/control-plane/internal/handlers/nats.go` and `services/control-plane/internal/service/chat_container.go`

**NATS Subscriber:** `agent.control.>`

**Actions:**
1. Receive `agent.control.{run_id}.start` message:
   ```
   [NATS RECEIVE] Received chat start message on subject: agent.control.{run_id}.start
   [NATS RECEIVE] Chat start payload: {...}
   [NATS RECEIVE] Run ID: {run_id}, Repository ID: {repo_id}, Mock Mode: false, Agent Type: {agent_type}, LLM Provider: {llm_provider}
   ```

2. Look up an existing container for the run ID; if it exists and is running, reuse it. Otherwise stop/remove the dead container and create a new one for the requested `agent_type`.
3. Create the Docker container via `CreateContainerForAgentType(agentType, ...)`:
   ```go
   chatContainerService.CreateContainerForAgentType(
       agentType, repoConfig, llmConfig, &runParams,
   )
   ```
   Supported `agent_type` values: `specialist`, `single-agent`, `crewai`, `crewai-expert`.
   - Container includes environment variables: `RUN_ID`, `USER_ID`, `TASK`, `PROJECT_ID`, `REPOSITORY_ID`, `AGENT_TYPE`, `LLM_PROVIDER`, `MODEL_NAME`, etc.
   - The container startup script (`scripts/container-start.sh`) clones the repository into `/workspace`.
   - Container starts the worker process defined by `PYTHON_MODULE` (e.g., `agent_worker.main`, `crewai_expert.main`).

4. Persist the `ChatContainer` record in the control-plane database.

**Log Output:**
```
[NATS RECEIVE] Creating {agent_type} container for run {run_id} with LLM provider {llm_provider}
[NATS RECEIVE] Successfully created container for run {run_id}
```

### Step 6: Worker Auto-Starts Workflow
**Location:** `services/agent-worker/scripts/container-start.sh` and the worker module configured by `PYTHON_MODULE`

**Actions:**
1. Container starts the worker process via `PYTHON_MODULE` (e.g., `internal.agents.crewai.src.agent_worker.main` for `crewai`, `crewai_expert.main` for `crewai-expert`, or the legacy `agent_worker.main` entry point).
2. Worker connects to NATS and creates JetStream streams.
3. Worker reads run parameters from environment variables:
   - `RUN_ID`, `USER_ID`, `TASK`, `PROJECT_ID`, `REPOSITORY_ID`, `AGENT_TYPE`, `LLM_PROVIDER`, `MODEL_NAME`, `MOCK_MODE`, etc.
4. Worker auto-starts the run. For LangGraph variants this calls `handle_run_start(run_id, payload, create_run, get_checkpointer, worker)`; for CrewAI variants it starts the pexpect-based `ProcessRunner` and publishes state/chat events.
5. Worker publishes a ready signal to `agent.control.worker.{run_id}.ready`.

**Log Output:**
```
[WORKER] Starting agent worker for run {run_id}
[WORKER] Auto-starting run {run_id}
[WORKER] Agent worker started and auto-started run {run_id}
```

### Step 7: Worker Executes the Selected Workflow
**Location:** Depends on `agent_type`:
- `specialist` / `single-agent`: `services/agent-worker/internal/agents/specialist/` and `services/agent-worker/internal/agents/single_agent/`
- `crewai`: `services/agent-worker/internal/agents/crewai/src/agent_worker/`
- `crewai-expert`: `services/agent-worker/internal/agents/crewai-expert/src/crewai_expert/`

**LangGraph variants (`specialist` / `single-agent`) state transitions:**
1. CREATED
2. PREPARING_WORKSPACE
3. SCOUTING
4. PLANNING
5. DESIGNING
6. IMPLEMENTING
7. TESTING
8. REVIEWING
9. VERIFYING
10. COMPLETED (or REPAIRING → back to IMPLEMENTING)

**CrewAI variants (`crewai` / `crewai-expert`):**
- Discover available CrewAI projects in `/workspace`.
- Stream project list to the UI as a `thread.item.done` event (rendered as selectable cards).
- Once a project is selected, run the CrewAI process with pexpect, streaming output as `progress_update` events.
- `crewai-expert` is a specialized LangGraph agent that prepares and executes a generic CrewAI agent: it handles dependency inspection, patch generation/approval, dependency syncing, and then runs the CrewAI CLI.

#### CrewAI Expert Detailed Flow

For the `crewai-expert` worker the execution path is:

1. **Project discovery** — the worker scans `/workspace` for CrewAI projects and publishes the list as a chat event (`agent.user.{uid}.chat.{rid}.worker.events`).
2. **Project selection** — the UI renders the list as cards; the user's choice is sent back as `agent.user.{uid}.chat.{rid}.user.events`.
3. **Prepare project** — the worker resolves the project, inspects dependencies, generates a patch, pauses for user approval, applies the patch, and syncs dependencies.
4. **Run CrewAI CLI** — the worker spawns `crewai run` as a pexpect subprocess and streams stdout/stderr as progress updates.
5. **Completion** — the worker publishes its terminal state (`Completed`, `Failed`, or `Cancelled`) and final chat events to NATS, which are streamed to the UI.

See the simplified flow diagram at [`docs/crewai-expert-flow.mmd`](crewai-expert-flow.mmd) / [`docs/svg/crewai-expert-flow.svg`](svg/crewai-expert-flow.svg).

**For Each State Transition:**

**NATS Message 2+ - Agent State Updates:**
```python
# Subject: agent.user.{uid}.events.{rid}.state.{event_type}
await nats.publish_event(
    event_type=event_type,
    run_id=run_id,
    user_id=user_id,
    payload={
        "state": event_type,
        "agent": agent_name,
        "data": {...}
    }
)
```

Worker chat output events are also published to `agent.user.{uid}.chat.{rid}.worker.events`.

**Log Output:**
```
[NATS PUBLISH] Publishing event {message_id} to subject: agent.user.{uid}.events.{rid}.state.scouting
[NATS PUBLISH] Event payload: {...}
[NATS PUBLISH] Successfully published event {message_id} to agent.user.{uid}.events.{rid}.state.scouting
```

### Step 8: Python Service Receives Agent Events
**Location:** `services/agent-service/internal/handlers/nats.py` and `services/agent-service/internal/chatkit/server.py`

**NATS Subscribers:**
- `agent.user.*.events.>` for worker state events
- `agent.user.*.chat.*.worker.events` for worker chat output events
- `agent.control.worker.*.ready` for worker ready signals

**Actions:**
1. Receive event
   ```
   [NATS RECEIVE] Received event on subject: agent.user.{uid}.events.{rid}.state.scouting
   [NATS RECEIVE] Event payload: {...}
   [NATS RECEIVE] Received agent event for run {run_id}: {...}
   ```

2. Push event into the in-memory event stream for the run (`internal/event_streams.py`).
3. `AegisChatKitServer.respond()` consumes the stream and maps events to ChatKit-compatible SSE events (`progress_update`, `thread.item.done`).
4. Forward to UI via SSE (Server-Sent Events).

### Step 9: UI Displays Agent Updates
**Location:** `apps/web/src/app/chat/chat.component.ts` (custom SSE client)

**UI Receives ChatKit-compatible SSE events:**
```
data: {"type": "progress_update", "icon": "agent", "text": "Analyzing repository structure..."}
data: {"type": "thread.item.done", "item": {"thread_id": "run-...", "role": "assistant", "content": [{"type": "input_text", "text": "..."}]}}
```

For CrewAI project selection the assistant message contains a JSON array of projects; the UI renders them as clickable cards.

**User Observes:**
- Real-time agent activity in the chat window
- State transitions and progress updates
- Agent messages, project cards, and artifact references
- Activity panel with full run timeline

### Step 10: Human Intervention (if needed)
**Trigger:** Protected action (push, PR, network access, etc.) in LangGraph workflows, or a patch approval checkpoint in `crewai-expert`.

**State:** `WAITING_APPROVAL` or an approval event published to `agent.user.{uid}.chat.{rid}.worker.events`.

**NATS Message - Approval Request:**
```python
# Subject: agent.user.{uid}.events.{rid}.state.waiting_approval
await nats.publish_event(
    event_type="waiting_approval",
    run_id=run_id,
    user_id=user_id,
    payload={
        "approval_id": approval_id,
        "action": "push_code",
        "reason": "Push to main branch requires approval"
    }
)
```

**UI Shows:** Approval dialog or inline approval options rendered in the chat message.

**User Action:** Approve or Reject

The UI publishes the decision as a user chat event to `agent.user.{uid}.chat.{rid}.user.events`. The agent-service forwards it to the worker.

**NATS Message - User Approval/Event:**
```python
# Subject: agent.user.{uid}.chat.{rid}.user.events
await nats.publish_chat_event(
    event_type="tool.allowed",  # or "tool.denied"
    run_id=run_id,
    user_id=user_id,
    payload={
        "tool_name": "push_code",
        "decision": "approved",
    }
)
```

**Resume/Continue:**
- For LangGraph variants the worker resumes the same graph thread from the PostgreSQL checkpoint.
- For `crewai-expert` the worker consumes the approval event and continues execution.

For explicit resume after container loss the agent-service can publish:
```python
# Subject: agent.control.{run_id}.resume
await nats.publish_chat_resume(
    run_id=run_id,
    repository_id=repository_id,
    project_id=project_id,
    mock_mode=False,
    agent_type="specialist",  # or single-agent / crewai / crewai-expert
    llm_provider="ollama",
    api_key=""
)
```

**Control Plane Actions (on resume):**
1. Receives `agent.control.{run_id}.resume`
2. Recreates container with same parameters
3. Worker auto-starts and resumes from checkpoint or previous state

### Step 11: Workflow Completion
**Final State:** `COMPLETED`, `FAILED`, `CANCELLED`, or `BUDGET_EXCEEDED`

The worker publishes a final state event to `agent.user.{uid}.events.{rid}.state.{event_type}` and a terminal chat event to `agent.user.{uid}.chat.{rid}.worker.events`. The agent-service maps this to a `thread.item.done` SSE event containing the final answer text.

**NATS Message - Final Event:**
```python
# Subject: agent.user.{uid}.events.{rid}.state.completed
await nats.publish_event(
    event_type="completed",
    run_id=run_id,
    user_id=user_id,
    payload={
        "status": "completed",
        "artifacts": [...],
        "summary": "..."
    }
)
```

**Worker Log:**
```
[WORKER] Run for run {run_id} completed with status completed
```

**UI Shows:** Final status, summary, and any project cards or artifact references included in the final assistant message.

### Step 12: Chat Termination (Optional)
**Trigger:** User clicks **Close session** in the chat UI.

**API Call:** `POST /api/chatkit/close/{thread_id}`

**NATS Message - Chat Close:**
```python
# Subject: agent.control.{run_id}.close
await nats.publish_chat_close(run_id=run_id)
```

**Log Output:**
```
[NATS PUBLISH] Publishing chat close {message_id} to subject: agent.control.{run_id}.close
[NATS PUBLISH] Chat close payload: {...}
```

**Control Plane Actions:**
1. Receive chat.close message
   ```
   [NATS RECEIVE] Received chat close message on subject: agent.control.{run_id}.close
   [NATS RECEIVE] Chat close payload: {...}
   [NATS RECEIVE] Run ID: {run_id}
   ```

2. Stop the worker container
3. Remove the container record from the database
4. Update `ChatContainer` status
   ```
   [NATS RECEIVE] Successfully terminated container for run {run_id}
   ```

## NATS Subject Patterns

### Control Signals (Agent-Service → Control-Plane)
- `agent.control.{run_id}.start` - Start run with all parameters (`user_id`, `task`, `project_id`, `agent_type`, `llm_provider`, etc.)
- `agent.control.{run_id}.close` - Close run (stop & remove container)
- `agent.control.{run_id}.resume` - Resume run (recreate container)

### Worker Ready Signals (Worker → Agent-Service / Control-Plane)
- `agent.control.worker.{run_id}.ready` - Worker publishes a ready signal after it starts

### State Events (Worker → Agent-Service)
- `agent.user.{uid}.events.{rid}.state.{event_type}` - Workflow state transition events
  - `created`, `preparing_workspace`, `scouting`, `planning`, `designing`
  - `implementing`, `testing`, `reviewing`, `verifying`, `repairing`
  - `waiting_approval`, `completed`, `failed`, `cancelled`, `budget_exceeded`, `reasoning`, `final_answer`

### Chat Events
- `agent.user.{uid}.chat.{rid}.worker.events` - Worker chat output events (`progress_update`, `thread.item.done`)
- `agent.user.{uid}.chat.{rid}.user.events` - User input / approval events sent from the UI/agent-service to the worker (`user_input`, `tool.allowed`, `tool.denied`)
- `agent.user.*.chat.errors` - Error stream for worker/agent failures

### Subscription Patterns
- `agent.control.>` - All control signals (Control Plane subscription)
- `agent.user.*.events.>` - All agent state events (Agent Service global event stream)
- `agent.user.*.chat.*.worker.events` - Worker chat output events (Agent Service)
- `agent.user.{uid}.chat.{rid}.user.events` - User events for a specific run (Worker subscription)

## Error Handling

### No Response After 30 Seconds
**Possible Causes:**
1. NATS not running
2. Control plane not subscribed to `agent.control.>`
3. Container creation failed
4. Worker not running or failed to auto-start
5. Workflow execution error

**Debug Steps:**
1. Check NATS connection: `docker logs agentic-nats`
2. Check control plane logs for `agent.control.{run_id}.start` receipt
3. Check container status: `docker ps`
4. Check worker logs for auto-start errors (`docker logs <container-name>`)
5. Check PostgreSQL for the run/chat container records

### Container Creation Fails
**Symptoms:** No `agent.user.{uid}.events.{rid}.state.*` or `agent.user.{uid}.chat.{rid}.worker.events` events published

**Debug:**
- Check control plane logs
- Check Docker daemon status and socket permissions
- Check repository access credentials
- Verify the requested `agent_type` has a matching image built (e.g., `agentic-agents-platform-agent-worker-crewai-expert:latest`)

### Workflow Doesn't Start
**Symptoms:** Container created but no state events

**Debug:**
- Check worker logs for auto-start errors
- Check environment variables in container (`AGENT_TYPE`, `LLM_PROVIDER`, `PYTHON_MODULE`)
- Check PostgreSQL connection from inside the worker container
- Check LangGraph checkpointer setup
- For CrewAI variants verify the target project exists in `/workspace`

## Testing

### E2E Test Flow
1. Navigate to projects page
2. Create or select project
3. Optionally add GitHub repository
4. Click "Start Chat"
5. In the config modal select an **Agent type** (`specialist`, `single-agent`, `crewai`, or `crewai-expert`) and **LLM provider**
6. Verify chat window opens
7. Send message with `trigger_workflow=true`
8. Wait for first agent update (max 30s)
9. Verify progress updates appear in the chat
10. For CrewAI variants verify project cards appear and are selectable

### Mock Mode
Set `mock_mode=true` (or select **Mock mode** in the UI) to skip:
- Actual LLM API calls

Note: container creation and repository cloning still happen unless `MOCK_DOCKER=true` is set in the control-plane environment. For a fully local smoke test run `make mock-llm-start`, which sets `LLM_PROVIDER=fake` on a clean stack.

### Starting an Agent Without a Message
Use the new `POST /api/chatkit/start` endpoint to spawn a worker container without sending a chat message:
```bash
curl -X POST http://localhost:8000/api/chatkit/start \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "project_id": "proj-456",
    "repository_id": "repo-123",
    "agent_type": "specialist",
    "llm_provider": "fake",
    "mock_mode": true
  }'
```

## Monitoring

### Key Metrics
- Chat start latency (UI → container ready)
- Workflow trigger latency (command → first state)
- State transition frequency
- Message delivery success rate
- Container lifecycle duration

### Log Correlation
All logs include `run_id` for correlation:
- `[NATS PUBLISH] ... run {run_id}`
- `[NATS RECEIVE] ... run {run_id}`
- `[WORKER] ... run {run_id}`

## Configuration

### Environment Variables
- `NATS_URL` - NATS server URL (default: nats://localhost:4222)
- `CONTROL_PLANE_URL` - Control plane URL (default: http://localhost:8080)
- `MOCK_MODE` - Enable mock mode for the worker / UI (default: false)
- `MOCK_DOCKER` - Mock Docker container creation in the control-plane (default: false)
- `LLM_PROVIDER` - LLM provider used by workers (`fake`, `ollama`, `openai`, `anthropic`)
- `AGENT_TYPE` - Default worker variant when not supplied by the UI (`specialist`)

### Timeouts
- Container creation: 30s
- Workflow execution: Configurable per run
- NATS message delivery: Automatic retry with exponential backoff
- SSE reconnection: Automatic with Last-Event-ID

## Troubleshooting

### Symptom: No chat.start message received
**Fix:** Verify NATS connection in the agent-service and that `NATSMessaging` is initialized.

### Symptom: Container created but no agent.user.{uid}.events.{rid}.state.* events
**Fix:** Check control-plane NATS publish permissions and that the worker successfully started. Verify the worker is subscribed to `agent.user.{uid}.chat.{rid}.user.events` for incoming commands/events.

### Symptom: run.start command sent but worker doesn't respond
**Fix:** Verify the worker container has `AGENT_TYPE`, `LLM_PROVIDER`, and `PYTHON_MODULE` set correctly and that it subscribed to the correct subject pattern.

### Symptom: Agent events published but UI doesn't update
**Fix:** Check agent-service subscription to `agent.user.*.events.>` and `agent.user.*.chat.*.worker.events`, and verify the SSE stream is being consumed by the Angular `ChatComponent`.

### Symptom: UI shows "Workflow started" but no updates
**Fix:** Check worker logs for execution errors, especially for LangGraph checkpointer or CrewAI project discovery failures.
