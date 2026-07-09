package repository

import (
	"database/sql"
	"fmt"

	"github.com/agentic-engineering/control-plane/internal/models"
	"github.com/google/uuid"
)

type OrganizationRepository struct {
	db *sql.DB
}

func NewOrganizationRepository(db *sql.DB) *OrganizationRepository {
	return &OrganizationRepository{db: db}
}

func (r *OrganizationRepository) List() ([]*models.Organization, error) {
	query := `SELECT id, name, slug, created_at, updated_at FROM app.organizations`
	rows, err := r.db.Query(query)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var orgs []*models.Organization
	for rows.Next() {
		org := &models.Organization{}
		err := rows.Scan(&org.ID, &org.Name, &org.Slug, &org.CreatedAt, &org.UpdatedAt)
		if err != nil {
			return nil, err
		}
		orgs = append(orgs, org)
	}
	return orgs, nil
}

func (r *OrganizationRepository) Create(org *models.Organization) (*models.Organization, error) {
	org.ID = uuid.New().String()
	query := `INSERT INTO app.organizations (id, name, slug, created_at, updated_at) 
			  VALUES ($1, $2, $3, NOW(), NOW()) RETURNING created_at, updated_at`
	err := r.db.QueryRow(query, org.ID, org.Name, org.Slug).Scan(&org.CreatedAt, &org.UpdatedAt)
	if err != nil {
		return nil, fmt.Errorf("failed to create organization: %w", err)
	}
	return org, nil
}

func (r *OrganizationRepository) GetBySlug(slug string) (*models.Organization, error) {
	org := &models.Organization{}
	query := `SELECT id, name, slug, created_at, updated_at FROM app.organizations WHERE slug = $1`
	err := r.db.QueryRow(query, slug).Scan(&org.ID, &org.Name, &org.Slug, &org.CreatedAt, &org.UpdatedAt)
	if err != nil {
		return nil, err
	}
	return org, nil
}

func (r *OrganizationRepository) Get(id string) (*models.Organization, error) {
	org := &models.Organization{}
	query := `SELECT id, name, slug, created_at, updated_at FROM app.organizations WHERE id = $1`
	err := r.db.QueryRow(query, id).Scan(&org.ID, &org.Name, &org.Slug, &org.CreatedAt, &org.UpdatedAt)
	if err != nil {
		return nil, err
	}
	return org, nil
}
