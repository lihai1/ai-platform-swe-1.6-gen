package handlers

import (
	"encoding/json"
	"errors"
	"log"

	internalnats "github.com/agentic-engineering/control-plane/internal/nats"
	"github.com/agentic-engineering/control-plane/internal/orchestrator"
	"github.com/agentic-engineering/control-plane/internal/repository"
	"github.com/agentic-engineering/control-plane/internal/service"
	"github.com/nats-io/nats.go"
)

// ChatStartMessage represents a chat start message from NATS
type ChatStartMessage struct {
	MessageID      string  `json:"message_id"`
	RunID          string  `json:"run_id"`
	RepositoryID   string  `json:"repository_id"`
	ProjectID      string  `json:"project_id"`
	UserID         string  `json:"user_id"`
	Task           string  `json:"task"`
	MockMode       bool    `json:"mock_mode"`
	AgentType      string  `json:"agent_type"`   // "multi-agent", "single-agent", "crewai", or "crewai-expert"
	LLMProvider    string  `json:"llm_provider"` // "fake", "ollama", "openai", "anthropic"
	ModelName      string  `json:"model_name"`   // Model name for the LLM provider
	APIKey         string  `json:"api_key"`      // API key for non-Ollama providers
	MaxTokens      int     `json:"max_tokens"`
	MaxCost        float64 `json:"max_cost"`
	MaxRepairCount int     `json:"max_repair_count"`
	Timestamp      string  `json:"timestamp"`
	SchemaVersion  string  `json:"schema_version"`
}

// ChatCloseMessage represents a chat close message from NATS
type ChatCloseMessage struct {
	MessageID     string `json:"message_id"`
	RunID         string `json:"run_id"`
	Timestamp     string `json:"timestamp"`
	SchemaVersion string `json:"schema_version"`
}

// ChatResumeMessage represents a chat resume message from NATS
type ChatResumeMessage struct {
	MessageID     string `json:"message_id"`
	RunID         string `json:"run_id"`
	RepositoryID  string `json:"repository_id"`
	ProjectID     string `json:"project_id"`
	MockMode      bool   `json:"mock_mode"`
	AgentType     string `json:"agent_type"` // "multi-agent", "single-agent", "crewai", or "crewai-expert"
	LLMProvider   string `json:"llm_provider"`
	ModelName     string `json:"model_name"`
	APIKey        string `json:"api_key"`
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
	log.Printf("[NATS RECEIVE] Run ID: %s, Repository ID: %s, Mock Mode: %v, Agent Type: %s, LLM Provider: %s", chatMsg.RunID, chatMsg.RepositoryID, chatMsg.MockMode, chatMsg.AgentType, chatMsg.LLMProvider)

	// Check if there's an existing container for this run_id
	existingContainer, getErr := chatContainerService.GetContainer(chatMsg.RunID)
	if getErr == nil && existingContainer != nil {
		log.Printf("[NATS RECEIVE] Found existing container for run %s, checking if it's alive", chatMsg.RunID)

		// Check if the container is still running
		containerStatus, statusErr := containerManager.GetChatContainerStatus(existingContainer.ContainerID)
		if statusErr != nil {
			log.Printf("[NATS RECEIVE] Failed to get container status for run %s: %v", chatMsg.RunID, statusErr)
		} else if !containerStatus.Running {
			log.Printf("[NATS RECEIVE] Container for run %s is not running (status: %s), cleaning up and recreating", chatMsg.RunID, containerStatus.Status)

			// Stop and remove the dead container
			if existingContainer.ContainerID != "" {
				if stopErr := containerManager.StopWorker(existingContainer.ContainerID); stopErr != nil {
					log.Printf("[NATS RECEIVE] Failed to stop dead container for run %s: %v", chatMsg.RunID, stopErr)
				} else {
					log.Printf("[NATS RECEIVE] Successfully stopped dead container for run %s", chatMsg.RunID)
				}
			}

			// Remove the database record
			if removeErr := chatContainerService.RemoveContainer(chatMsg.RunID); removeErr != nil {
				log.Printf("[NATS RECEIVE] Failed to remove container record for run %s: %v", chatMsg.RunID, removeErr)
			} else {
				log.Printf("[NATS RECEIVE] Successfully removed container record for run %s", chatMsg.RunID)
			}
		} else {
			log.Printf("[NATS RECEIVE] Container for run %s is still running, reusing existing container", chatMsg.RunID)
			return
		}
	}

	repoConfig := orchestrator.RepositoryConfig{
		RunID:        chatMsg.RunID,
		RepositoryID: chatMsg.RepositoryID,
	}
	llmConfig := orchestrator.LLMConfig{
		MockMode:    chatMsg.MockMode,
		LLMProvider: chatMsg.LLMProvider,
		ModelName:   chatMsg.ModelName,
		APIKey:      chatMsg.APIKey,
	}
	runParams := orchestrator.RunParameters{
		UserID:          chatMsg.UserID,
		ProjectID:       chatMsg.ProjectID,
		RepositoryID:    chatMsg.RepositoryID,
		Task:            chatMsg.Task,
		ChatkitThreadID: chatMsg.RunID,
		MaxTokens:       chatMsg.MaxTokens,
		MaxCost:         chatMsg.MaxCost,
		MaxRepairCount:  chatMsg.MaxRepairCount,
	}

	agentType := chatMsg.AgentType
	if agentType == "" {
		agentType = "specialist"
	}
	_, err := chatContainerService.CreateContainerForAgentType(agentType, repoConfig, llmConfig, &runParams)
	if err != nil {
		log.Printf("[NATS RECEIVE] Failed to create container for run %s: %v", chatMsg.RunID, err)
		return
	}
	log.Printf("[NATS RECEIVE] Creating %s container for run %s", agentType, chatMsg.RunID)

	if chatMsg.MockMode {
		log.Printf("[NATS RECEIVE] Mock mode enabled for run %s; mock-worker will handle this run", chatMsg.RunID)
	} else {
		log.Printf("[NATS RECEIVE] Successfully started worker container for run %s", chatMsg.RunID)
	}

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

// HandleChatResume handles chat resume messages from NATS
func HandleChatResume(msg *nats.Msg, chatContainerService *service.ChatContainerService, containerManager *orchestrator.Manager, repoRepo *repository.RepositoryRepository, nc *nats.Conn, js nats.JetStreamContext) {
	var chatMsg ChatResumeMessage
	if err := json.Unmarshal(msg.Data, &chatMsg); err != nil {
		log.Printf("[NATS RECEIVE] Failed to unmarshal chat resume message: %v", err)
		return
	}

	log.Printf("[NATS RECEIVE] Received chat resume message on subject: %s", msg.Subject)
	log.Printf("[NATS RECEIVE] Chat resume payload: %s", string(msg.Data))
	log.Printf("[NATS RECEIVE] Run ID: %s, Repository ID: %s, Mock Mode: %v, Agent Type: %s, LLM Provider: %s", chatMsg.RunID, chatMsg.RepositoryID, chatMsg.MockMode, chatMsg.AgentType, chatMsg.LLMProvider)

	repoConfig := orchestrator.RepositoryConfig{
		RunID:        chatMsg.RunID,
		RepositoryID: chatMsg.RepositoryID,
	}
	llmConfig := orchestrator.LLMConfig{
		MockMode:    chatMsg.MockMode,
		LLMProvider: chatMsg.LLMProvider,
		ModelName:   chatMsg.ModelName,
		APIKey:      chatMsg.APIKey,
	}
	runParams := orchestrator.RunParameters{
		UserID:          "", // userID not available on resume
		ProjectID:       chatMsg.ProjectID,
		RepositoryID:    chatMsg.RepositoryID,
		Task:            "", // task not available on resume
		ChatkitThreadID: "", // chatkitThreadID not available on resume
		MaxTokens:       0,  // maxTokens not available on resume
		MaxCost:         0,  // maxCost not available on resume
		MaxRepairCount:  2,  // maxRepairCount default
	}

	agentType := chatMsg.AgentType
	if agentType == "" {
		agentType = "specialist"
	}
	_, err := chatContainerService.CreateContainerForAgentType(agentType, repoConfig, llmConfig, &runParams)
	if err != nil {
		log.Printf("[NATS RECEIVE] Failed to recreate container for run %s: %v", chatMsg.RunID, err)
		return
	}
	log.Printf("[NATS RECEIVE] Recreating %s container for run %s", agentType, chatMsg.RunID)

	if chatMsg.MockMode {
		log.Printf("[NATS RECEIVE] Mock mode enabled for run %s; mock-worker will handle this run", chatMsg.RunID)
	} else {
		log.Printf("[NATS RECEIVE] Successfully restarted worker container for run %s", chatMsg.RunID)
	}

	log.Printf("[NATS RECEIVE] Worker container restarted and will publish ready signal for run %s", chatMsg.RunID)
}

// CleanNATSMessageBus purges the known agent JetStream streams so the
// control-plane starts from a clean state and does not process stale messages.
func CleanNATSMessageBus(js nats.JetStreamContext) int {
	log.Println("Cleaning NATS message bus...")

	streams := internalnats.AllStreams()
	cleaned := 0
	for _, stream := range streams {
		if err := js.PurgeStream(stream); err != nil {
			if errors.Is(err, nats.ErrStreamNotFound) {
				log.Printf("NATS stream %s not found, skipping", stream)
				continue
			}
			log.Printf("Failed to purge NATS stream %s: %v", stream, err)
			continue
		}
		log.Printf("Purged NATS stream %s", stream)
		cleaned++
	}

	log.Printf("Cleaned %d NATS stream(s)", cleaned)
	return cleaned
}
