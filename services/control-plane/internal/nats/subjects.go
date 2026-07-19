package nats

// Package nats provides centralized NATS subject constants for the control-plane service.
// This ensures consistency across the control-plane codebase and makes it easier to
// maintain NATS subject patterns.
//
// Control-plane primarily handles:
// - Control: agent.control.{run_id}.{action} - Container lifecycle commands
//
// Stream Names:
// - AGENT_CHAT: Chat and user events
// - AGENT_CONTROL: Control plane commands
// - AGENT_EVENTS: State events
// - AGENT_ERRORS: Error messages

// Control stream subjects
const (
	// ControlWildcardSubject matches all control messages for subscription
	ControlWildcardSubject = "agent.control.>"
)

// Stream names
const (
	// StreamAgentChat is the stream name for chat and user events
	StreamAgentChat = "AGENT_CHAT"
	// StreamAgentControl is the stream name for control plane commands
	StreamAgentControl = "AGENT_CONTROL"
	// StreamAgentEvents is the stream name for state events
	StreamAgentEvents = "AGENT_EVENTS"
	// StreamAgentErrors is the stream name for error messages
	StreamAgentErrors = "AGENT_ERRORS"
)

// AllStreams returns all known stream names for cleanup operations
func AllStreams() []string {
	return []string{
		StreamAgentChat,
		StreamAgentControl,
		StreamAgentEvents,
		StreamAgentErrors,
	}
}
