package config

import (
	"os"
)

type Config struct {
	Port                string
	DatabaseURL         string
	JWTSecret           string
	Environment         string
	OrchestratorType    string
	DockerSocketPath    string
	KubeconfigPath      string
	KubernetesNamespace string
}

func Load() *Config {
	return &Config{
		Port:                getEnv("PORT", "8080"),
		DatabaseURL:         getEnv("DATABASE_URL", "postgres://agentic:agentic@localhost:5433/agentic?sslmode=disable"),
		JWTSecret:           getEnv("JWT_SECRET", "dev-secret-change-in-production"),
		Environment:         getEnv("ENVIRONMENT", "development"),
		OrchestratorType:    getEnv("ORCHESTRATOR_TYPE", "docker-bind"),
		DockerSocketPath:    getEnv("DOCKER_SOCKET_PATH", "/var/run/docker.sock"),
		KubeconfigPath:      getEnv("KUBECONFIG_PATH", ""),
		KubernetesNamespace: getEnv("KUBERNETES_NAMESPACE", "default"),
	}
}

func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}
