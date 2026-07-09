package service

import (
	"fmt"
	"strings"

	"github.com/agentic-engineering/control-plane/internal/models"
	"github.com/agentic-engineering/control-plane/internal/repository"
)

type ProjectService struct {
	projectRepo *repository.ProjectRepository
	orgRepo     *repository.OrganizationRepository
	userRepo    *repository.UserRepository
}

func NewProjectService(projectRepo *repository.ProjectRepository, orgRepo *repository.OrganizationRepository, userRepo *repository.UserRepository) *ProjectService {
	return &ProjectService{
		projectRepo: projectRepo,
		orgRepo:     orgRepo,
		userRepo:    userRepo,
	}
}

func (s *ProjectService) ListProjects() ([]*models.Project, error) {
	return s.projectRepo.List()
}

func (s *ProjectService) CreateProject(orgID, name, description string) (*models.Project, error) {
	// If no organization provided, find-or-create the default one
	if orgID == "" {
		existing, err := s.orgRepo.GetBySlug("default")
		if err == nil {
			orgID = existing.ID
		} else {
			defaultOrg := &models.Organization{
				Name: "Default Organization",
				Slug: "default",
			}
			org, err := s.orgRepo.Create(defaultOrg)
			if err != nil {
				// If it's a duplicate key error, the org already exists - try to get it again
				if strings.Contains(err.Error(), "duplicate key") || strings.Contains(err.Error(), "unique constraint") {
					existing, retryErr := s.orgRepo.GetBySlug("default")
					if retryErr == nil {
						orgID = existing.ID
					} else {
						return nil, fmt.Errorf("failed to get default organization after duplicate error: %w", retryErr)
					}
				} else {
					return nil, fmt.Errorf("failed to create default organization: %w", err)
				}
			} else {
				orgID = org.ID
			}
		}
	}

	project := &models.Project{
		OrganizationID: orgID,
		Name:           name,
		Description:    description,
	}
	return s.projectRepo.Create(project)
}

func (s *ProjectService) GetProject(id string) (*models.Project, error) {
	return s.projectRepo.Get(id)
}

func (s *ProjectService) UpdateProject(id, name, description string) (*models.Project, error) {
	project, err := s.projectRepo.Get(id)
	if err != nil {
		return nil, err
	}
	project.Name = name
	project.Description = description
	return s.projectRepo.Update(project)
}

func (s *ProjectService) DeleteProject(id string) error {
	return s.projectRepo.Delete(id)
}
