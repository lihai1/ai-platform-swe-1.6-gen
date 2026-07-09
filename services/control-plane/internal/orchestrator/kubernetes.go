package orchestrator

import (
	"context"
	"fmt"
	"os"
	"time"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
)

// KubernetesOrchestrator implements ContainerOrchestrator using Kubernetes API
type KubernetesOrchestrator struct {
	clientset      *kubernetes.Clientset
	namespace      string
	kubeconfigPath string
	mockMode       bool
}

// NewKubernetesOrchestrator creates a new Kubernetes orchestrator
func NewKubernetesOrchestrator(kubeconfigPath, namespace string) (*KubernetesOrchestrator, error) {
	mockMode := os.Getenv("MOCK_KUBERNETES") == "true"

	if namespace == "" {
		namespace = "default"
	}

	if mockMode {
		return &KubernetesOrchestrator{
			namespace: namespace,
			mockMode:  true,
		}, nil
	}

	var config *rest.Config
	var err error

	if kubeconfigPath != "" {
		// Use kubeconfig file
		config, err = clientcmd.BuildConfigFromFlags("", kubeconfigPath)
	} else {
		// Use in-cluster config
		config, err = rest.InClusterConfig()
	}

	if err != nil {
		return nil, fmt.Errorf("failed to create Kubernetes config: %w", err)
	}

	clientset, err := kubernetes.NewForConfig(config)
	if err != nil {
		return nil, fmt.Errorf("failed to create Kubernetes clientset: %w", err)
	}

	return &KubernetesOrchestrator{
		clientset:      clientset,
		namespace:      namespace,
		kubeconfigPath: kubeconfigPath,
		mockMode:       false,
	}, nil
}

// CreateContainer creates a new Kubernetes pod for the chat
func (k *KubernetesOrchestrator) CreateContainer(config ContainerConfig) (*ContainerResult, error) {
	if k.mockMode {
		return &ContainerResult{
			ContainerID: fmt.Sprintf("mock-pod-%s", config.RunID),
			Status:      "running",
		}, nil
	}

	// Build environment variables
	env := []corev1.EnvVar{
		{Name: "RUN_ID", Value: config.RunID},
		{Name: "REPOSITORY_URL", Value: config.RepositoryURL},
		{Name: "BRANCH", Value: config.Branch},
	}

	if config.Credentials != nil {
		env = append(env, corev1.EnvVar{Name: "GIT_USERNAME", Value: config.Credentials.Username})
		env = append(env, corev1.EnvVar{Name: "GIT_TOKEN", Value: config.Credentials.Token})
	}

	for k, v := range config.EnvVars {
		env = append(env, corev1.EnvVar{Name: k, Value: v})
	}

	// Create pod
	pod := &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name: config.RunID,
			Labels: map[string]string{
				"app":        "agentic-orchestrator",
				"run-id":     config.RunID,
				"managed-by": "control-plane",
			},
		},
		Spec: corev1.PodSpec{
			Containers: []corev1.Container{
				{
					Name:    "agent",
					Image:   config.Image,
					Command: []string{"/app/container-start.sh"},
					Env:     env,
				},
			},
			RestartPolicy: corev1.RestartPolicyNever,
		},
	}

	createdPod, err := k.clientset.CoreV1().Pods(k.namespace).Create(context.Background(), pod, metav1.CreateOptions{})
	if err != nil {
		return nil, fmt.Errorf("failed to create pod: %w", err)
	}

	// Wait for pod to be ready
	timeout := 5 * time.Minute
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	for {
		select {
		case <-ctx.Done():
			return nil, fmt.Errorf("timeout waiting for pod to be ready")
		default:
			pod, err := k.clientset.CoreV1().Pods(k.namespace).Get(context.Background(), createdPod.Name, metav1.GetOptions{})
			if err != nil {
				return nil, fmt.Errorf("failed to get pod status: %w", err)
			}

			if pod.Status.Phase == corev1.PodRunning {
				return &ContainerResult{
					ContainerID: pod.Name,
					Status:      "running",
				}, nil
			}

			if pod.Status.Phase == corev1.PodFailed || pod.Status.Phase == corev1.PodSucceeded {
				return nil, fmt.Errorf("pod terminated with phase: %s", pod.Status.Phase)
			}

			time.Sleep(2 * time.Second)
		}
	}
}

// StopContainer stops a running pod
func (k *KubernetesOrchestrator) StopContainer(containerID string) error {
	if k.mockMode {
		return nil
	}

	err := k.clientset.CoreV1().Pods(k.namespace).Delete(context.Background(), containerID, metav1.DeleteOptions{})
	if err != nil {
		return fmt.Errorf("failed to delete pod: %w", err)
	}

	return nil
}

// RemoveContainer removes a pod
func (k *KubernetesOrchestrator) RemoveContainer(containerID string) error {
	if k.mockMode {
		return nil
	}

	// In Kubernetes, StopContainer and RemoveContainer are the same operation (delete pod)
	// This is kept for interface compatibility
	return k.StopContainer(containerID)
}

// GetContainerStatus gets the status of a pod
func (k *KubernetesOrchestrator) GetContainerStatus(containerID string) (*ContainerStatus, error) {
	if k.mockMode {
		return &ContainerStatus{
			ContainerID: containerID,
			Status:      "running",
			Running:     true,
		}, nil
	}

	pod, err := k.clientset.CoreV1().Pods(k.namespace).Get(context.Background(), containerID, metav1.GetOptions{})
	if err != nil {
		return nil, fmt.Errorf("failed to get pod: %w", err)
	}

	status := string(pod.Status.Phase)
	running := pod.Status.Phase == corev1.PodRunning

	return &ContainerStatus{
		ContainerID: containerID,
		Status:      status,
		Running:     running,
	}, nil
}

// ExecInContainer executes a command inside a pod
func (k *KubernetesOrchestrator) ExecInContainer(containerID string, command []string) error {
	if k.mockMode {
		return nil
	}

	// Create exec request
	req := k.clientset.CoreV1().RESTClient().Post().
		Resource("pods").
		Namespace(k.namespace).
		Name(containerID).
		SubResource("exec").
		VersionedParams(&corev1.PodExecOptions{
			Command:   command,
			Container: "agent",
			Stdin:     false,
			Stdout:    true,
			Stderr:    true,
		}, metav1.ParameterCodec)

	exec, err := req.Stream(context.Background())
	if err != nil {
		return fmt.Errorf("failed to execute command: %w", err)
	}
	defer exec.Close()

	return nil
}
