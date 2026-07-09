package orchestrator

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"
)

// DockerBindOrchestrator implements ContainerOrchestrator using Docker HTTP API with socket support
type DockerBindOrchestrator struct {
	httpClient   *http.Client
	mockMode     bool
	dockerSocket string
}

// NewDockerBindOrchestrator creates a new Docker bind orchestrator
func NewDockerBindOrchestrator(dockerSocketPath string) (*DockerBindOrchestrator, error) {
	mockMode := os.Getenv("MOCK_DOCKER") == "true"

	if mockMode {
		return &DockerBindOrchestrator{mockMode: true}, nil
	}

	if dockerSocketPath == "" {
		dockerSocketPath = os.Getenv("DOCKER_SOCKET_PATH")
		if dockerSocketPath == "" {
			dockerSocketPath = "/var/run/docker.sock"
		}
	}

	// For Docker bind, we use the Unix socket
	dockerHost := fmt.Sprintf("unix://%s", dockerSocketPath)

	return &DockerBindOrchestrator{
		httpClient:   &http.Client{Timeout: 30 * time.Second},
		mockMode:     false,
		dockerSocket: dockerHost,
	}, nil
}

// CreateContainer creates a new Docker container for the chat
func (d *DockerBindOrchestrator) CreateContainer(config ContainerConfig) (*ContainerResult, error) {
	if d.mockMode {
		return &ContainerResult{
			ContainerID: fmt.Sprintf("mock-container-%s", config.RunID),
			Status:      "running",
		}, nil
	}

	// Build environment variables
	env := []string{
		fmt.Sprintf("RUN_ID=%s", config.RunID),
		fmt.Sprintf("REPOSITORY_URL=%s", config.RepositoryURL),
		fmt.Sprintf("BRANCH=%s", config.Branch),
	}

	if config.Credentials != nil {
		env = append(env, fmt.Sprintf("GIT_USERNAME=%s", config.Credentials.Username))
		env = append(env, fmt.Sprintf("GIT_TOKEN=%s", config.Credentials.Token))
	}

	for k, v := range config.EnvVars {
		env = append(env, fmt.Sprintf("%s=%s", k, v))
	}

	// Create container via Docker API
	createReq := map[string]interface{}{
		"Image": config.Image,
		"Env":   env,
		"Cmd":   []string{"/app/container-start.sh"},
		"HostConfig": map[string]interface{}{
			"NetworkMode": "bridge",
		},
	}

	body, err := json.Marshal(createReq)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal create request: %w", err)
	}

	// Note: In production with actual Docker socket, this would use the Unix socket
	// For now, we'll use the HTTP API approach which works with socket mounting
	dockerHost := os.Getenv("DOCKER_HOST")
	if dockerHost == "" {
		dockerHost = "http://localhost:2375"
	}

	resp, err := d.httpClient.Post(
		fmt.Sprintf("%s/containers/create?name=%s", dockerHost, config.RunID),
		"application/json",
		bytes.NewReader(body),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to create container: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusCreated {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("failed to create container: %s", string(body))
	}

	var createResp struct {
		ID string `json:"Id"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&createResp); err != nil {
		return nil, fmt.Errorf("failed to decode create response: %w", err)
	}

	// Start the container
	startResp, err := d.httpClient.Post(
		fmt.Sprintf("%s/containers/%s/start", dockerHost, createResp.ID),
		"application/json",
		nil,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to start container: %w", err)
	}
	defer startResp.Body.Close()

	if startResp.StatusCode != http.StatusNoContent && startResp.StatusCode != http.StatusAccepted {
		body, _ := io.ReadAll(startResp.Body)
		return nil, fmt.Errorf("failed to start container: %s", string(body))
	}

	return &ContainerResult{
		ContainerID: createResp.ID,
		Status:      "running",
	}, nil
}

// StopContainer stops a running container
func (d *DockerBindOrchestrator) StopContainer(containerID string) error {
	if d.mockMode {
		return nil
	}

	dockerHost := os.Getenv("DOCKER_HOST")
	if dockerHost == "" {
		dockerHost = "http://localhost:2375"
	}

	resp, err := d.httpClient.Post(
		fmt.Sprintf("%s/containers/%s/stop?t=30", dockerHost, containerID),
		"application/json",
		nil,
	)
	if err != nil {
		return fmt.Errorf("failed to stop container: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusNoContent && resp.StatusCode != http.StatusAccepted {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("failed to stop container: %s", string(body))
	}

	return nil
}

// RemoveContainer removes a container
func (d *DockerBindOrchestrator) RemoveContainer(containerID string) error {
	if d.mockMode {
		return nil
	}

	dockerHost := os.Getenv("DOCKER_HOST")
	if dockerHost == "" {
		dockerHost = "http://localhost:2375"
	}

	req, _ := http.NewRequest("DELETE", fmt.Sprintf("%s/containers/%s?force=true", dockerHost, containerID), nil)
	resp, err := d.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("failed to remove container: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusNoContent && resp.StatusCode != http.StatusAccepted {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("failed to remove container: %s", string(body))
	}

	return nil
}

// GetContainerStatus gets the status of a container
func (d *DockerBindOrchestrator) GetContainerStatus(containerID string) (*ContainerStatus, error) {
	if d.mockMode {
		return &ContainerStatus{
			ContainerID: containerID,
			Status:      "running",
			Running:     true,
		}, nil
	}

	dockerHost := os.Getenv("DOCKER_HOST")
	if dockerHost == "" {
		dockerHost = "http://localhost:2375"
	}

	resp, err := d.httpClient.Get(fmt.Sprintf("%s/containers/%s/json", dockerHost, containerID))
	if err != nil {
		return nil, fmt.Errorf("failed to inspect container: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("failed to inspect container: %s", string(body))
	}

	var inspectResp struct {
		State struct {
			Status  string `json:"Status"`
			Running bool   `json:"Running"`
		} `json:"State"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&inspectResp); err != nil {
		return nil, fmt.Errorf("failed to decode inspect response: %w", err)
	}

	return &ContainerStatus{
		ContainerID: containerID,
		Status:      inspectResp.State.Status,
		Running:     inspectResp.State.Running,
	}, nil
}

// ExecInContainer executes a command inside a container
func (d *DockerBindOrchestrator) ExecInContainer(containerID string, command []string) error {
	if d.mockMode {
		return nil
	}

	dockerHost := os.Getenv("DOCKER_HOST")
	if dockerHost == "" {
		dockerHost = "http://localhost:2375"
	}

	execReq := map[string]interface{}{
		"AttachStdout": true,
		"AttachStderr": true,
		"Cmd":          command,
	}

	body, err := json.Marshal(execReq)
	if err != nil {
		return fmt.Errorf("failed to marshal exec request: %w", err)
	}

	// Create exec instance
	resp, err := d.httpClient.Post(
		fmt.Sprintf("%s/containers/%s/exec", dockerHost, containerID),
		"application/json",
		bytes.NewReader(body),
	)
	if err != nil {
		return fmt.Errorf("failed to create exec instance: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusCreated {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("failed to create exec instance: %s", string(body))
	}

	var execResp struct {
		ID string `json:"Id"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&execResp); err != nil {
		return fmt.Errorf("failed to decode exec response: %w", err)
	}

	// Start exec instance
	startReq := map[string]interface{}{
		"Detach": false,
	}
	startBody, _ := json.Marshal(startReq)
	startResp, err := d.httpClient.Post(
		fmt.Sprintf("%s/exec/%s/start", dockerHost, execResp.ID),
		"application/json",
		bytes.NewReader(startBody),
	)
	if err != nil {
		return fmt.Errorf("failed to start exec: %w", err)
	}
	defer startResp.Body.Close()

	if startResp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(startResp.Body)
		return fmt.Errorf("failed to start exec: %s", string(body))
	}

	return nil
}
