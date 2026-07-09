package repository

import (
	"database/sql"
	"fmt"
	"time"

	"github.com/agentic-engineering/control-plane/internal/models"
)

type ChatContainerRepository struct {
	db *sql.DB
}

func NewChatContainerRepository(db *sql.DB) *ChatContainerRepository {
	return &ChatContainerRepository{db: db}
}

func (r *ChatContainerRepository) Create(container *models.ChatContainer) error {
	query := `
		INSERT INTO app.chat_containers (id, run_id, container_id, container_name, repository_url, branch, status, created_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
	`
	_, err := r.db.Exec(query, container.ID, container.RunID, container.ContainerID, container.ContainerName, container.RepositoryURL, container.Branch, container.Status, container.CreatedAt)
	if err != nil {
		return fmt.Errorf("failed to create chat container: %w", err)
	}
	return nil
}

func (r *ChatContainerRepository) GetByRunID(runID string) (*models.ChatContainer, error) {
	query := `
		SELECT id, run_id, container_id, container_name, repository_url, branch, status, created_at, stopped_at
		FROM app.chat_containers
		WHERE run_id = $1
	`
	var container models.ChatContainer
	var stoppedAt sql.NullTime
	err := r.db.QueryRow(query, runID).Scan(
		&container.ID,
		&container.RunID,
		&container.ContainerID,
		&container.ContainerName,
		&container.RepositoryURL,
		&container.Branch,
		&container.Status,
		&container.CreatedAt,
		&stoppedAt,
	)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("chat container not found")
		}
		return nil, fmt.Errorf("failed to get chat container: %w", err)
	}
	if stoppedAt.Valid {
		container.StoppedAt = &stoppedAt.Time
	}
	return &container, nil
}

func (r *ChatContainerRepository) UpdateStatus(id, status string) error {
	query := `
		UPDATE app.chat_containers
		SET status = $1
		WHERE id = $2
	`
	_, err := r.db.Exec(query, status, id)
	if err != nil {
		return fmt.Errorf("failed to update chat container status: %w", err)
	}
	return nil
}

func (r *ChatContainerRepository) MarkStopped(id string) error {
	now := time.Now()
	query := `
		UPDATE app.chat_containers
		SET status = 'stopped', stopped_at = $1
		WHERE id = $2
	`
	_, err := r.db.Exec(query, now, id)
	if err != nil {
		return fmt.Errorf("failed to mark chat container as stopped: %w", err)
	}
	return nil
}

func (r *ChatContainerRepository) Delete(id string) error {
	query := `DELETE FROM app.chat_containers WHERE id = $1`
	_, err := r.db.Exec(query, id)
	if err != nil {
		return fmt.Errorf("failed to delete chat container: %w", err)
	}
	return nil
}

func (r *ChatContainerRepository) List() ([]*models.ChatContainer, error) {
	query := `
		SELECT id, run_id, container_id, container_name, repository_url, branch, status, created_at, stopped_at
		FROM app.chat_containers
		ORDER BY created_at DESC
	`
	rows, err := r.db.Query(query)
	if err != nil {
		return nil, fmt.Errorf("failed to list chat containers: %w", err)
	}
	defer rows.Close()

	var containers []*models.ChatContainer
	for rows.Next() {
		var container models.ChatContainer
		var stoppedAt sql.NullTime
		err := rows.Scan(
			&container.ID,
			&container.RunID,
			&container.ContainerID,
			&container.ContainerName,
			&container.RepositoryURL,
			&container.Branch,
			&container.Status,
			&container.CreatedAt,
			&stoppedAt,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan chat container: %w", err)
		}
		if stoppedAt.Valid {
			container.StoppedAt = &stoppedAt.Time
		}
		containers = append(containers, &container)
	}
	return containers, nil
}
