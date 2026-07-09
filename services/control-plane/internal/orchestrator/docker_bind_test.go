package orchestrator

import (
	"os"
	"testing"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
)

func TestDockerBindOrchestrator(t *testing.T) {
	RegisterFailHandler(Fail)
	RunSpecs(t, "DockerBindOrchestrator Suite")
}

var _ = Describe("DockerBindOrchestrator", func() {
	var orch *DockerBindOrchestrator

	BeforeEach(func() {
		os.Setenv("MOCK_DOCKER", "true")
	})

	AfterEach(func() {
		os.Unsetenv("MOCK_DOCKER")
	})

	Describe("NewDockerBindOrchestrator", func() {
		Context("in mock mode", func() {
			It("should create a non-nil orchestrator", func() {
				var err error
				orch, err = NewDockerBindOrchestrator("/var/run/docker.sock")
				Expect(err).NotTo(HaveOccurred())
				Expect(orch).NotTo(BeNil())
			})

			It("should set mock mode to true", func() {
				var err error
				orch, err = NewDockerBindOrchestrator("/var/run/docker.sock")
				Expect(err).NotTo(HaveOccurred())
				Expect(orch.mockMode).To(BeTrue())
			})
		})
	})

	Describe("CreateContainer", func() {
		BeforeEach(func() {
			var err error
			orch, err = NewDockerBindOrchestrator("/var/run/docker.sock")
			Expect(err).NotTo(HaveOccurred())
		})

		It("should create a container in mock mode", func() {
			config := ContainerConfig{
				RunID:         "test-run-123",
				RepositoryURL: "https://github.com/test/repo",
				Branch:        "main",
				Image:         "test-image:latest",
				EnvVars:       map[string]string{"TEST_VAR": "test-value"},
				ContainerName: "automated-run-test-run-123",
			}

			result, err := orch.CreateContainer(config)
			Expect(err).NotTo(HaveOccurred())
			Expect(result).NotTo(BeNil())
		})

		It("should return a non-empty container ID", func() {
			config := ContainerConfig{
				RunID:         "test-run-123",
				RepositoryURL: "https://github.com/test/repo",
				Branch:        "main",
				Image:         "test-image:latest",
				EnvVars:       map[string]string{"TEST_VAR": "test-value"},
				ContainerName: "automated-run-test-run-123",
			}

			result, err := orch.CreateContainer(config)
			Expect(err).NotTo(HaveOccurred())
			Expect(result.ContainerID).NotTo(BeEmpty())
		})

		It("should return running status", func() {
			config := ContainerConfig{
				RunID:         "test-run-123",
				RepositoryURL: "https://github.com/test/repo",
				Branch:        "main",
				Image:         "test-image:latest",
				EnvVars:       map[string]string{"TEST_VAR": "test-value"},
				ContainerName: "automated-run-test-run-123",
			}

			result, err := orch.CreateContainer(config)
			Expect(err).NotTo(HaveOccurred())
			Expect(result.Status).To(Equal("running"))
		})
	})

	Describe("StopContainer", func() {
		BeforeEach(func() {
			var err error
			orch, err = NewDockerBindOrchestrator("/var/run/docker.sock")
			Expect(err).NotTo(HaveOccurred())
		})

		It("should stop a container in mock mode", func() {
			err := orch.StopContainer("test-container-id")
			Expect(err).NotTo(HaveOccurred())
		})
	})

	Describe("RemoveContainer", func() {
		BeforeEach(func() {
			var err error
			orch, err = NewDockerBindOrchestrator("/var/run/docker.sock")
			Expect(err).NotTo(HaveOccurred())
		})

		It("should remove a container in mock mode", func() {
			err := orch.RemoveContainer("test-container-id")
			Expect(err).NotTo(HaveOccurred())
		})
	})

	Describe("GetContainerStatus", func() {
		BeforeEach(func() {
			var err error
			orch, err = NewDockerBindOrchestrator("/var/run/docker.sock")
			Expect(err).NotTo(HaveOccurred())
		})

		It("should get container status in mock mode", func() {
			status, err := orch.GetContainerStatus("test-container-id")
			Expect(err).NotTo(HaveOccurred())
			Expect(status).NotTo(BeNil())
		})

		It("should return the correct container ID", func() {
			status, err := orch.GetContainerStatus("test-container-id")
			Expect(err).NotTo(HaveOccurred())
			Expect(status.ContainerID).To(Equal("test-container-id"))
		})

		It("should return running as true", func() {
			status, err := orch.GetContainerStatus("test-container-id")
			Expect(err).NotTo(HaveOccurred())
			Expect(status.Running).To(BeTrue())
		})
	})
})
