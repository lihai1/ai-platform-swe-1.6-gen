package orchestrator

import (
	"testing"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
)

func TestKubernetesOrchestrator(t *testing.T) {
	RegisterFailHandler(Fail)
	RunSpecs(t, "KubernetesOrchestrator Suite")
}

func TestDockerBindOrchestrator(t *testing.T) {
	RegisterFailHandler(Fail)
	RunSpecs(t, "DockerBindOrchestrator Suite")
}

func TestManager(t *testing.T) {
	RegisterFailHandler(Fail)
	RunSpecs(t, "Manager Suite")
}
