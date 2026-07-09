package orchestrator

import (
	"context"
	"fmt"
	"time"

	"github.com/google/uuid"
)

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

// CreateChatContainer creates a new container for a run
func (m *Manager) CreateChatContainer(runID, repositoryURL, branch string, credentials *RepositoryCredentials, mockMode bool) (*ChatContainerInfo, error) {
	containerName := fmt.Sprintf("automated-run-%s", runID)
	config := ContainerConfig{
		RunID:         runID,
		RepositoryURL: repositoryURL,
		Branch:        branch,
		Credentials:   credentials,
		Image:         "agentic-orchestrator:latest",
		ContainerName: containerName,
		EnvVars: map[string]string{
			"RUN_ID":         runID,
			"REPOSITORY_URL": repositoryURL,
			"BRANCH":         branch,
			"NATS_URL":       "nats://nats:4222",
			"MOCK_MODE":      "false",
		},
	}

	if mockMode {
		config.EnvVars["MOCK_MODE"] = "true"
	}

	if credentials != nil {
		config.EnvVars["GIT_USERNAME"] = credentials.Username
		config.EnvVars["GIT_TOKEN"] = credentials.Token
	}

	result, err := m.orchestrator.CreateContainer(config)
	if err != nil {
		return nil, fmt.Errorf("failed to create container: %w", err)
	}

	return &ChatContainerInfo{
		ID:            uuid.New().String(),
		RunID:         runID,
		ContainerID:   result.ContainerID,
		ContainerName: containerName,
		RepositoryURL: repositoryURL,
		Branch:        branch,
		Status:        result.Status,
		CreatedAt:     time.Now(),
	}, nil
}

// StopChatContainer stops a chat container
func (m *Manager) StopChatContainer(containerID string) error {
	if err := m.orchestrator.StopContainer(containerID); err != nil {
		return fmt.Errorf("failed to stop container: %w", err)
	}
	return nil
}

// RemoveChatContainer removes a chat container
func (m *Manager) RemoveChatContainer(containerID string) error {
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
func (m *Manager) StartWorker(runID, repositoryURL, branch string, credentials *RepositoryCredentials, mockMode bool) (*ChatContainerInfo, error) {
	return m.CreateChatContainer(runID, repositoryURL, branch, credentials, mockMode)
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

// TODO! consider to remove this function when worker ready signal is verified
// WaitForContainerReady waits for a container to be ready (running)
func (m *Manager) WaitForContainerReady(containerID string, timeout time.Duration) error {
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	ticker := time.NewTicker(1 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return fmt.Errorf("timeout waiting for container to be ready")
		case <-ticker.C:
			status, err := m.GetChatContainerStatus(containerID)
			if err != nil {
				// Container might not exist yet, continue waiting
				continue
			}
			if status.Running {
				return nil
			}
		}
	}
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
