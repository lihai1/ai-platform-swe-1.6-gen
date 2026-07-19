package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"os/exec"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/agentic-engineering/control-plane/internal/config"
	"github.com/agentic-engineering/control-plane/internal/db"
	"github.com/agentic-engineering/control-plane/internal/handlers"
	"github.com/agentic-engineering/control-plane/internal/middleware"
	"github.com/agentic-engineering/control-plane/internal/orchestrator"
	"github.com/agentic-engineering/control-plane/internal/repository"
	"github.com/agentic-engineering/control-plane/internal/service"
	"github.com/gorilla/mux"
	"github.com/nats-io/nats.go"
)

func main() {
	cfg := config.Load()

	database, err := db.Connect(cfg.DatabaseURL)
	if err != nil {
		log.Fatalf("Failed to connect to database: %v", err)
	}
	defer database.Close()

	// Run migrations
	log.Println("Running database migrations...")
	migrateCmd := exec.Command("migrate", "-path", "./migrations", "-database", cfg.DatabaseURL, "up")
	migrateCmd.Stdout = os.Stdout
	migrateCmd.Stderr = os.Stderr
	if err := migrateCmd.Run(); err != nil {
		log.Printf("Migration failed (may already be applied): %v", err)
	} else {
		log.Println("Migrations completed successfully")
	}

	// Initialize repositories
	userRepo := repository.NewUserRepository(database)
	orgRepo := repository.NewOrganizationRepository(database)
	projectRepo := repository.NewProjectRepository(database)
	repoRepo := repository.NewRepositoryRepository(database)
	chatContainerRepo := repository.NewChatContainerRepository(database)

	// Initialize orchestrator
	containerOrchestrator, err := orchestrator.NewOrchestrator(
		orchestrator.OrchestratorType(cfg.OrchestratorType),
		cfg.DockerSocketPath,
		cfg.KubeconfigPath,
		cfg.KubernetesNamespace,
	)
	if err != nil {
		log.Fatalf("Failed to create orchestrator: %v", err)
	}
	containerManager := orchestrator.NewManager(containerOrchestrator)

	log.Printf("Initialized orchestrator: type=%s, docker_socket=%s, kubernetes_namespace=%s",
		cfg.OrchestratorType, cfg.DockerSocketPath, cfg.KubernetesNamespace)

	// Clean up rogue containers on startup
	// This removes orphaned containers from previous runs that are no longer in the database
	log.Println("INFO: Starting orphaned container cleanup on startup...")
	validRunIDs, err := chatContainerRepo.GetAllRunIDs()
	if err != nil {
		log.Printf("WARN: Failed to get valid run IDs from database, skipping container cleanup: %v", err)
	} else {
		log.Printf("INFO: Found %d valid run IDs in database", len(validRunIDs))
		if err := containerManager.CleanupRogueContainers(validRunIDs); err != nil {
			log.Printf("WARN: Container cleanup encountered errors (startup will continue): %v", err)
		}
	}
	log.Println("INFO: Container cleanup completed")

	// Initialize services
	authService := service.NewAuthService(cfg.JWTSecret, userRepo)
	projectService := service.NewProjectService(projectRepo, orgRepo, userRepo)
	repositoryService := service.NewRepositoryService(repoRepo, projectRepo)
	chatContainerService := service.NewChatContainerService(chatContainerRepo, repoRepo, containerManager)

	// Initialize handlers
	authHandler := handlers.NewAuthHandler(authService)
	projectHandler := handlers.NewProjectHandler(projectService)
	repositoryHandler := handlers.NewRepositoryHandler(repositoryService)
	// chatContainerHandler := handlers.NewChatContainerHandler(chatContainerService) // No longer needed with NATS
	healthHandler := handlers.NewHealthHandler()
	ollamaHandler := handlers.NewOllamaHandler(cfg.OllamaBaseURL)

	// Setup router
	r := mux.NewRouter()

	// Handle OPTIONS requests before any routing
	r.Use(func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
			if req.Method == "OPTIONS" {
				w.Header().Set("Access-Control-Allow-Origin", "*")
				w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
				w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")
				w.Header().Set("Access-Control-Max-Age", "86400")
				w.WriteHeader(http.StatusOK)
				return
			}
			next.ServeHTTP(w, req)
		})
	})

	// CORS middleware
	r.Use(middleware.CORSMiddleware)
	r.Use(middleware.LoggingMiddleware)

	// Health endpoints
	r.HandleFunc("/healthz", healthHandler.Health).Methods("GET")
	r.HandleFunc("/readyz", healthHandler.Ready).Methods("GET")

	// API routes
	api := r.PathPrefix("/api/v1").Subrouter()
	api.Use(middleware.AuthMiddleware(cfg.JWTSecret))

	// Auth routes (no auth required)
	r.HandleFunc("/api/v1/auth/login", authHandler.Login).Methods("POST")
	r.HandleFunc("/api/v1/auth/register", authHandler.Register).Methods("POST")
	r.HandleFunc("/api/v1/auth/me", authHandler.GetCurrentUser).Methods("GET")

	// Ollama routes (no auth required - public endpoint for model listing)
	r.HandleFunc("/api/v1/ollama/models", ollamaHandler.ListModels).Methods("GET", "OPTIONS")

	// Project routes
	api.HandleFunc("/projects", projectHandler.ListProjects).Methods("GET", "OPTIONS")
	api.HandleFunc("/projects", projectHandler.CreateProject).Methods("POST", "OPTIONS")
	api.HandleFunc("/projects/{id}", projectHandler.GetProject).Methods("GET", "OPTIONS")
	api.HandleFunc("/projects/{id}", projectHandler.UpdateProject).Methods("PUT", "OPTIONS")
	api.HandleFunc("/projects/{id}", projectHandler.DeleteProject).Methods("DELETE", "OPTIONS")

	// Repository routes
	api.HandleFunc("/repositories", repositoryHandler.ListRepositories).Methods("GET", "OPTIONS")
	api.HandleFunc("/repositories", repositoryHandler.CreateRepository).Methods("POST", "OPTIONS")
	api.HandleFunc("/repositories/{id}", repositoryHandler.GetRepository).Methods("GET", "OPTIONS")
	api.HandleFunc("/repositories/{id}", repositoryHandler.UpdateRepository).Methods("PUT", "OPTIONS")
	api.HandleFunc("/repositories/{id}", repositoryHandler.DeleteRepository).Methods("DELETE", "OPTIONS")

	// Initialize NATS client
	nc, err := nats.Connect(cfg.NATSURL)
	if err != nil {
		log.Fatalf("Failed to connect to NATS: %v", err)
	}
	defer nc.Close()

	// Initialize JetStream context for durable messaging
	js, err := nc.JetStream()
	if err != nil {
		log.Fatalf("Failed to initialize JetStream: %v", err)
	}

	// Clean the NATS message bus to avoid processing stale messages
	handlers.CleanNATSMessageBus(js)

	// Subscribe to chat start messages on agent.control.>
	_, err = nc.Subscribe("agent.control.>", func(msg *nats.Msg) {
		if strings.HasSuffix(msg.Subject, ".start") {
			handlers.HandleChatStart(msg, chatContainerService, containerManager, repoRepo, nc, js)
		} else if strings.HasSuffix(msg.Subject, ".close") {
			handlers.HandleChatClose(msg, chatContainerService, containerManager)
		} else if strings.HasSuffix(msg.Subject, ".resume") {
			handlers.HandleChatResume(msg, chatContainerService, containerManager, repoRepo, nc, js)
		}
	})
	if err != nil {
		log.Fatalf("Failed to subscribe to agent.control.>: %v", err)
	}

	log.Println("Subscribed to NATS agent.control.> (start/close/resume) subjects")

	// Wrap router with CORS handler that handles OPTIONS at server level
	handler := http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		// Set CORS headers for all requests
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")
		w.Header().Set("Access-Control-Max-Age", "86400")

		// Handle OPTIONS requests immediately for CORS preflight
		if req.Method == "OPTIONS" {
			w.WriteHeader(http.StatusOK)
			return
		}

		r.ServeHTTP(w, req)
	})

	srv := &http.Server{
		Addr:         ":" + cfg.Port,
		Handler:      handler,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 15 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	go func() {
		log.Printf("Server starting on port %s", cfg.Port)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Server failed: %v", err)
		}
	}()

	// Graceful shutdown
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	log.Println("Shutting down server...")
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	if err := srv.Shutdown(ctx); err != nil {
		log.Fatalf("Server forced to shutdown: %v", err)
	}

	log.Println("Server exited")
}
