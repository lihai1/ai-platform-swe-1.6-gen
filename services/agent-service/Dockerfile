FROM python:3.12-slim

WORKDIR /app

RUN pip install uv

# Copy shared package and install it first
COPY ./shared /tmp/shared
RUN pip install /tmp/shared && rm -rf /tmp/shared

COPY ./services/agent-service ./
RUN uv pip install --system -r pyproject.toml

# Install pytest for integration tests
RUN pip install pytest pytest-asyncio



EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
