package orchestrator

import (
	"os"
	"testing"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
)

func TestKubernetesOrchestrator(t *testing.T) {
	RegisterFailHandler(Fail)
	RunSpecs(t, "KubernetesOrchestrator Suite")
}

var _ = Describe("KubernetesOrchestrator", func() {
	var orch *KubernetesOrchestrator

	BeforeEach(func() {
		os.Setenv("MOCK_KUBERNETES", "true")
	})

	AfterEach(func() {
		os.Unsetenv("MOCK_KUBERNETES")
	})

	Describe("NewKubernetesOrchestrator", func() {
		Context("in mock mode", func() {
			It("should create a non-nil orchestrator", func() {
				var err error
				orch, err = NewKubernetesOrchestrator("", "default")
				Expect(err).NotTo(HaveOccurred())
				Expect(orch).NotTo(BeNil())
			})

			It("should set mock mode to true", func() {
				var err error
				orch, err = NewKubernetesOrchestrator("", "default")
				Expect(err).NotTo(HaveOccurred())
				Expect(orch.mockMode).To(BeTrue())
			})
		})

		Context("with default namespace", func() {
			It("should use default namespace when empty string provided", func() {
				var err error
				orch, err = NewKubernetesOrchestrator("", "")
				Expect(err).NotTo(HaveOccurred())
				Expect(orch.namespace).To(Equal("default"))
			})
		})

		Context("with custom namespace", func() {
			It("should use the provided namespace", func() {
				var err error
				orch, err = NewKubernetesOrchestrator("", "test-namespace")
				Expect(err).NotTo(HaveOccurred())
				Expect(orch.namespace).To(Equal("test-namespace"))
			})
		})
	})

	Describe("CreateContainer", func() {
		BeforeEach(func() {
			var err error
			orch, err = NewKubernetesOrchestrator("", "default")
			Expect(err).NotTo(HaveOccurred())
		})

		It("should create a container in mock mode", func() {
			config := ContainerConfig{
				RunID:         "test-run-123",
				RepositoryURL: "https://github.com/test/repo",
				Branch:        "main",
				Image:         "test-image:latest",
				EnvVars:       map[string]string{"TEST_VAR": "test-value"},
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
			}

			result, err := orch.CreateContainer(config)
			Expect(err).NotTo(HaveOccurred())
			Expect(result.Status).To(Equal("running"))
		})
	})

	Describe("StopContainer", func() {
		BeforeEach(func() {
			var err error
			orch, err = NewKubernetesOrchestrator("", "default")
			Expect(err).NotTo(HaveOccurred())
		})

		It("should stop a container in mock mode", func() {
			err := orch.StopContainer("test-pod-id")
			Expect(err).NotTo(HaveOccurred())
		})
	})

	Describe("RemoveContainer", func() {
		BeforeEach(func() {
			var err error
			orch, err = NewKubernetesOrchestrator("", "default")
			Expect(err).NotTo(HaveOccurred())
		})

		It("should remove a container in mock mode", func() {
			err := orch.RemoveContainer("test-pod-id")
			Expect(err).NotTo(HaveOccurred())
		})
	})

	Describe("GetContainerStatus", func() {
		BeforeEach(func() {
			var err error
			orch, err = NewKubernetesOrchestrator("", "default")
			Expect(err).NotTo(HaveOccurred())
		})

		It("should get container status in mock mode", func() {
			status, err := orch.GetContainerStatus("test-pod-id")
			Expect(err).NotTo(HaveOccurred())
			Expect(status).NotTo(BeNil())
		})

		It("should return the correct container ID", func() {
			status, err := orch.GetContainerStatus("test-pod-id")
			Expect(err).NotTo(HaveOccurred())
			Expect(status.ContainerID).To(Equal("test-pod-id"))
		})

		It("should return running as true", func() {
			status, err := orch.GetContainerStatus("test-pod-id")
			Expect(err).NotTo(HaveOccurred())
			Expect(status.Running).To(BeTrue())
		})
	})
})
