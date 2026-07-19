package orchestrator

import (
	"fmt"
	"log"
	"os"
	"regexp"
	"strings"
	"time"

	"github.com/google/uuid"
)

// RepositoryConfig holds repository-related configuration
type RepositoryConfig struct {
	RunID         string
	RepositoryURL string
	Branch        string
	RepositoryID  string
	Credentials   *RepositoryCredentials
}

// LLMConfig holds LLM-related configuration
type LLMConfig struct {
	MockMode    bool
	LLMProvider string
	ModelName   string
	APIKey      string
}

// WorkerContainerConfig holds container deployment configuration
type WorkerContainerConfig struct {
	ImageName           string
	ContainerNamePrefix string
	Network             string
	NATSURL             string
	AgentType           string
}

// RunParameters holds run-specific parameters
type RunParameters struct {
	UserID          string
	ProjectID       string
	RepositoryID    string
	Task            string
	ChatkitThreadID string
	MaxTokens       int
	MaxCost         float64
	MaxRepairCount  int
}

// Manager manages container lifecycle for runs
type Manager struct {
	orchestrator ContainerOrchestrator
}

// NewManager creates a new container manager
func NewManager(orchestrator ContainerOrchestrator) *Manager {
	return &Manager{
		orchestrator: orchestrator,
	}
}

// StopChatContainer stops a chat container
func (m *Manager) StopChatContainer(containerID string) error {
	if strings.HasPrefix(containerID, "mock-") {
		return nil
	}
	if err := m.orchestrator.StopContainer(containerID); err != nil {
		return fmt.Errorf("failed to stop container: %w", err)
	}
	return nil
}

// RemoveChatContainer removes a chat container
func (m *Manager) RemoveChatContainer(containerID string) error {
	if strings.HasPrefix(containerID, "mock-") {
		return nil
	}
	if err := m.orchestrator.RemoveContainer(containerID); err != nil {
		return fmt.Errorf("failed to remove container: %w", err)
	}
	return nil
}

// GetChatContainerStatus gets the status of a chat container
func (m *Manager) GetChatContainerStatus(containerID string) (*ChatContainerStatus, error) {
	status, err := m.orchestrator.GetContainerStatus(containerID)
	if err != nil {
		return nil, fmt.Errorf("failed to get container status: %w", err)
	}

	return &ChatContainerStatus{
		ContainerID: status.ContainerID,
		Status:      status.Status,
		Running:     status.Running,
	}, nil
}

// StartWorker starts a worker container for a run
func (m *Manager) StartWorker(repoConfig RepositoryConfig, llmConfig LLMConfig) (*ChatContainerInfo, error) {
	return m.CreateContainerForAgentType("specialist", repoConfig, llmConfig, nil)
}

// agentContainerConfigs maps agent types to their Docker image and naming prefix.
var agentContainerConfigs = map[string]WorkerContainerConfig{
	"single-agent": {
		ImageName:           "agentic-agents-platform-agent-worker-single-agent:latest",
		ContainerNamePrefix: "automated-single-agent-run",
		Network:             "agentic-network",
		NATSURL:             "nats://nats:4222",
		AgentType:           "single-agent",
	},
	"specialist": {
		ImageName:           "agentic-agents-platform-agent-worker-specialist:latest",
		ContainerNamePrefix: "automated-specialists-run",
		Network:             "agentic-network",
		NATSURL:             "nats://nats:4222",
		AgentType:           "specialist",
	},
	"crewai": {
		ImageName:           "agentic-agents-platform-agent-worker-crewai:latest",
		ContainerNamePrefix: "automated-crewai-run",
		Network:             "agentic-network",
		NATSURL:             "nats://nats:4222",
		AgentType:           "crewai",
	},
	"crewai-expert": {
		ImageName:           "agentic-agents-platform-agent-worker-crewai-expert:latest",
		ContainerNamePrefix: "automated-crewai-expert-run",
		Network:             "agentic-network",
		NATSURL:             "nats://nats:4222",
		AgentType:           "crewai-expert",
	},
}

func (m *Manager) workerConfigForAgentType(agentType string) (WorkerContainerConfig, error) {
	if agentType == "" {
		agentType = "specialist"
	}
	cfg, ok := agentContainerConfigs[agentType]
	if !ok {
		return WorkerContainerConfig{}, fmt.Errorf("unsupported agent type: %s", agentType)
	}
	return cfg, nil
}

// createContainer builds the low-level ContainerConfig and asks the orchestrator to create the container.
func (m *Manager) createContainer(repoConfig RepositoryConfig, llmConfig LLMConfig, containerConfig WorkerContainerConfig, runParams *RunParameters) (*ChatContainerInfo, error) {
	containerName := fmt.Sprintf("%s-%s", containerConfig.ContainerNamePrefix, repoConfig.RunID)
	env := map[string]string{
		"RUN_ID":         repoConfig.RunID,
		"REPOSITORY_URL": repoConfig.RepositoryURL,
		"BRANCH":         repoConfig.Branch,
		"NATS_URL":       containerConfig.NATSURL,
		"LLM_PROVIDER":   llmConfig.LLMProvider,
		"MODEL_NAME":     llmConfig.ModelName,
		"API_KEY":        llmConfig.APIKey,
	}

	if runParams != nil {
		env["USER_ID"] = runParams.UserID
		env["PROJECT_ID"] = runParams.ProjectID
		env["REPOSITORY_ID"] = runParams.RepositoryID
		env["TASK"] = runParams.Task
		env["MAX_TOKENS"] = fmt.Sprintf("%d", runParams.MaxTokens)
		env["MAX_COST"] = fmt.Sprintf("%f", runParams.MaxCost)
		env["MAX_REPAIR_COUNT"] = fmt.Sprintf("%d", runParams.MaxRepairCount)
	} else {
		env["USER_ID"] = ""
		env["PROJECT_ID"] = ""
		env["REPOSITORY_ID"] = ""
		env["TASK"] = ""
		env["MAX_TOKENS"] = ""
		env["MAX_COST"] = ""
		env["MAX_REPAIR_COUNT"] = "2"
	}

	if containerConfig.AgentType != "" {
		env["AGENT_TYPE"] = containerConfig.AgentType
	}

	// Set MOCK_MODE from environment variable with default "false"
	mockModeEnv := os.Getenv("MOCK_MODE")
	if mockModeEnv == "" {
		mockModeEnv = "false"
	}
	env["MOCK_MODE"] = mockModeEnv

	// Override with parameter if explicitly set to true
	if llmConfig.MockMode {
		env["MOCK_MODE"] = "true"
	}

	if repoConfig.Credentials != nil {
		env["GIT_USERNAME"] = repoConfig.Credentials.Username
		env["GIT_TOKEN"] = repoConfig.Credentials.Token
	}

	// Pass through environment variables required by the worker
	for _, key := range []string{
		"DATABASE_URL",
		"OPENAI_API_KEY",
		"ANTHROPIC_API_KEY",
		"OLLAMA_BASE_URL",
		"LANGSMITH_API_KEY",
		"LANGSMITH_PROJECT",
	} {
		if val := os.Getenv(key); val != "" {
			env[key] = val
		}
	}

	config := ContainerConfig{
		RunID:         repoConfig.RunID,
		RepositoryURL: repoConfig.RepositoryURL,
		Branch:        repoConfig.Branch,
		Credentials:   repoConfig.Credentials,
		Image:         containerConfig.ImageName,
		ContainerName: containerName,
		Network:       containerConfig.Network,
		EnvVars:       env,
	}

	result, err := m.orchestrator.CreateContainer(config)
	if err != nil {
		return nil, fmt.Errorf("failed to create container: %w", err)
	}

	return &ChatContainerInfo{
		ID:            uuid.New().String(),
		RunID:         repoConfig.RunID,
		ContainerID:   result.ContainerID,
		ContainerName: containerName,
		RepositoryURL: repoConfig.RepositoryURL,
		Branch:        repoConfig.Branch,
		Status:        result.Status,
		CreatedAt:     time.Now(),
	}, nil
}

// CreateContainerForAgentType creates a container for the given agent type.
func (m *Manager) CreateContainerForAgentType(agentType string, repoConfig RepositoryConfig, llmConfig LLMConfig, runParams *RunParameters) (*ChatContainerInfo, error) {
	containerConfig, err := m.workerConfigForAgentType(agentType)
	if err != nil {
		return nil, err
	}
	return m.createContainer(repoConfig, llmConfig, containerConfig, runParams)
}

// StopWorker stops and removes a worker container for a run
func (m *Manager) StopWorker(containerID string) error {
	// Stop the container
	if err := m.StopChatContainer(containerID); err != nil {
		return fmt.Errorf("failed to stop worker container: %w", err)
	}

	// Remove the container
	if err := m.RemoveChatContainer(containerID); err != nil {
		return fmt.Errorf("failed to remove worker container: %w", err)
	}

	return nil
}

// CreateSingleAgentContainer creates a new container for a single-agent worker
func (m *Manager) CreateSingleAgentContainer(repoConfig RepositoryConfig, llmConfig LLMConfig) (*ChatContainerInfo, error) {
	return m.CreateContainerForAgentType("single-agent", repoConfig, llmConfig, nil)
}

// CreateSpecialistAgentContainer creates a new container for a specialist agent (multi-agent) worker
func (m *Manager) CreateSpecialistAgentContainer(repoConfig RepositoryConfig, llmConfig LLMConfig) (*ChatContainerInfo, error) {
	return m.CreateContainerForAgentType("specialist", repoConfig, llmConfig, nil)
}

// CreateSingleAgentContainerWithParams creates a new container for a single-agent worker with run parameters
func (m *Manager) CreateSingleAgentContainerWithParams(repoConfig RepositoryConfig, llmConfig LLMConfig, runParams RunParameters) (*ChatContainerInfo, error) {
	return m.CreateContainerForAgentType("single-agent", repoConfig, llmConfig, &runParams)
}

// CreateSpecialistAgentContainerWithParams creates a new container for a specialist agent (multi-agent) worker with run parameters
func (m *Manager) CreateSpecialistAgentContainerWithParams(repoConfig RepositoryConfig, llmConfig LLMConfig, runParams RunParameters) (*ChatContainerInfo, error) {
	return m.CreateContainerForAgentType("specialist", repoConfig, llmConfig, &runParams)
}

// CreateCrewAIContainerWithParams creates a new container for a CrewAI worker with run parameters
func (m *Manager) CreateCrewAIContainerWithParams(repoConfig RepositoryConfig, llmConfig LLMConfig, runParams RunParameters) (*ChatContainerInfo, error) {
	return m.CreateContainerForAgentType("crewai", repoConfig, llmConfig, &runParams)
}

// CreateCrewAIExpertContainerWithParams creates a new container for the CrewAI expert worker with run parameters
func (m *Manager) CreateCrewAIExpertContainerWithParams(repoConfig RepositoryConfig, llmConfig LLMConfig, runParams RunParameters) (*ChatContainerInfo, error) {
	return m.CreateContainerForAgentType("crewai-expert", repoConfig, llmConfig, &runParams)
}

// ChatContainerInfo holds information about a run container
type ChatContainerInfo struct {
	ID            string
	RunID         string
	ContainerID   string
	ContainerName string
	RepositoryURL string
	Branch        string
	Status        string
	CreatedAt     time.Time
}

// ChatContainerStatus holds the status of a chat container
type ChatContainerStatus struct {
	ContainerID string
	Status      string
	Running     bool
}

// systemContainers defines containers that should never be cleaned up
var systemContainers = map[string]bool{
	"agentic-web":           true,
	"agentic-agent-service": true,
	"agentic-control-plane": true,
	"agentic-postgres":      true,
	"agentic-nats":          true,
}

// isSystemContainer checks if a container is a system container that should be protected
func isSystemContainer(containerName string) bool {
	return systemContainers[containerName]
}

// extractRunIDFromName extracts a run ID from a container name using the run-{uuid} pattern
func extractRunIDFromName(containerName string) string {
	runIDPattern := regexp.MustCompile(`^run-([a-f0-9-]{36})$`)
	matches := runIDPattern.FindStringSubmatch(containerName)
	if matches == nil {
		return ""
	}
	return matches[1]
}

// ShouldCleanupContainer determines if a container should be cleaned up based on its name and valid run IDs
func ShouldCleanupContainer(containerName string, validRunIDs map[string]bool) bool {
	if isSystemContainer(containerName) {
		return false
	}

	runID := extractRunIDFromName(containerName)
	if runID == "" {
		return false
	}

	// Container is rogue if its run ID is not in the database
	return !validRunIDs[runID]
}

// removeContainer safely removes a container with proper error handling and logging
func (m *Manager) removeContainer(containerID, containerName, runID string) error {
	log.Printf("INFO: Found rogue container: name=%s id=%s run_id=%s", containerName, containerID, runID)

	// Try to stop the container first, but don't fail if it's already stopped
	if err := m.StopChatContainer(containerID); err != nil {
		log.Printf("WARN: Failed to stop rogue container id=%s (may already be stopped): %v", containerID, err)
	} else {
		log.Printf("INFO: Successfully stopped rogue container id=%s", containerID)
	}

	// Remove the container (force remove if stop failed)
	if err := m.RemoveChatContainer(containerID); err != nil {
		log.Printf("ERROR: Failed to remove rogue container id=%s: %v", containerID, err)
		return err
	}

	log.Printf("INFO: Successfully removed rogue container: id=%s name=%s run_id=%s", containerID, containerName, runID)
	return nil
}

// processContainer checks a single container and removes it if it's a rogue container
func (m *Manager) processContainer(container map[string]interface{}, validRunIDs map[string]bool) (bool, error) {
	names, ok := container["Names"].([]interface{})
	if !ok || len(names) == 0 {
		return false, nil
	}

	containerName := strings.TrimPrefix(names[0].(string), "/")
	containerID, ok := container["Id"].(string)
	if !ok {
		return false, nil
	}

	// Check if this is a system container
	if isSystemContainer(containerName) {
		log.Printf("DEBUG: Skipping system container: %s", containerName)
		return false, nil
	}

	// Extract run ID from container name
	runID := extractRunIDFromName(containerName)
	if runID == "" {
		log.Printf("DEBUG: Skipping container %s (does not match worker naming pattern)", containerName)
		return false, nil
	}

	// Check if run ID exists in database
	if validRunIDs[runID] {
		log.Printf("DEBUG: Container id=%s run_id=%s is valid (exists in database)", containerID, runID)
		return false, nil
	}

	// Remove the rogue container
	if err := m.removeContainer(containerID, containerName, runID); err != nil {
		return false, err
	}

	return true, nil
}

// CleanupRogueContainers removes containers with run IDs that are not in the database.
// This function is called on startup to clean up orphaned containers from previous runs.
// It handles errors gracefully to prevent control-plane startup failures.
func (m *Manager) CleanupRogueContainers(validRunIDs map[string]bool) error {
	log.Println("Starting rogue container cleanup...")

	containers, err := m.orchestrator.ListContainers(nil)
	if err != nil {
		log.Printf("ERROR: Failed to list containers: %v", err)
		return fmt.Errorf("failed to list containers: %w", err)
	}

	log.Printf("Found %d total containers to check", len(containers))

	cleanedCount := 0
	skippedCount := 0
	errorCount := 0

	for _, container := range containers {
		cleaned, err := m.processContainer(container, validRunIDs)
		if err != nil {
			errorCount++
		} else if cleaned {
			cleanedCount++
		} else {
			skippedCount++
		}
	}

	log.Printf("Rogue container cleanup complete: cleaned=%d skipped=%d errors=%d total=%d",
		cleanedCount, skippedCount, errorCount, len(containers))

	if cleanedCount > 0 {
		log.Printf("INFO: Successfully cleaned up %d rogue containers", cleanedCount)
	} else {
		log.Println("INFO: No rogue containers found")
	}

	return nil
}
