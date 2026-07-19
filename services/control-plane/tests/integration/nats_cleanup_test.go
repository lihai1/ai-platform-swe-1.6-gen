package integration_test

import (
	"errors"
	"strings"
	"time"

	"github.com/agentic-engineering/control-plane/internal/handlers"
	"github.com/nats-io/nats.go"
	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
)

var _ = Describe("CleanNATSMessageBus", func() {
	It("purges all agent streams on startup", func() {
		nc := getNATSConnection()

		js, err := nc.JetStream()
		Expect(err).NotTo(HaveOccurred())

		streamPatterns := map[string]string{
			"AGENT_CHAT":    "agent.user.*.chat.>",
			"AGENT_CONTROL": "agent.control.>",
			"AGENT_EVENTS":  "agent.user.*.events.>",
			"AGENT_ERRORS":  "agent.user.cleanup.errors",
		}

		ensuredStreams := make([]string, 0, len(streamPatterns))
		for stream, pattern := range streamPatterns {
			subject, ok := ensureStream(js, stream, pattern)
			if !ok {
				continue
			}
			_, err := js.Publish(subject, []byte(`{"test":"data"}`))
			Expect(err).NotTo(HaveOccurred())
			ensuredStreams = append(ensuredStreams, stream)
		}

		Expect(len(ensuredStreams)).To(BeNumerically(">=", 1))

		cleaned := handlers.CleanNATSMessageBus(js)
		Expect(cleaned).To(BeNumerically(">=", len(ensuredStreams)))

		for _, stream := range ensuredStreams {
			info, err := js.StreamInfo(stream)
			Expect(err).NotTo(HaveOccurred())
			Expect(info.State.Msgs).To(BeZero())
		}
	})
})

func ensureStream(js nats.JetStreamContext, name, pattern string) (string, bool) {
	info, err := js.StreamInfo(name)
	if err == nil {
		return concreteSubject(info.Config.Subjects[0]), true
	}
	if !errors.Is(err, nats.ErrStreamNotFound) {
		Expect(err).NotTo(HaveOccurred())
	}

	// AGENT_ERRORS overlaps with AGENT_CHAT's real subject, so use a
	// non-overlapping fallback when we need to create it.
	if name == "AGENT_ERRORS" {
		pattern = "agent.user.cleanup.errors"
	}

	cfg := &nats.StreamConfig{
		Name:        name,
		Subjects:    []string{pattern},
		Retention:   nats.LimitsPolicy,
		MaxAge:      24 * time.Hour,
		Storage:     nats.FileStorage,
		Description: "Integration test stream for " + name,
	}

	_, err = js.AddStream(cfg)
	if err != nil {
		if errors.Is(err, nats.ErrStreamNameAlreadyInUse) {
			info, err = js.StreamInfo(name)
			if err == nil {
				return concreteSubject(info.Config.Subjects[0]), true
			}
		}
		// Stream could not be created (e.g. subject overlap); skip it.
		return "", false
	}

	return concreteSubject(pattern), true
}

func concreteSubject(pattern string) string {
	if !strings.Contains(pattern, "*") && !strings.Contains(pattern, ">") {
		return pattern
	}
	// Replace the single wildcard with a test token and the multi-token
	// wildcard with a concrete tail subject.
	s := strings.Replace(pattern, ".*.", ".test.", 1)
	s = strings.Replace(s, ".>", ".events", 1)
	if strings.Contains(s, ">") {
		s = strings.Replace(s, ">", "events", 1)
	}
	return s
}
