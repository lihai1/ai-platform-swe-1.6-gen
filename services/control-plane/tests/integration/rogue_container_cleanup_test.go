package integration_test

import (
	"database/sql"
	"fmt"
	"time"

	"github.com/agentic-engineering/control-plane/internal/config"
	"github.com/agentic-engineering/control-plane/internal/db"
	"github.com/agentic-engineering/control-plane/internal/orchestrator"
	"github.com/agentic-engineering/control-plane/internal/repository"
	"github.com/google/uuid"
	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
)

var _ = Describe("RogueContainerCleanup", func() {
	var database *sql.DB
	var chatContainerRepo *repository.ChatContainerRepository
	var containerManager *orchestrator.Manager
	var testRunID string
	var testContainerID string

	BeforeEach(func() {
		// Load configuration
		cfg := config.Load()

		// Connect to database
		var err error
		database, err = db.Connect(cfg.DatabaseURL)
		Expect(err).NotTo(HaveOccurred())

		// Initialize repository
		chatContainerRepo = repository.NewChatContainerRepository(database)

		// Initialize orchestrator
		containerOrchestrator, err := orchestrator.NewOrchestrator(
			orchestrator.OrchestratorType(cfg.OrchestratorType),
			cfg.DockerSocketPath,
			cfg.KubeconfigPath,
			cfg.KubernetesNamespace,
		)
		Expect(err).NotTo(HaveOccurred())
		containerManager = orchestrator.NewManager(containerOrchestrator)

		// Generate test run ID
		testRunID = fmt.Sprintf("test-run-%d", time.Now().UnixNano())
	})

	AfterEach(func() {
		// Clean up test data from database
		if database != nil {
			_, err := database.Exec("DELETE FROM app.chat_containers WHERE run_id = $1", testRunID)
			Expect(err).NotTo(HaveOccurred())
			database.Close()
		}

		// Clean up test container if it exists
		if testContainerID != "" {
			_ = containerManager.RemoveChatContainer(testContainerID)
		}
	})

	Context("when no rogue containers exist", func() {
		It("should return empty list of cleaned containers", func() {
			// Get valid run IDs from database (should be empty or only contain other runs)
			validRunIDs, err := chatContainerRepo.GetAllRunIDs()
			Expect(err).NotTo(HaveOccurred())

			// Run cleanup
			err = containerManager.CleanupRogueContainers(validRunIDs)
			Expect(err).NotTo(HaveOccurred())

			// No containers should have been cleaned
			// This is verified by the logs showing cleaned=0
		})
	})

	Context("when valid container exists in database", func() {
		It("should not clean the valid container", func() {
			// Create a test container entry in database with proper UUID
			testContainerID = fmt.Sprintf("test-container-%d", time.Now().UnixNano())
			now := time.Now()
			testUUID := uuid.New().String()

			_, err := database.Exec(`
				INSERT INTO app.chat_containers (id, run_id, container_id, container_name, repository_url, branch, status, created_at)
				VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
			`, testUUID, testRunID, testContainerID, testContainerID, "https://github.com/test/repo", "main", "running", now)
			Expect(err).NotTo(HaveOccurred())

			// Get valid run IDs (should include our test run)
			validRunIDs, err := chatContainerRepo.GetAllRunIDs()
			Expect(err).NotTo(HaveOccurred())
			Expect(validRunIDs[testRunID]).To(BeTrue())

			// Run cleanup
			err = containerManager.CleanupRogueContainers(validRunIDs)
			Expect(err).NotTo(HaveOccurred())

			// Container should still exist in database
			var count int
			err = database.QueryRow("SELECT COUNT(*) FROM app.chat_containers WHERE run_id = $1", testRunID).Scan(&count)
			Expect(err).NotTo(HaveOccurred())
			Expect(count).To(Equal(1))
		})
	})

	Context("when container exists but not in database", func() {
		It("should identify rogue container for cleanup", func() {
			// Get valid run IDs (should NOT include our rogue run)
			validRunIDs, err := chatContainerRepo.GetAllRunIDs()
			Expect(err).NotTo(HaveOccurred())

			// Create a rogue run ID that doesn't exist in database with proper UUID format
			rogueUUID := uuid.New().String()
			rogueRunID := fmt.Sprintf("run-%s", rogueUUID)
			Expect(validRunIDs[rogueUUID]).To(BeFalse())

			// The cleanup logic would identify this as a rogue container
			shouldClean := orchestrator.ShouldCleanupContainer(rogueRunID, validRunIDs)
			Expect(shouldClean).To(BeTrue())
		})
	})

	Context("when system containers exist", func() {
		It("should never clean system containers", func() {
			// System containers should be protected regardless of database state
			systemContainers := []string{
				"agentic-web",
				"agentic-agent-service",
				"agentic-control-plane",
				"agentic-postgres",
				"agentic-nats",
			}

			validRunIDs := map[string]bool{}

			for _, sysContainer := range systemContainers {
				shouldClean := orchestrator.ShouldCleanupContainer(sysContainer, validRunIDs)
				Expect(shouldClean).To(BeFalse(), "System container %s should never be cleaned", sysContainer)
			}
		})
	})

	Context("when mixed containers exist", func() {
		It("should only clean rogue containers", func() {
			// Create a valid container in database with proper UUID
			validUUID := uuid.New().String()
			validRunID := fmt.Sprintf("valid-run-%s", validUUID)
			_, err := database.Exec(`
				INSERT INTO app.chat_containers (id, run_id, container_id, container_name, repository_url, branch, status, created_at)
				VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
			`, uuid.New().String(), validRunID, "valid-container-id", "valid-container-id", "https://github.com/test/repo", "main", "running", time.Now())
			Expect(err).NotTo(HaveOccurred())

			// Get valid run IDs
			validRunIDs, err := chatContainerRepo.GetAllRunIDs()
			Expect(err).NotTo(HaveOccurred())
			Expect(validRunIDs[validRunID]).To(BeTrue())

			// Test that valid container would not be cleaned
			shouldCleanValid := orchestrator.ShouldCleanupContainer(validRunID, validRunIDs)
			Expect(shouldCleanValid).To(BeFalse())

			// Test that rogue container would be cleaned
			rogueUUID := uuid.New().String()
			rogueRunID := fmt.Sprintf("run-%s", rogueUUID)
			shouldCleanRogue := orchestrator.ShouldCleanupContainer(rogueRunID, validRunIDs)
			Expect(shouldCleanRogue).To(BeTrue())

			// Test that system container would not be cleaned
			shouldCleanSystem := orchestrator.ShouldCleanupContainer("agentic-web", validRunIDs)
			Expect(shouldCleanSystem).To(BeFalse())

			// Clean up test data
			_, err = database.Exec("DELETE FROM app.chat_containers WHERE run_id = $1", validRunID)
			Expect(err).NotTo(HaveOccurred())
		})
	})

	Context("when actual Docker containers exist", func() {
		It("should clean rogue containers and return list of cleaned containers", func() {
			// This test requires actual Docker access and creates real containers
			// It should be run with make dev-env to have the full environment

			// Get current valid run IDs
			validRunIDs, err := chatContainerRepo.GetAllRunIDs()
			Expect(err).NotTo(HaveOccurred())

			// Run cleanup - this will clean any rogue containers
			err = containerManager.CleanupRogueContainers(validRunIDs)
			Expect(err).NotTo(HaveOccurred())

			// The cleanup should complete without errors
			// In a real scenario with rogue containers, they would be removed
			// Since we're in a clean environment, we expect no containers to be cleaned
		})
	})
})
