package integration_test

import (
	"os"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
)

// Helper function to get NATS connection
func getNATSConnection(t *testing.T) *nats.Conn {
	natsURL := os.Getenv("NATS_URL")
	if natsURL == "" {
		natsURL = "nats://localhost:4222"
	}

	nc, err := nats.Connect(natsURL)
	if err != nil {
		t.Fatalf("Failed to connect to NATS: %v", err)
	}

	// Wait for connection to be established
	time.Sleep(100 * time.Millisecond)

	return nc
}
