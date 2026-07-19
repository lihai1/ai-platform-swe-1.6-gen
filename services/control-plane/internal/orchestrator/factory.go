package orchestrator

import (
	"fmt"
)

// ContainerOrchestrator defines the interface for container orchestration
type ContainerOrchestrator interface {
	CreateContainer(config ContainerConfig) (*ContainerResult, error)
	StopContainer(containerID string) error
	RemoveContainer(containerID string) error
	GetContainerStatus(containerID string) (*ContainerStatus, error)
	ExecInContainer(containerID string, command []string) error
	ListContainers(filterArgs map[string]string) ([]map[string]interface{}, error)
}

// ContainerConfig holds configuration for creating a container
type ContainerConfig struct {
	RunID         string
	RepositoryURL string
	Branch        string
	Credentials   *RepositoryCredentials
	Image         string
	EnvVars       map[string]string
	ContainerName string
	Network       string
}

// RepositoryCredentials holds credentials for repository access
type RepositoryCredentials struct {
	Username string
	Token    string
}

// ContainerResult holds the result of container creation
type ContainerResult struct {
	ContainerID string
	Status      string
}

// ContainerStatus holds the status of a container
type ContainerStatus struct {
	ContainerID string
	Status      string
	Running     bool
}

// OrchestratorType defines the type of orchestrator
type OrchestratorType string

const (
	OrchestratorTypeDockerHTTP OrchestratorType = "docker-http"
	OrchestratorTypeDockerBind OrchestratorType = "docker-bind"
	OrchestratorTypeKubernetes OrchestratorType = "kubernetes"
)

// NewOrchestrator creates a new container orchestrator based on type and configuration
func NewOrchestrator(orchestratorType OrchestratorType, dockerSocketPath, kubeconfigPath, kubernetesNamespace string) (ContainerOrchestrator, error) {
	switch orchestratorType {
	case OrchestratorTypeDockerHTTP:
		return NewDockerHTTPOrchestrator()
	case OrchestratorTypeDockerBind:
		return NewDockerBindOrchestrator(dockerSocketPath)
	case OrchestratorTypeKubernetes:
		return NewKubernetesOrchestrator(kubeconfigPath, kubernetesNamespace)
	default:
		return nil, fmt.Errorf("unsupported orchestrator type: %s", orchestratorType)
	}
}
