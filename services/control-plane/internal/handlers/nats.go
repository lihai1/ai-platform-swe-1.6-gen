package handlers

import (
	"encoding/json"
	"log"

	"github.com/agentic-engineering/control-plane/internal/orchestrator"
	"github.com/agentic-engineering/control-plane/internal/repository"
	"github.com/agentic-engineering/control-plane/internal/service"
	"github.com/nats-io/nats.go"
)

// ChatStartMessage represents a chat start message from NATS
type ChatStartMessage struct {
	MessageID     string `json:"message_id"`
	RunID         string `json:"run_id"`
	RepositoryID  string `json:"repository_id"`
	ProjectID     string `json:"project_id"`
	MockMode      bool   `json:"mock_mode"`
	Timestamp     string `json:"timestamp"`
	SchemaVersion string `json:"schema_version"`
}

// ChatCloseMessage represents a chat close message from NATS
type ChatCloseMessage struct {
	MessageID     string `json:"message_id"`
	RunID         string `json:"run_id"`
	Timestamp     string `json:"timestamp"`
	SchemaVersion string `json:"schema_version"`
}

// HandleChatStart handles chat start messages from NATS
func HandleChatStart(msg *nats.Msg, chatContainerService *service.ChatContainerService, containerManager *orchestrator.Manager, repoRepo *repository.RepositoryRepository, nc *nats.Conn, js nats.JetStreamContext) {
	var chatMsg ChatStartMessage
	if err := json.Unmarshal(msg.Data, &chatMsg); err != nil {
		log.Printf("[NATS RECEIVE] Failed to unmarshal chat start message: %v", err)
		return
	}

	log.Printf("[NATS RECEIVE] Received chat start message on subject: %s", msg.Subject)
	log.Printf("[NATS RECEIVE] Chat start payload: %s", string(msg.Data))
	log.Printf("[NATS RECEIVE] Run ID: %s, Repository ID: %s, Mock Mode: %v", chatMsg.RunID, chatMsg.RepositoryID, chatMsg.MockMode)

	// Get repository details for StartWorker
	repo, err := repoRepo.Get(chatMsg.RepositoryID)
	if err != nil {
		log.Printf("[NATS RECEIVE] Failed to get repository for run %s: %v", chatMsg.RunID, err)
		return
	}

	// Start worker container
	_, err = containerManager.StartWorker(chatMsg.RunID, repo.GitURL, repo.Branch, nil, chatMsg.MockMode)
	if err != nil {
		log.Printf("[NATS RECEIVE] Failed to start worker for run %s: %v", chatMsg.RunID, err)
		return
	}

	log.Printf("[NATS RECEIVE] Successfully started worker container for run %s", chatMsg.RunID)

	// Worker will publish its own ready signal via container-start.sh
	// Control-plane no longer publishes worker ready - worker handles this
	log.Printf("[NATS RECEIVE] Worker container started and will publish ready signal for run %s", chatMsg.RunID)
}

// HandleChatClose handles chat close messages from NATS
func HandleChatClose(msg *nats.Msg, chatContainerService *service.ChatContainerService, containerManager *orchestrator.Manager) {
	var chatMsg ChatCloseMessage
	if err := json.Unmarshal(msg.Data, &chatMsg); err != nil {
		log.Printf("[NATS RECEIVE] Failed to unmarshal chat close message: %v", err)
		return
	}

	log.Printf("[NATS RECEIVE] Received chat close message on subject: %s", msg.Subject)
	log.Printf("[NATS RECEIVE] Chat close payload: %s", string(msg.Data))
	log.Printf("[NATS RECEIVE] Run ID: %s", chatMsg.RunID)

	// Get container info before stopping
	container, err := chatContainerService.GetContainer(chatMsg.RunID)
	if err != nil {
		log.Printf("[NATS RECEIVE] Failed to get container for run %s: %v", chatMsg.RunID, err)
		return
	}

	// Stop and remove worker container
	if container != nil && container.ContainerID != "" {
		log.Printf("[NATS RECEIVE] Stopping worker container for run %s", chatMsg.RunID)
		if err := containerManager.StopWorker(container.ContainerID); err != nil {
			log.Printf("[NATS RECEIVE] Failed to stop worker for run %s: %v", chatMsg.RunID, err)
			return
		}
		log.Printf("[NATS RECEIVE] Successfully stopped worker container for run %s", chatMsg.RunID)
	}

	// Clean up database record
	if err := chatContainerService.RemoveContainer(chatMsg.RunID); err != nil {
		log.Printf("[NATS RECEIVE] Failed to remove container record for run %s: %v", chatMsg.RunID, err)
		return
	}

	log.Printf("[NATS RECEIVE] Successfully terminated worker for run %s", chatMsg.RunID)
}
