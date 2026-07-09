package integration_test

import (
	"encoding/json"
	"testing"
	"time"
)

func TestContainerLifecyclePublishStart(t *testing.T) {
	nc := getNATSConnection(t)
	defer nc.Close()

	subject := "agent.chat.test-run-123.run.start"

	// Publish agent start message
	message := map[string]interface{}{
		"message_id":   "test-msg-789",
		"command_type": "run.start",
		"run_id":       "test-run-123",
		"payload": map[string]interface{}{
			"user_id":       "test-user-123",
			"project_id":    "test-project-123",
			"repository_id": "test-repo-123",
			"task":          "Test task",
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

func TestContainerLifecyclePublishCancel(t *testing.T) {
	nc := getNATSConnection(t)
	defer nc.Close()

	subject := "agent.chat.test-run-123.run.cancel"

	// Publish cancel message
	message := map[string]interface{}{
		"message_id":     "test-msg-790",
		"command_type":   "run.cancel",
		"run_id":         "test-run-123",
		"payload":        map[string]interface{}{},
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

func TestContainerLifecycleFullFlow(t *testing.T) {
	nc := getNATSConnection(t)
	defer nc.Close()

	runID := "test-run-lifecycle-123"
	startSubject := "agent.chat." + runID + ".run.start"
	cancelSubject := "agent.chat." + runID + ".run.cancel"

	// Publish start message
	startMessage := map[string]interface{}{
		"message_id":     "test-msg-start",
		"command_type":   "run.start",
		"run_id":         runID,
		"payload":        map[string]interface{}{},
		"timestamp":      time.Now().UTC().Format(time.RFC3339),
		"schema_version": "1.0",
	}
	startBytes, err := json.Marshal(startMessage)
	if err != nil {
		t.Fatalf("Failed to marshal message: %v", err)
	}

	err = nc.Publish(startSubject, startBytes)
	if err != nil {
		t.Fatalf("Failed to publish message: %v", err)
	}

	// Wait a bit for message to be processed
	time.Sleep(100 * time.Millisecond)

	// Publish cancel message
	cancelMessage := map[string]interface{}{
		"message_id":     "test-msg-cancel",
		"command_type":   "run.cancel",
		"run_id":         runID,
		"payload":        map[string]interface{}{},
		"timestamp":      time.Now().UTC().Format(time.RFC3339),
		"schema_version": "1.0",
	}
	cancelBytes, err := json.Marshal(cancelMessage)
	if err != nil {
		t.Fatalf("Failed to marshal message: %v", err)
	}

	err = nc.Publish(cancelSubject, cancelBytes)
	if err != nil {
		t.Fatalf("Failed to publish message: %v", err)
	}

	// Wait a bit for message to be processed
	time.Sleep(100 * time.Millisecond)
}
