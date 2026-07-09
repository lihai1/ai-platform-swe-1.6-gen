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

// DockerHTTPOrchestrator implements ContainerOrchestrator using Docker HTTP API
type DockerHTTPOrchestrator struct {
	httpClient *http.Client
	mockMode   bool
	dockerHost string
}

// NewDockerHTTPOrchestrator creates a new Docker HTTP orchestrator
func NewDockerHTTPOrchestrator() (*DockerHTTPOrchestrator, error) {
	mockMode := os.Getenv("MOCK_DOCKER") == "true"

	if mockMode {
		return &DockerHTTPOrchestrator{mockMode: true}, nil
	}

	dockerHost := os.Getenv("DOCKER_HOST")
	if dockerHost == "" {
		dockerHost = "http://localhost:2375"
	}

	return &DockerHTTPOrchestrator{
		httpClient: &http.Client{Timeout: 30 * time.Second},
		mockMode:   false,
		dockerHost: dockerHost,
	}, nil
}

// CreateContainer creates a new Docker container for the chat
func (d *DockerHTTPOrchestrator) CreateContainer(config ContainerConfig) (*ContainerResult, error) {
	if d.mockMode {
		// Mock mode - return fake container ID
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

	resp, err := d.httpClient.Post(
		fmt.Sprintf("%s/containers/create?name=%s", d.dockerHost, config.RunID),
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
		fmt.Sprintf("%s/containers/%s/start", d.dockerHost, createResp.ID),
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
func (d *DockerHTTPOrchestrator) StopContainer(containerID string) error {
	if d.mockMode {
		return nil
	}

	resp, err := d.httpClient.Post(
		fmt.Sprintf("%s/containers/%s/stop?t=30", d.dockerHost, containerID),
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
func (d *DockerHTTPOrchestrator) RemoveContainer(containerID string) error {
	if d.mockMode {
		return nil
	}

	req, _ := http.NewRequest("DELETE", fmt.Sprintf("%s/containers/%s?force=true", d.dockerHost, containerID), nil)
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
func (d *DockerHTTPOrchestrator) GetContainerStatus(containerID string) (*ContainerStatus, error) {
	if d.mockMode {
		return &ContainerStatus{
			ContainerID: containerID,
			Status:      "running",
			Running:     true,
		}, nil
	}

	resp, err := d.httpClient.Get(fmt.Sprintf("%s/containers/%s/json", d.dockerHost, containerID))
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

// ListContainers lists all containers with optional filters
func (d *DockerHTTPOrchestrator) ListContainers(filterArgs map[string]string) ([]map[string]interface{}, error) {
	if d.mockMode {
		return []map[string]interface{}{}, nil
	}

	resp, err := d.httpClient.Get(fmt.Sprintf("%s/containers/json?all=true", d.dockerHost))
	if err != nil {
		return nil, fmt.Errorf("failed to list containers: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("failed to list containers: %s", string(body))
	}

	var containers []map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&containers); err != nil {
		return nil, fmt.Errorf("failed to decode list response: %w", err)
	}

	return containers, nil
}

// ExecInContainer executes a command inside a container
func (d *DockerHTTPOrchestrator) ExecInContainer(containerID string, command []string) error {
	if d.mockMode {
		return nil
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
		fmt.Sprintf("%s/containers/%s/exec", d.dockerHost, containerID),
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
		fmt.Sprintf("%s/exec/%s/start", d.dockerHost, execResp.ID),
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
