package orchestrator

import (
	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
)

var _ = Describe("Manager", func() {
	var manager *Manager
	var mockOrch *MockOrchestrator

	BeforeEach(func() {
		mockOrch = &MockOrchestrator{}
		manager = NewManager(mockOrch)
	})

	Describe("isSystemContainer", func() {
		Context("when container name is a system container", func() {
			It("should return true for agentic-web", func() {
				Expect(isSystemContainer("agentic-web")).To(BeTrue())
			})

			It("should return true for agentic-agent-service", func() {
				Expect(isSystemContainer("agentic-agent-service")).To(BeTrue())
			})

			It("should return true for agentic-control-plane", func() {
				Expect(isSystemContainer("agentic-control-plane")).To(BeTrue())
			})

			It("should return true for agentic-postgres", func() {
				Expect(isSystemContainer("agentic-postgres")).To(BeTrue())
			})

			It("should return true for agentic-nats", func() {
				Expect(isSystemContainer("agentic-nats")).To(BeTrue())
			})
		})

		Context("when container name is not a system container", func() {
			It("should return false for worker containers", func() {
				Expect(isSystemContainer("run-123e4567-e89b-12d3-a456-426614174000")).To(BeFalse())
			})

			It("should return false for random container names", func() {
				Expect(isSystemContainer("random-container")).To(BeFalse())
			})
		})
	})

	Describe("extractRunIDFromName", func() {
		Context("when container name matches run-{uuid} pattern", func() {
			It("should extract valid UUID from run- prefix", func() {
				runID := extractRunIDFromName("run-123e4567-e89b-12d3-a456-426614174000")
				Expect(runID).To(Equal("123e4567-e89b-12d3-a456-426614174000"))
			})

			It("should extract UUID with different format", func() {
				runID := extractRunIDFromName("run-550e8400-e29b-41d4-a716-446655440000")
				Expect(runID).To(Equal("550e8400-e29b-41d4-a716-446655440000"))
			})
		})

		Context("when container name does not match pattern", func() {
			It("should return empty string for system containers", func() {
				runID := extractRunIDFromName("agentic-web")
				Expect(runID).To(BeEmpty())
			})

			It("should return empty string for invalid format", func() {
				runID := extractRunIDFromName("run-123")
				Expect(runID).To(BeEmpty())
			})

			It("should return empty string for random names", func() {
				runID := extractRunIDFromName("random-container-name")
				Expect(runID).To(BeEmpty())
			})

			It("should return empty string for empty input", func() {
				runID := extractRunIDFromName("")
				Expect(runID).To(BeEmpty())
			})
		})
	})

	Describe("ShouldCleanupContainer", func() {
		Context("when container is a system container", func() {
			It("should return false regardless of valid run IDs", func() {
				validRunIDs := map[string]bool{"123e4567-e89b-12d3-a456-426614174000": true}
				Expect(ShouldCleanupContainer("agentic-web", validRunIDs)).To(BeFalse())
			})
		})

		Context("when container name does not match pattern", func() {
			It("should return false", func() {
				validRunIDs := map[string]bool{}
				Expect(ShouldCleanupContainer("random-container", validRunIDs)).To(BeFalse())
			})
		})

		Context("when container has valid run ID in database", func() {
			It("should return false", func() {
				validRunIDs := map[string]bool{"123e4567-e89b-12d3-a456-426614174000": true}
				Expect(ShouldCleanupContainer("run-123e4567-e89b-12d3-a456-426614174000", validRunIDs)).To(BeFalse())
			})
		})

		Context("when container has invalid run ID not in database", func() {
			It("should return true", func() {
				validRunIDs := map[string]bool{}
				Expect(ShouldCleanupContainer("run-123e4567-e89b-12d3-a456-426614174000", validRunIDs)).To(BeTrue())
			})
		})
	})

	Describe("CleanupRogueContainers", func() {
		Context("when listing containers fails", func() {
			It("should return error", func() {
				mockOrch.listError = true
				validRunIDs := map[string]bool{}

				err := manager.CleanupRogueContainers(validRunIDs)
				Expect(err).To(HaveOccurred())
				Expect(err.Error()).To(ContainSubstring("failed to list containers"))
			})
		})

		Context("when no containers exist", func() {
			It("should complete successfully with zero counts", func() {
				mockOrch.containers = []map[string]interface{}{}
				validRunIDs := map[string]bool{}

				err := manager.CleanupRogueContainers(validRunIDs)
				Expect(err).NotTo(HaveOccurred())
			})
		})

		Context("when only system containers exist", func() {
			It("should skip all system containers", func() {
				mockOrch.containers = []map[string]interface{}{
					{"Id": "abc123", "Names": []interface{}{"/agentic-web"}},
					{"Id": "def456", "Names": []interface{}{"/agentic-control-plane"}},
				}
				validRunIDs := map[string]bool{}

				err := manager.CleanupRogueContainers(validRunIDs)
				Expect(err).NotTo(HaveOccurred())
				Expect(mockOrch.removedContainers).To(BeEmpty())
			})
		})

		Context("when rogue containers exist", func() {
			It("should remove containers with invalid run IDs", func() {
				mockOrch.containers = []map[string]interface{}{
					{"Id": "abc123", "Names": []interface{}{"/run-123e4567-e89b-12d3-a456-426614174000"}},
				}
				validRunIDs := map[string]bool{} // Empty database

				err := manager.CleanupRogueContainers(validRunIDs)
				Expect(err).NotTo(HaveOccurred())
				Expect(mockOrch.removedContainers).To(HaveLen(1))
				Expect(mockOrch.removedContainers).To(ContainElement("abc123"))
			})
		})

		Context("when valid containers exist", func() {
			It("should not remove containers with valid run IDs", func() {
				mockOrch.containers = []map[string]interface{}{
					{"Id": "abc123", "Names": []interface{}{"/run-123e4567-e89b-12d3-a456-426614174000"}},
				}
				validRunIDs := map[string]bool{"123e4567-e89b-12d3-a456-426614174000": true}

				err := manager.CleanupRogueContainers(validRunIDs)
				Expect(err).NotTo(HaveOccurred())
				Expect(mockOrch.removedContainers).To(BeEmpty())
			})
		})

		Context("when mixed containers exist", func() {
			It("should only remove rogue containers", func() {
				mockOrch.containers = []map[string]interface{}{
					{"Id": "sys1", "Names": []interface{}{"/agentic-web"}},
					{"Id": "valid1", "Names": []interface{}{"/run-123e4567-e89b-12d3-a456-426614174000"}},
					{"Id": "rogue1", "Names": []interface{}{"/run-550e8400-e29b-41d4-a716-446655440000"}},
					{"Id": "random1", "Names": []interface{}{"/random-container"}},
				}
				validRunIDs := map[string]bool{"123e4567-e89b-12d3-a456-426614174000": true}

				err := manager.CleanupRogueContainers(validRunIDs)
				Expect(err).NotTo(HaveOccurred())
				Expect(mockOrch.removedContainers).To(HaveLen(1))
				Expect(mockOrch.removedContainers).To(ContainElement("rogue1"))
			})
		})
	})

	Describe("CreateCrewAIExpertContainerWithParams", func() {
		Context("when creating a crewai-expert container", func() {
			It("should use the crewai-expert image and agent type", func() {
				repoConfig := RepositoryConfig{RunID: "run-123", RepositoryURL: "https://example.com/repo.git"}
				llmConfig := LLMConfig{}
				runParams := RunParameters{UserID: "user-123"}

				_, err := manager.CreateCrewAIExpertContainerWithParams(repoConfig, llmConfig, runParams)
				Expect(err).NotTo(HaveOccurred())
				Expect(mockOrch.createdConfigs).To(HaveLen(1))

				config := mockOrch.createdConfigs[0]
				Expect(config.Image).To(Equal("agentic-agents-platform-agent-worker-crewai-expert:latest"))
				Expect(config.EnvVars["AGENT_TYPE"]).To(Equal("crewai-expert"))
				Expect(config.EnvVars["USER_ID"]).To(Equal("user-123"))
			})
		})
	})
})

// MockOrchestrator is a mock implementation of ContainerOrchestrator for testing
type MockOrchestrator struct {
	containers        []map[string]interface{}
	removedContainers []string
	createdConfigs    []ContainerConfig
	listError         bool
	stopError         bool
	removeError       bool
}

func (m *MockOrchestrator) CreateContainer(config ContainerConfig) (*ContainerResult, error) {
	m.createdConfigs = append(m.createdConfigs, config)
	return &ContainerResult{ContainerID: "mock-id", Status: "running"}, nil
}

func (m *MockOrchestrator) StopContainer(containerID string) error {
	if m.stopError {
		return &mockError{message: "stop failed"}
	}
	return nil
}

func (m *MockOrchestrator) RemoveContainer(containerID string) error {
	if m.removeError {
		return &mockError{message: "remove failed"}
	}
	m.removedContainers = append(m.removedContainers, containerID)
	return nil
}

func (m *MockOrchestrator) GetContainerStatus(containerID string) (*ContainerStatus, error) {
	return &ContainerStatus{ContainerID: containerID, Status: "running", Running: true}, nil
}

func (m *MockOrchestrator) ExecInContainer(containerID string, command []string) error {
	return nil
}

func (m *MockOrchestrator) ListContainers(filterArgs map[string]string) ([]map[string]interface{}, error) {
	if m.listError {
		return nil, &mockError{message: "list failed"}
	}
	return m.containers, nil
}

type mockError struct {
	message string
}

func (e *mockError) Error() string {
	return e.message
}
