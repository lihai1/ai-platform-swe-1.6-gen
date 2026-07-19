package service

import (
	"fmt"
	"log"

	"github.com/agentic-engineering/control-plane/internal/models"
	"github.com/agentic-engineering/control-plane/internal/orchestrator"
	"github.com/agentic-engineering/control-plane/internal/repository"
)

type ChatContainerService struct {
	containerRepo *repository.ChatContainerRepository
	repoRepo      *repository.RepositoryRepository
	manager       *orchestrator.Manager
}

func NewChatContainerService(
	containerRepo *repository.ChatContainerRepository,
	repoRepo *repository.RepositoryRepository,
	manager *orchestrator.Manager,
) *ChatContainerService {
	return &ChatContainerService{
		containerRepo: containerRepo,
		repoRepo:      repoRepo,
		manager:       manager,
	}
}

// resolveRepository fetches repository URL and branch when a repository ID is provided.
func (s *ChatContainerService) resolveRepository(repositoryID, runID string) (string, string, error) {
	if repositoryID == "" {
		log.Printf("No repository_id provided for run %s, creating container without repository", runID)
		return "", "", nil
	}

	repo, err := s.repoRepo.Get(repositoryID)
	if err != nil {
		return "", "", fmt.Errorf("failed to get repository: %w", err)
	}
	return repo.GitURL, repo.Branch, nil
}

// toChatContainer builds a ChatContainer model from orchestrator output and repository details.
func (s *ChatContainerService) toChatContainer(containerInfo *orchestrator.ChatContainerInfo, runID, repositoryURL, branch string) *models.ChatContainer {
	return &models.ChatContainer{
		ID:            containerInfo.ID,
		RunID:         runID,
		ContainerID:   containerInfo.ContainerID,
		ContainerName: containerInfo.ContainerName,
		RepositoryURL: repositoryURL,
		Branch:        branch,
		Status:        containerInfo.Status,
		CreatedAt:     containerInfo.CreatedAt,
	}
}

// CreateContainerForAgentType creates and persists a chat container for the given agent type.
func (s *ChatContainerService) CreateContainerForAgentType(
	agentType string,
	repoConfig orchestrator.RepositoryConfig,
	llmConfig orchestrator.LLMConfig,
	runParams *orchestrator.RunParameters,
) (*models.ChatContainer, error) {
	runID := repoConfig.RunID
	repositoryURL, branch, err := s.resolveRepository(repoConfig.RepositoryID, runID)
	if err != nil {
		return nil, err
	}

	repoConfig.RepositoryURL = repositoryURL
	repoConfig.Branch = branch

	containerInfo, err := s.manager.CreateContainerForAgentType(agentType, repoConfig, llmConfig, runParams)
	if err != nil {
		return nil, fmt.Errorf("failed to create %s container: %w", agentType, err)
	}

	container := s.toChatContainer(containerInfo, runID, repositoryURL, branch)
	if err := s.containerRepo.Create(container); err != nil {
		return nil, fmt.Errorf("failed to save chat container: %w", err)
	}

	return container, nil
}

// CreateSpecialistAgentContainer creates a container for specialist agent (multi-agent) mode
func (s *ChatContainerService) CreateSpecialistAgentContainer(repoConfig orchestrator.RepositoryConfig, llmConfig orchestrator.LLMConfig) (*models.ChatContainer, error) {
	return s.CreateContainerForAgentType("specialist", repoConfig, llmConfig, nil)
}

// CreateSingleAgentContainer creates a container for single-agent mode
func (s *ChatContainerService) CreateSingleAgentContainer(repoConfig orchestrator.RepositoryConfig, llmConfig orchestrator.LLMConfig) (*models.ChatContainer, error) {
	return s.CreateContainerForAgentType("single-agent", repoConfig, llmConfig, nil)
}

func (s *ChatContainerService) GetContainer(runID string) (*models.ChatContainer, error) {
	return s.containerRepo.GetByRunID(runID)
}

func (s *ChatContainerService) StopContainer(runID string) error {
	container, err := s.containerRepo.GetByRunID(runID)
	if err != nil {
		return fmt.Errorf("failed to get chat container: %w", err)
	}

	// Stop container via orchestrator
	if err := s.manager.StopChatContainer(container.ContainerID); err != nil {
		return fmt.Errorf("failed to stop container: %w", err)
	}

	// Update database
	if err := s.containerRepo.MarkStopped(container.ID); err != nil {
		return fmt.Errorf("failed to mark container as stopped: %w", err)
	}

	return nil
}

func (s *ChatContainerService) RemoveContainer(runID string) error {
	container, err := s.containerRepo.GetByRunID(runID)
	if err != nil {
		return fmt.Errorf("failed to get chat container: %w", err)
	}

	// Remove container via orchestrator
	if err := s.manager.RemoveChatContainer(container.ContainerID); err != nil {
		return fmt.Errorf("failed to remove container: %w", err)
	}

	// Delete from database
	if err := s.containerRepo.Delete(container.ID); err != nil {
		return fmt.Errorf("failed to delete chat container: %w", err)
	}

	return nil
}

func (s *ChatContainerService) ListContainers() ([]*models.ChatContainer, error) {
	return s.containerRepo.List()
}

// CreateSpecialistAgentContainerWithParams creates a container for specialist agent (multi-agent) mode with run parameters
func (s *ChatContainerService) CreateSpecialistAgentContainerWithParams(repoConfig orchestrator.RepositoryConfig, llmConfig orchestrator.LLMConfig, runParams orchestrator.RunParameters) (*models.ChatContainer, error) {
	return s.CreateContainerForAgentType("specialist", repoConfig, llmConfig, &runParams)
}

// CreateSingleAgentContainerWithParams creates a container for single-agent mode with run parameters
func (s *ChatContainerService) CreateSingleAgentContainerWithParams(repoConfig orchestrator.RepositoryConfig, llmConfig orchestrator.LLMConfig, runParams orchestrator.RunParameters) (*models.ChatContainer, error) {
	return s.CreateContainerForAgentType("single-agent", repoConfig, llmConfig, &runParams)
}

// CreateCrewAIContainerWithParams creates a container for CrewAI mode with run parameters
func (s *ChatContainerService) CreateCrewAIContainerWithParams(repoConfig orchestrator.RepositoryConfig, llmConfig orchestrator.LLMConfig, runParams orchestrator.RunParameters) (*models.ChatContainer, error) {
	return s.CreateContainerForAgentType("crewai", repoConfig, llmConfig, &runParams)
}

// CreateCrewAIExpertContainerWithParams creates a container for the CrewAI expert worker with run parameters
func (s *ChatContainerService) CreateCrewAIExpertContainerWithParams(repoConfig orchestrator.RepositoryConfig, llmConfig orchestrator.LLMConfig, runParams orchestrator.RunParameters) (*models.ChatContainer, error) {
	return s.CreateContainerForAgentType("crewai-expert", repoConfig, llmConfig, &runParams)
}
