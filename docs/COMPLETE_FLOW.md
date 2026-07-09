# Complete Chat-to-Agent Flow Documentation

## Overview
This document describes the complete flow from UI start page to agent execution, including all NATS messages, service interactions, and state transitions.

> **Subject reference:** The authoritative, verified NATS subject list is in
> [NATS Subject Patterns](#nats-subject-patterns) below. Note that **agent
> lifecycle events are published on `agent.events.{run_id}.{event_type}`** (the
> `AGENT_EVENTS` JetStream stream), *not* on `agent.chat.*`. The step-by-step
> narrative that follows is illustrative; some inline code snippets are
> simplified. Inline `file:line` references may drift as the code evolves.

## Architecture Components

### Services
1. **Angular UI** (port 4200) - User interface
2. **Python Agent Service** (port 8000) - ChatKit and workflow orchestration
3. **Go Control Plane** (port 8080) - Container management and repository access
4. **NATS JetStream** (port 4222) - Message broker
5. **PostgreSQL** (port 5432) - Data persistence
6. **Agent Worker** - Executes LangGraph workflows (runs in container or as separate process)

### Key Tables
- `chatkit_threads` - Chat thread persistence
- `chatkit_items` - Chat messages
- `chat_containers` - Container lifecycle tracking
- `agent_runs` - Workflow execution tracking
- `agent_events` - Event history

## Complete Flow

### Step 1: User Starts New Project
**Location:** `apps/web/src/app/projects/projects.component.ts`

1. User navigates to `/` (projects page)
2. UI loads projects from control plane: `GET /api/v1/projects`
3. User clicks "New Project" or selects existing project
4. User optionally selects GitHub repository (or none)
5. User clicks "Start Chat"

**Navigation:** `router.navigate(['/chat'], { queryParams: { project_id, repository_id } })`

### Step 2: Chat Window Opens
**Location:** `apps/web/src/app/chat/chat.component.ts`

1. Angular navigates to `/chat?project_id=X&repository_id=Y`
2. ChatComponent loads ChatKit client script from `/assets/chatkit-client.js`
3. ChatKit initializes with:
   - `apiUrl`: Python service endpoint
   - `projectId`: From query params
   - `repositoryId`: From query params (optional)
   - `triggerWorkflow`: Checkbox state

### Step 3: User Sends First Message
**Location:** ChatKit client → `services/agent-service/internal/chatkit/router.py`

1. User types message and clicks send
2. ChatKit sends: `POST /api/chatkit/`
   ```json
   {
     "message": "Add a login feature",
     "repository_id": "repo-123",
     "project_id": "proj-456",
     "trigger_workflow": true,
     "mock_mode": false
   }
   ```

### Step 4: Python Service Starts Chat
**Location:** `services/agent-service/internal/chatkit/router.py:115-162`

**Actions:**
1. Create or get thread ID
2. Save user message to database

**NATS Message 1 - Chat Start:**
```python
# Subject: chat.start
await nats.publish_chat_start(
    chat_id=thread_id,
    repository_id=repository_id,
    project_id=project_id,
    mock_mode=False
)
```

**Log Output:**
```
[NATS PUBLISH] Publishing chat start {message_id} to subject: chat.start
[NATS PUBLISH] Chat start payload: {...}
```

3. Subscribe to agent events for this chat:
```python
await nats.subscribe_to_chat_events(
    chat_id=thread_id,
    event_handler=handle_chat_event
)
```

**Log Output:**
```
Subscribed to agent events for chat {chat_id}
```

### Step 5: Control Plane Creates Container
**Location:** `services/control-plane/cmd/server/main.go:112-221`

**NATS Subscriber:** `chat.start`

**Actions:**
1. Receive chat.start message
   ```
   [NATS RECEIVE] Received chat start message on subject: chat.start
   [NATS RECEIVE] Chat start payload: {...}
   [NATS RECEIVE] Chat ID: {chat_id}, Repository ID: {repo_id}, Mock Mode: false
   ```

2. Create Docker container:
   ```go
   chatContainerService.CreateContainer(chatID, repositoryID, mockMode)
   ```
   - Container includes: CHAT_ID, REPOSITORY_URL, GIT credentials
   - Container clones repository
   - Container starts worker process

3. Save ChatContainer record to database

**NATS Message 2 - Agent Chat Start:**
```go
// Subject: agent.chat.{chat_id}.start
subject := fmt.Sprintf("agent.chat.%s.start", chatID)
nc.Publish(subject, agentStartData)
```

**Log Output:**
```
[NATS PUBLISH] Publishing agent start message to subject: agent.chat.{chat_id}.start
[NATS PUBLISH] Agent start payload: {...}
[NATS PUBLISH] Successfully published agent start message for chat {chat_id}
```

### Step 6: Python Service Triggers Workflow
**Location:** `services/agent-service/internal/chatkit/router.py:92-113`

**Condition:** `trigger_workflow=true` and `project_id` and `repository_id` provided

**NATS Message 3 - Run Start Command:**
```python
# Subject: agent.chat.{chat_id}.run.start
await nats.publish_command(
    command_type="run.start",
    run_id=chat_id,
    chat_id=chat_id,
    payload={
        "user_id": user_id,
        "project_id": project_id,
        "repository_id": repository_id,
        "task": message,
        "chatkit_thread_id": thread_id,
        "max_repair_count": 2
    }
)
```

**Log Output:**
```
[NATS PUBLISH] Publishing command {message_id} to subject: agent.chat.{chat_id}.run.start
[NATS PUBLISH] Command payload: {...}
[NATS PUBLISH] Successfully published command {message_id} to agent.chat.{chat_id}.run.start
```

**Response to UI:**
```
data: {"content": "Workflow started. Processing your request...", "thread_id": "...", "workflow_triggered": true}
```

### Step 7: Agent Worker Receives Command
**Location:** `services/agent-service/app/worker.py:41-93`

**NATS Subscriber:** `agent.chat.{chat_id}.>` (all messages for this chat)

**Actions:**
1. Receive run.start command
   ```
   [NATS RECEIVE] Received command on subject: agent.chat.{chat_id}.run.start
   [NATS RECEIVE] Command payload: {...}
   [WORKER] Received command run.start for chat {chat_id}
   [WORKER] Command payload: {...}
   ```

2. Check idempotency (skip if already processed)

3. Execute workflow:
   ```python
   result = await create_run({
       "run_id": chat_id,
       "user_id": payload["user_id"],
       "project_id": payload["project_id"],
       "repository_id": payload["repository_id"],
       "task": payload["task"],
       "max_repair_count": 2,
       "mock_mode": False
   }, checkpointer)
   ```

4. Acknowledge NATS message
   ```
   [NATS RECEIVE] Successfully processed and acked command {message_id}
   ```

### Step 8: Orchestrator Agent Executes in Sequence
**Location:** `services/agent-service/internal/workflow/graph.py`

**State Transitions:**
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

**For Each State Transition:**

**NATS Message 4+ - Agent State Updates:**
```python
# Subject: agent.chat.{chat_id}.{state}
await nats.publish_event(
    event_type=state.lower(),
    run_id=chat_id,
    chat_id=chat_id,
    payload={
        "state": state,
        "agent": agent_name,
        "data": {...}
    }
)
```

**Log Output:**
```
[NATS PUBLISH] Publishing event {message_id} to subject: agent.chat.{chat_id}.scouting
[NATS PUBLISH] Event payload: {...}
[NATS PUBLISH] Successfully published event {message_id} to agent.chat.{chat_id}.scouting
```

### Step 9: Python Service Receives Agent Events
**Location:** `services/agent-service/internal/chatkit/router.py:56-60`

**NATS Subscriber:** `agent.chat.{chat_id}.>`

**Actions:**
1. Receive event
   ```
   [NATS RECEIVE] Received event on subject: agent.chat.{chat_id}.scouting
   [NATS RECEIVE] Event payload: {...}
   [NATS RECEIVE] Received agent event for chat {chat_id}: {...}
   ```

2. Update chat state in database

3. Forward to UI via SSE (Server-Sent Events)

### Step 10: UI Displays Agent Updates
**Location:** ChatKit client (SSE stream)

**UI Receives:**
```
data: {"state": "scouting", "agent": "repo-scout", "message": "Analyzing repository structure..."}
data: {"state": "planning", "agent": "solution-planner", "message": "Creating implementation plan..."}
data: {"state": "implementing", "agent": "go-developer", "message": "Writing code..."}
...
```

**User Observes:**
- Real-time agent activity in chat window
- State transitions and progress updates
- Agent messages and artifacts

### Step 11: Human Intervention (if needed)
**Trigger:** Protected action (push, PR, network access, etc.)

**State:** WAITING_APPROVAL

**NATS Message - Approval Request:**
```python
# Subject: agent.chat.{chat_id}.waiting_approval
await nats.publish_event(
    event_type="waiting_approval",
    run_id=chat_id,
    chat_id=chat_id,
    payload={
        "approval_id": approval_id,
        "action": "push_code",
        "reason": "Push to main branch requires approval"
    }
)
```

**UI Shows:** Approval dialog

**User Action:** Approve or Reject

**API Call:** `POST /api/v1/runs/{run_id}/approvals/{approval_id}/approve`

**NATS Message - Resume Command:**
```python
# Subject: agent.chat.{chat_id}.run.resume
await nats.publish_command(
    command_type="run.resume",
    run_id=chat_id,
    chat_id=chat_id,
    payload={
        "approval_id": approval_id,
        "decision": "approved"
    }
)
```

**Workflow:** Resumes from checkpoint

### Step 12: Workflow Completion
**Final State:** COMPLETED, FAILED, CANCELLED, or BUDGET_EXCEEDED

**NATS Message - Final Event:**
```python
# Subject: agent.chat.{chat_id}.completed
await nats.publish_event(
    event_type="completed",
    run_id=chat_id,
    chat_id=chat_id,
    payload={
        "status": "completed",
        "artifacts": [...],
        "summary": "..."
    }
)
```

**Worker Log:**
```
[WORKER] Run for chat {chat_id} completed with status completed
```

**UI Shows:** Final status and artifacts

### Step 13: Chat Termination (Optional)
**Trigger:** User closes chat

**API Call:** `POST /api/chatkit/close/{thread_id}`

**NATS Message - Chat Close:**
```python
# Subject: chat.close
await nats.publish_chat_close(chat_id=thread_id)
```

**Log Output:**
```
[NATS PUBLISH] Publishing chat close {message_id} to subject: chat.close
[NATS PUBLISH] Chat close payload: {...}
```

**Control Plane Actions:**
1. Receive chat.close message
   ```
   [NATS RECEIVE] Received chat close message on subject: chat.close
   [NATS RECEIVE] Chat close payload: {...}
   [NATS RECEIVE] Chat ID: {chat_id}
   ```

2. Stop container
3. Remove container
4. Update ChatContainer status
   ```
   [NATS RECEIVE] Successfully terminated container for chat {chat_id}
   ```

## NATS Subject Patterns

### Lifecycle Subjects (plain NATS, consumed by the Go control plane)
- `chat.start` - Trigger worker container creation
- `chat.close` - Trigger worker container termination

### Command / Orchestration Subjects (JetStream stream `AGENT_COMMANDS`, subjects `agent.chat.>`)
- `agent.chat.{run_id}.user.events` - Orchestration commands (`command_type`: `run.start`, `run.cancel`, `run.resume`); the worker subscribes here.
- `agent.chat.{run_id}.{command_type}` - Generic per-run command subject used by `publish_command`.

### Event Subjects (JetStream stream `AGENT_EVENTS`, subjects `agent.events.>`)
- `agent.events.{run_id}.{event_type}` - All agent lifecycle/state events. `event_type` is one of:
  - `created`, `preparing_workspace`, `scouting`, `planning`, `designing`
  - `implementing`, `testing`, `reviewing`, `verifying`, `repairing`
  - `waiting_approval`, `completed`, `failed`, `cancelled`, `budget_exceeded`
  - plus `started` / `progress` (emitted by the mock worker)

### Subscription Patterns
- `agent.events.{run_id}.>` - All events for one run (agent-service `NatsBridge` + `subscribe_to_events`).
- `agent.events.>` - All events across all runs (agent-service startup subscription for DB persistence).
- `agent.chat.{run_id}.>` - All chat-scoped messages for one run.
- `agent.chat.>.user.events` - Worker user events fan-in (agent-service).

## Error Handling

### No Response After 30 Seconds
**Possible Causes:**
1. NATS not running
2. Control plane not subscribed to chat.start
3. Container creation failed
4. Worker not running or not subscribed
5. Workflow execution error

**Debug Steps:**
1. Check NATS connection: `nc.IsConnected()`
2. Check control plane logs for chat.start receipt
3. Check container status: `docker ps`
4. Check worker logs for command receipt
5. Check PostgreSQL for run record

### Container Creation Fails
**Symptoms:** No agent.chat.{chat_id}.start message published

**Debug:**
- Check control plane logs
- Check Docker daemon status
- Check repository access credentials

### Workflow Doesn't Start
**Symptoms:** Worker receives command but doesn't execute

**Debug:**
- Check worker logs for errors
- Check PostgreSQL connection
- Check LangGraph checkpointer setup

## Testing

### E2E Test Flow
1. Navigate to projects page
2. Create or select project
3. Optionally add GitHub repository
4. Click "Start Chat"
5. Verify chat window opens
6. Send message with trigger_workflow=true
7. Wait for first agent update (max 30s)
8. Verify agent state appears in chat
9. Verify subsequent updates appear

### Mock Mode
Set `mock_mode=true` to skip:
- Actual container creation
- Real repository cloning
- LLM API calls

## Monitoring

### Key Metrics
- Chat start latency (UI → container ready)
- Workflow trigger latency (command → first state)
- State transition frequency
- Message delivery success rate
- Container lifecycle duration

### Log Correlation
All logs include `chat_id` for correlation:
- `[NATS PUBLISH] ... chat {chat_id}`
- `[NATS RECEIVE] ... chat {chat_id}`
- `[WORKER] ... chat {chat_id}`

## Configuration

### Environment Variables
- `NATS_URL` - NATS server URL (default: nats://localhost:4222)
- `CONTROL_PLANE_URL` - Control plane URL (default: http://localhost:8080)
- `MOCK_MODE` - Enable mock mode (default: false)
- `MOCK_DOCKER` - Mock Docker operations (default: false)

### Timeouts
- Container creation: 30s
- Workflow execution: Configurable per run
- NATS message delivery: Automatic retry with exponential backoff
- SSE reconnection: Automatic with Last-Event-ID

## Troubleshooting

### Symptom: No chat.start message received
**Fix:** Verify NATS connection in Python service

### Symptom: Container created but no agent.chat.{chat_id}.start
**Fix:** Check control plane NATS publish permissions

### Symptom: run.start command sent but worker doesn't respond
**Fix:** Verify worker is subscribed to correct subject pattern

### Symptom: Agent events published but UI doesn't update
**Fix:** Check Python service subscription to agent.chat.{chat_id}.>

### Symptom: UI shows "Workflow started" but no updates
**Fix:** Check worker logs for execution errors
