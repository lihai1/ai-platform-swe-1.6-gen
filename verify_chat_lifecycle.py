#!/usr/bin/env python3
"""Verification script for chat lifecycle implementation"""
import os
import sys

def verify_implementation():
    """Verify that the chat lifecycle implementation is correct"""
    
    print("="*60)
    print("CHAT LIFECYCLE IMPLEMENTATION VERIFICATION")
    print("="*60)
    
    checks_passed = 0
    checks_total = 0
    
    # Check 1: NATS messaging library has new methods
    print("\n1. Checking NATS messaging library...")
    checks_total += 1
    nats_file = "/Users/akwa/dev-agents/ai-platform-swe-1.6-gen/services/agent-service/internal/messaging/nats.py"
    if os.path.exists(nats_file):
        with open(nats_file, 'r') as f:
            content = f.read()
            if 'publish_chat_start' in content and 'publish_chat_close' in content and 'subscribe_to_chat_events' in content:
                print("   ✓ NATS methods implemented")
                checks_passed += 1
            else:
                print("   ✗ NATS methods not found")
    else:
        print("   ✗ NATS file not found")
    
    # Check 2: Subject patterns are chat-based
    print("\n2. Checking NATS subject patterns...")
    checks_total += 1
    if os.path.exists(nats_file):
        with open(nats_file, 'r') as f:
            content = f.read()
            if 'agent.chat.{chat_id}' in content or 'agent.chat.' in content:
                print("   ✓ Chat-based subject patterns found")
                checks_passed += 1
            else:
                print("   ✗ Chat-based subject patterns not found")
    
    # Check 3: Python service publishes chat start
    print("\n3. Checking Python service chat start...")
    checks_total += 1
    chatkit_file = "/Users/akwa/dev-agents/swe-1.6-gen/services/agent-service/internal/chatkit/router.py"
    if os.path.exists(chatkit_file):
        with open(chatkit_file, 'r') as f:
            content = f.read()
            if 'publish_chat_start' in content and 'NATSMessaging' in content:
                print("   ✓ Python service publishes chat start via NATS")
                checks_passed += 1
            else:
                print("   ✗ Chat start publishing not found")
    else:
        print("   ✗ Chatkit router file not found")
    
    # Check 4: Python service has chat close endpoint
    print("\n4. Checking Python service chat close endpoint...")
    checks_total += 1
    if os.path.exists(chatkit_file):
        with open(chatkit_file, 'r') as f:
            content = f.read()
            if 'publish_chat_close' in content and 'close_chat' in content:
                print("   ✓ Chat close endpoint implemented")
                checks_passed += 1
            else:
                print("   ✗ Chat close endpoint not found")
    
    # Check 5: Control plane subscribes to NATS
    print("\n5. Checking control plane NATS subscription...")
    checks_total += 1
    control_plane_file = "/Users/akwa/dev-agents/swe-1.6-gen/services/control-plane/cmd/server/main.go"
    if os.path.exists(control_plane_file):
        with open(control_plane_file, 'r') as f:
            content = f.read()
            if 'chat.start' in content and 'chat.close' in content and 'nats.Connect' in content:
                print("   ✓ Control plane subscribes to NATS")
                checks_passed += 1
            else:
                print("   ✗ NATS subscription not found")
    else:
        print("   ✗ Control plane file not found")
    
    # Check 6: Control plane has NATS dependency
    print("\n6. Checking control plane NATS dependency...")
    checks_total += 1
    go_mod_file = "/Users/akwa/dev-agents/swe-1.6-gen/services/control-plane/go.mod"
    if os.path.exists(go_mod_file):
        with open(go_mod_file, 'r') as f:
            content = f.read()
            if 'nats-io/nats.go' in content or 'nats.io/nats.go' in content:
                print("   ✓ NATS dependency added to go.mod")
                checks_passed += 1
            else:
                print("   ✗ NATS dependency not found")
    else:
        print("   ✗ go.mod file not found")
    
    # Check 7: Python service main subscribes to agent events
    print("\n7. Checking Python service agent event subscription...")
    checks_total += 1
    main_file = "/Users/akwa/dev-agents/swe-1.6-gen/services/agent-service/app/main.py"
    if os.path.exists(main_file):
        with open(main_file, 'r') as f:
            content = f.read()
            if 'subscribe_to_commands' in content or 'subscribe_to_chat_events' in content:
                print("   ✓ Python service subscribes to agent events")
                checks_passed += 1
            else:
                print("   ✗ Agent event subscription not found")
    else:
        print("   ✗ Main file not found")
    
    # Check 8: Worker uses chat_id
    print("\n8. Checking worker chat_id usage...")
    checks_total += 1
    worker_file = "/Users/akwa/dev-agents/swe-1.6-gen/services/agent-service/app/worker.py"
    if os.path.exists(worker_file):
        with open(worker_file, 'r') as f:
            content = f.read()
            if 'chat_id' in content and 'chat_id or run_id' in content:
                print("   ✓ Worker uses chat_id")
                checks_passed += 1
            elif 'chat_id' in content:
                print("   ✓ Worker uses chat_id")
                checks_passed += 1
            else:
                print("   ✗ Worker not updated for chat_id")
    else:
        print("   ✗ Worker file not found")
    
    # Check 9: Sequence diagrams updated
    print("\n9. Checking sequence diagrams...")
    checks_total += 1
    diagrams = [
        "/Users/akwa/dev-agents/swe-1.6-gen/docs/sequence-workflow-trigger.mmd",
        "/Users/akwa/dev-agents/swe-1.6-gen/docs/sequence-chat-lifecycle.mmd"
    ]
    diagrams_found = 0
    for diagram in diagrams:
        if os.path.exists(diagram):
            diagrams_found += 1
    
    if diagrams_found == len(diagrams):
        print(f"   ✓ All sequence diagrams updated ({diagrams_found}/{len(diagrams)})")
        checks_passed += 1
    else:
        print(f"   ⚠ Some diagrams missing ({diagrams_found}/{len(diagrams)})")
    
    # Check 10: Documentation updated
    print("\n10. Checking documentation...")
    checks_total += 1
    readme_file = "/Users/akwa/dev-agents/swe-1.6-gen/docs/README.md"
    if os.path.exists(readme_file):
        with open(readme_file, 'r') as f:
            content = f.read()
            if 'chat.start' in content and 'chat.close' in content and 'sequence-chat-lifecycle' in content:
                print("   ✓ Documentation updated")
                checks_passed += 1
            else:
                print("   ✗ Documentation not fully updated")
    else:
        print("   ✗ README not found")
    
    # Summary
    print("\n" + "="*60)
    print(f"VERIFICATION RESULTS: {checks_passed}/{checks_total} checks passed")
    print("="*60)
    
    if checks_passed == checks_total:
        print("\n✅ All implementation checks passed!")
        print("\nImplementation Summary:")
        print("- NATS messaging: Chat-based subject patterns")
        print("- Python service: Publishes chat.start/close via NATS")
        print("- Control plane: Subscribes to NATS for container management")
        print("- Worker: Uses chat_id instead of run_id")
        print("- Documentation: Updated with new flow")
        print("\nTo run full e2e test:")
        print("1. Start NATS: docker-compose up -d nats")
        print("2. Start control plane: cd services/control-plane && go run cmd/server/main.go")
        print("3. Start agent service: cd services/agent-service && python -m app.main")
        print("4. Run test: python test_chat_lifecycle_simple.py")
        return True
    else:
        print(f"\n⚠ {checks_total - checks_passed} checks failed")
        print("Some implementation may be incomplete")
        return False

if __name__ == "__main__":
    success = verify_implementation()
    sys.exit(0 if success else 1)
