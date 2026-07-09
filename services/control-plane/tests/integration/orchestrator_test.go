package integration_test

import (
	"encoding/json"
	"testing"
	"time"
)

func TestOrchestratorWorkerReady(t *testing.T) {
	nc := getNATSConnection(t)
	defer nc.Close()

	subject := "agent.chat.test-run-123.worker.ready"

	// Publish worker ready message
	message := map[string]interface{}{
		"message_id":     "test-msg-worker-ready",
		"run_id":         "test-run-123",
		"status":         "ready",
		"timestamp":      time.Now().UTC().Format(time.RFC3339),
		"schema_version": "1.0",
	}
	messageBytes, err := json.Marshal(message)
	if err != nil {
		t.Fatalf("Failed to marshal message: %v", err)
	}

	err = nc.Publish(subject, messageBytes)
	if err != nil {
		t.Fatalf("Failed to publish message: %v", err)
	}

	// Wait a bit for message to be processed
	time.Sleep(100 * time.Millisecond)
}

func TestOrchestratorCommandReception(t *testing.T) {
	nc := getNATSConnection(t)
	defer nc.Close()

	subject := "agent.chat.test-run-orch-456.run.start"

	// Publish orchestrator command
	message := map[string]interface{}{
		"message_id":   "test-msg-orch",
		"command_type": "run.start",
		"run_id":       "test-run-orch-456",
		"payload": map[string]interface{}{
			"user_id":       "test-user-456",
			"project_id":    "test-project-456",
			"repository_id": "test-repo-456",
			"task":          "Orchestrator test task",
		},
		"timestamp":      time.Now().UTC().Format(time.RFC3339),
		"schema_version": "1.0",
	}
	messageBytes, err := json.Marshal(message)
	if err != nil {
		t.Fatalf("Failed to marshal message: %v", err)
	}

	err = nc.Publish(subject, messageBytes)
	if err != nil {
		t.Fatalf("Failed to publish message: %v", err)
	}

	// Wait a bit for message to be processed
	time.Sleep(100 * time.Millisecond)
}
