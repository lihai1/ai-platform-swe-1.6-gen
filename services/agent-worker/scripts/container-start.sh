#!/bin/bash
set -e

echo "Starting agent orchestrator container..."

# Get environment variables
CHAT_ID="${CHAT_ID}"
REPOSITORY_URL="${REPOSITORY_URL}"
BRANCH="${BRANCH:-main}"
GIT_USERNAME="${GIT_USERNAME:-}"
GIT_TOKEN="${GIT_TOKEN:-}"
NATS_URL="${NATS_URL:-nats://localhost:4222}"
MOCK_MODE="${MOCK_MODE:-false}"

if [ -z "$CHAT_ID" ]; then
    echo "Error: CHAT_ID environment variable is required"
    exit 1
fi

echo "Chat ID: $CHAT_ID"
echo "Repository URL: $REPOSITORY_URL"
echo "Branch: $BRANCH"
echo "NATS URL: $NATS_URL"
echo "Mock Mode: $MOCK_MODE"

# Clone repository to workspace (or use mock repository)
echo "Setting up workspace..."
cd /workspace

if [ "$MOCK_MODE" = "true" ]; then
    echo "Mock mode enabled - creating mock repository structure..."
    # Create a simple mock repository structure
    mkdir -p /workspace/src
    cat > /workspace/README.md << 'EOF'
# Mock Repository

This is a mock repository for testing purposes.
EOF
    cat > /workspace/src/main.go << 'EOF'
package main

import "fmt"

func main() {
    fmt.Println("Hello, World!")
}
EOF
    cat > /workspace/go.mod << 'EOF'
module mock-repo

go 1.21
EOF
    git init
    git config user.email "mock@example.com"
    git config user.name "Mock User"
    git add .
    git commit -m "Initial commit"
    echo "Mock repository created successfully"
else
    if [ -z "$REPOSITORY_URL" ]; then
        echo "Error: REPOSITORY_URL environment variable is required in non-mock mode"
        exit 1
    fi

    # Configure git credentials if provided
    if [ -n "$GIT_USERNAME" ] && [ -n "$GIT_TOKEN" ]; then
        echo "Configuring git credentials..."
        git config --global credential.helper store
        echo "https://${GIT_USERNAME}:${GIT_TOKEN}@github.com" > ~/.git-credentials
    fi

    # Clone the repository
    if [ -d "/workspace/.git" ]; then
        echo "Repository already exists, pulling latest changes..."
        git fetch origin
        git checkout "$BRANCH"
        git pull origin "$BRANCH"
    else
        echo "Cloning repository..."
        git clone -b "$BRANCH" "$REPOSITORY_URL" /workspace
    fi

    echo "Repository cloned successfully"
fi

# Start the worker process
echo "Starting worker for chat $CHAT_ID..."
export CHAT_ID="$CHAT_ID"
export NATS_URL="$NATS_URL"
export MOCK_MODE="$MOCK_MODE"

# Run the worker
python -m app.worker --chat-id "$CHAT_ID"
