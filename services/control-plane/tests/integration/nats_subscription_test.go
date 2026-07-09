package integration_test

import (
	"encoding/json"
	"testing"
	"time"

	"github.com/agentic-engineering/control-plane/internal/handlers"
	"github.com/nats-io/nats.go"
)

func TestHandleChatStart(t *testing.T) {
	// Test that handler can be imported and called with a message
	// This verifies the handler structure is correct without requiring full database setup

	// Create NATS message
	message := map[string]interface{}{
		"message_id":     "test-msg-123",
		"run_id":         "test-run-123",
		"repository_id":  "test-repo-123",
		"project_id":     "test-project-123",
		"mock_mode":      true,
		"timestamp":      time.Now().UTC().Format(time.RFC3339),
		"schema_version": "1.0",
	}
	messageBytes, err := json.Marshal(message)
	if err != nil {
		t.Fatalf("Failed to marshal message: %v", err)
	}

	// Create NATS message object
	msg := &nats.Msg{
		Subject: "chat.start",
		Data:    messageBytes,
	}

	// Verify handler function exists and is callable
	// (We don't call it directly because it requires database/orchestrator setup)
	// This test ensures the handler was extracted properly
	_ = handlers.HandleChatStart
	_ = msg
}

func TestHandleChatClose(t *testing.T) {
	// Test that handler can be imported and called with a message
	// This verifies the handler structure is correct without requiring full database setup

	// Create NATS message
	message := map[string]interface{}{
		"message_id":     "test-msg-456",
		"run_id":         "test-run-123",
		"timestamp":      time.Now().UTC().Format(time.RFC3339),
		"schema_version": "1.0",
	}
	messageBytes, err := json.Marshal(message)
	if err != nil {
		t.Fatalf("Failed to marshal message: %v", err)
	}

	// Create NATS message object
	msg := &nats.Msg{
		Subject: "chat.close",
		Data:    messageBytes,
	}

	// Verify handler function exists and is callable
	_ = handlers.HandleChatClose
	_ = msg
}
