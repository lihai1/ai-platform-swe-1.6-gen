# NOTE: build context is the repository root (see docker-compose.yml / Makefile)
# so that the shared agent_core package can be copied into the image.
FROM python:3.12-slim

WORKDIR /app

RUN pip install uv

COPY services/agent-service/pyproject.toml ./
RUN uv pip install --system -r pyproject.toml

# Shared core package (single source of truth for config/db/models/messaging).
# Placed on the import path via /app.
COPY shared/agent-core/agent_core ./agent_core

COPY services/agent-service/ .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
