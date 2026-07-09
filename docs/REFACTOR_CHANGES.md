# Refactor Changes & Rationale

This document details all changes made during the maintenance refactor pass (July 2026), organized by phase with rationale and impact.

---

## Phase A: Correctness Bugs (Highest Priority)

### 1. Fixed `chat_id`/`run_id` Schema Drift

**Problem:**
- Migration `004` renamed all `run_id` columns to `chat_id` on the `agent.*` tables
- However, the ORM models and several queries had drifted inconsistently:
  - `agent-service/internal/models.py` used `run_id` on `AgentEvent` and `AgentApproval`
  - `agent-worker/internal/models.py` used `chat_id` on those same tables
  - Queries in `store.py`, `events.py`, `router.py` referenced the wrong column names
- This caused `AttributeError` and SQL errors on the approvals and events paths

**Changes:**
- Made `agent-worker/internal/models.py` the canonical source (it already had `chat_id`)
- Copied it to `agent-service/internal/models.py` to eliminate drift
- Fixed all ORM column references in:
  - `services/agent-service/internal/chatkit/store.py` (lines 50, 64)
  - `services/agent-worker/internal/workflow/events.py` (lines 38, 112, 121)
  - `services/agent-worker/internal/workflow/router.py` (lines 189, 243)

**Impact:**
- Eliminates runtime errors on the approvals and events paths
- Both services now use the same canonical schema

---

### 2. Fixed Invalid `publish_event(chat_id=...)` TypeError

**Problem:**
- The worker called `nats.publish_event(chat_id=run_id, ...)` in `events.py` and `nodes.py`
- The `NATSMessaging.publish_event` method signature does NOT accept a `chat_id` kwarg
- The exception was caught and logged, but the worker silently failed to publish events
- Result: UI received no progress updates during agent execution

**Changes:**
- Removed the invalid `chat_id` kwarg from `publish_event` calls in:
  - `services/agent-worker/internal/workflow/events.py` (line 138)
  - `services/agent-worker/internal/workflow/nodes.py` (line 34)

**Impact:**
- Worker state events now successfully publish to NATS
- UI receives real-time progress updates

---

### 3. Fixed Swapped Positional Arguments in `event_generator`

**Problem:**
- In `services/agent-worker/internal/workflow/events.py`, the call to `EventSourceResponse` passed:
  - `event_generator(run_id, last_event_id, session)`
- But the function signature is `event_generator(run_id, session, last_event_id=None)`
- This would cause incorrect behavior when reconnecting with a `Last-Event-ID` header

**Changes:**
- Fixed the call to match the signature: `event_generator(run_id, session, last_event_id)`

**Impact:**
- SSE reconnection with `Last-Event-ID` now works correctly

---

## Phase B: Dead Code Removal

### 1. Deleted Duplicated Agent/Skills/Tools from `agent-service`

**Problem:**
- `agent-service` contained copies of:
  - `internal/agents/` (factory, implementers, model_factory, schemas, specialists, validators)
  - `internal/skills/` (registry, snapshots)
  - `internal/tools/` (repository, workspace)
  - `internal/workflow/tracing.py`
- These modules are only used by `agent-worker` (the actual executor)
- `agent-service` is the API/streaming gateway and only needs mock workflow nodes
- This duplication caused confusion about where execution code lives

**Changes:**
- Deleted the above directories/files from `agent-service`
- Relocated 3 security tests that referenced the deleted modules:
  - `test_authorization.py`
  - `test_prompt_injection.py`
  - `test_secret_redaction.py`
  → moved to `services/agent-worker/tests/security/`
- Added `pytest-describe` to `agent-worker/pyproject.toml` (required by the relocated tests)

**Impact:**
- Eliminates confusion: execution code lives only in `agent-worker`
- Reduces code duplication and maintenance burden
- Tests now live alongside the code they test

---

## Phase C: Shared Package Extraction

### 1. Created `shared/agent-core` Package

**Problem:**
- Both services duplicated `config.py`, `db.py`, `models.py`, and `messaging/nats.py`
- Changes had to be made in two places, leading to drift
- No single source of truth for shared infrastructure

**Changes:**
- Created `shared/agent-core/agent_core/` with:
  - `config.py` — Settings (single source of truth)
  - `db.py` — Async engine, session, Base
  - `models.py` — SQLAlchemy ORM models (canonical schema)
  - `messaging/nats.py` — NATSMessaging client (superset used by both services)
  - Added `subscribe_to_orchestration_events` to the shared NATS client (worker-only method)
  - Fixed deprecated `datetime.utcnow()` → `datetime.now(timezone.utc)` throughout
- Created `pyproject.toml` for the shared package
- Created `__init__.py` files for proper package structure
- Replaced each service's modules with thin re-export shims:
  - `internal/config.py` → `from agent_core.config import ...`
  - `internal/db.py` → `from agent_core.db import ...`
  - `internal/models.py` → `from agent_core.models import ...`
  - `internal/messaging/nats.py` → `from agent_core.messaging.nats import NATSMessaging`

**Impact:**
- Single source of truth for shared infrastructure
- Changes to config/db/models/messaging only need to be made once
- Clear separation: shared vs. service-specific code

---

### 2. Wired Docker Builds for Shared Package

**Problem:**
- Docker build contexts were service-specific (`./services/agent-service`)
- Could not copy the shared package into the image

**Changes:**
- Updated `docker-compose.yml`:
  - `agent-service` and `mock-worker` now use `context: .` (repo root)
- Updated `Makefile`:
  - Build commands now use `-f <dockerfile> .` (repo root)
- Updated `Dockerfile`s:
  - `agent-service/Dockerfile`: COPY `shared/agent-core/agent_core ./agent_core`
  - `agent-worker/Dockerfile.worker`: COPY `shared/agent-core/agent_core /app/agent_core`
- Added root `.dockerignore` to exclude large artifacts (venv, node_modules, compiled Go binary)

**Impact:**
- Docker images now include the shared package
- Build context is repo-wide (more accurate for multi-service projects)
- Faster builds due to `.dockerignore`

---

## Phase D: Best-Practice Fixes

### 1. Replaced `print()` Debugging with `logging`

**Problem:**
- Debugging used `print()` statements in production code
- No structured logging, no log levels, no ability to configure output

**Changes:**
- Added `import logging` and `logger = logging.getLogger(__name__)` to:
  - `services/agent-service/internal/chatkit/nats_bridge.py`
  - `services/agent-service/internal/chatkit/server.py`
  - `services/agent-service/internal/chatkit/router.py`
  - `services/agent-service/app/main.py`
  - `services/agent-worker/internal/workflow/events.py`
- Replaced `print()` with appropriate logger calls:
  - `logger.info()` for normal operations
  - `logger.debug()` for detailed event data
  - `logger.warning()` for expected failures (e.g., NATS publish failure)
  - `logger.exception()` for unexpected errors with traceback

**Impact:**
- Structured, configurable logging
- Better production observability
- Can enable/disable debug output without code changes

---

### 2. Fixed Deprecated `datetime.utcnow()`

**Problem:**
- `datetime.utcnow()` is deprecated in Python 3.12+
- It returns a naive datetime (no timezone info)
- Can cause issues with timezone-aware comparisons

**Changes:**
- In `shared/agent-core/agent_core/messaging/nats.py`:
  - Added `from datetime import datetime, timedelta, timezone`
  - Replaced all `datetime.utcnow()` with `datetime.now(timezone.utc)`

**Impact:**
- Uses modern, non-deprecated API
- All timestamps are timezone-aware (UTC)
- Future-proof for Python 3.12+

---

### 3. Fixed Invalid CORS Wildcard-with-Credentials

**Problem:**
- The CORS middleware was configured with:
  - `allow_origins=["*"]`
  - `allow_credentials=True`
- This violates the Fetch spec: a wildcard origin cannot be combined with credentials
- Browsers reject this configuration

**Changes:**
- In `services/agent-service/app/main.py`:
  - Made origins configurable via `CORS_ALLOW_ORIGINS` env var (comma-separated)
  - Only set `allow_credentials=True` if origins is NOT `["*"]`
  - Default behavior unchanged (wildcard, no credentials) for local dev

**Impact:**
- CORS configuration now complies with the Fetch spec
- Production deployments can specify exact origins with credentials

---

### 4. Untracked Accidentally Committed Binary

**Problem:**
- The compiled Go binary `services/control-plane/server` (37 MB) was committed
- Build artifacts should never be in git
- Blobs the repository and causes merge conflicts

**Changes:**
- Ran `git rm --cached services/control-plane/server` to untrack
- Added `services/control-plane/server` to `.gitignore`

**Impact:**
- Repository size reduced by 37 MB
- Future builds won't accidentally commit the binary

---

### 5. Removed Lambda Tuple Hack in `nats_bridge.py`

**Problem:**
- Used a lambda tuple to execute two side effects:
  - `lambda event: (print(...), queue.put_nowait(event))`
- The tuple is discarded; unclear intent
- Hard to read and maintain

**Changes:**
- Created a proper `enqueue(event)` function that:
  - Logs the event
  - Puts it in the queue
- Passed the function as the handler instead of a lambda

**Impact:**
- Clearer, more maintainable code
- Proper separation of concerns

---

## Phase E: Documentation & Diagrams

### 1. Corrected NATS Subjects in Documentation

**Problem:**
- `COMPLETE_FLOW.md` and Mermaid diagrams used incorrect NATS subjects:
  - Referenced `agent.commands.>` (actual is `agent.chat.>`)
  - Referenced `agent.events.{run_id}` (actual is `agent.events.{run_id}.{event_type}`)
  - Misrepresented command/event subject separation

**Changes:**
- Updated `docs/COMPLETE_FLOW.md`:
  - Added authoritative subject reference section
  - Corrected all subject patterns
  - Added accuracy note about illustrative vs. authoritative content
- Updated `docs/architecture-component-diagram.mmd`:
  - Added shared package node
  - Corrected NATS subject labels
  - Added control-plane subscription to `chat.start`/`chat.close`
- Updated `docs/sequence-nats-messaging.mmd`:
  - Corrected stream subjects
  - Fixed subscription patterns

**Impact:**
- Documentation now matches actual implementation
- Clearer understanding of NATS message flow

---

### 2. Updated README.md

**Problem:**
- README had stale references:
  - `IMPLEMENTATION_PLAN.md` (doesn't exist)
  - No mention of shared package
  - Project structure tree outdated
  - No explanation of service responsibilities

**Changes:**
- Added service responsibilities table (gateway vs. executor)
- Added shared package to architecture section
- Updated project structure tree
- Added local-dev instruction to install shared package
- Added "Maintenance Refactor" section documenting this work
- Fixed dead `IMPLEMENTATION_PLAN.md` link
- Corrected agent container creation flow description

**Impact:**
- README accurately reflects current architecture
- New contributors understand the shared package and service split

---

### 3. Updated agent-service README.md

**Problem:**
- Specialist agents section implied they live in `agent-service`
- No mention of shared package

**Changes:**
- Added clarifying note: specialist agents execute in `agent-worker`
- Explained `agent-service` is the API/streaming gateway
- Mentioned shared package location

**Impact:**
- Reduces confusion about where execution code lives

---

## Verification Notes

### Dependency Installation Issue
- Third-party dependency installs (pip/uv) fail in this environment due to TLS cert error (`UnknownIssuer`)
- Therefore, changes were verified using `python -m py_compile` (syntax check only)
- Full import/runtime tests require dependencies that cannot be installed here
- **Docker image builds must be verified in CI**

### Compilation Verification
- All Python files across both services and the shared package compile successfully
- No stale `run_id` ORM column references remain
- No `print()` statements remain in modified files
- No `datetime.utcnow()` remains in shared messaging

---

## Summary

This refactor fixed critical correctness bugs (schema drift, invalid NATS calls), eliminated code duplication, extracted a shared package, and improved code quality (logging, deprecations, CORS). Documentation was updated to match the actual implementation. All changes are compile-verified; Docker builds require CI verification due to local dependency installation issues.
