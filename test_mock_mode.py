#!/usr/bin/env python3
"""Test script for mock mode e2e testing"""
import asyncio
import sys
import os

# Add the agent service to the path
sys.path.insert(0, '/Users/akwa/dev-agents/ai-platform-swe-1.6-gen/services/agent-service')

from internal.workflow.nodes import (
    scouting_node,
    planning_node,
    implementing_node,
    testing_node,
    reviewing_node,
    verifying_node,
)

async def test_mock_mode():
    """Test mock mode workflow nodes"""
    print("Testing mock mode workflow nodes...")
    
    # Test state with mock mode enabled
    state = {
        "chat_id": "test-chat-1",
        "user_id": "test-user",
        "task": "Add a new feature",
        "status": "CREATED",
        "current_phase": "CREATED",
        "mock_mode": True,
        "repair_count": 0,
        "max_repair_count": 2,
    }
    
    print("\n1. Testing scouting_node with mock_mode=True...")
    state = await scouting_node(state)
    print(f"   Repository summary: {state['repository_summary']}")
    assert state['repository_summary']['framework'] == 'Mock', "Scouting failed mock mode check"
    print("   ✓ Scouting node passed")
    
    print("\n2. Testing planning_node with mock_mode=True...")
    state = await planning_node(state)
    print(f"   Selected agents: {state['selected_agents']}")
    print(f"   Implementation plan: {state['implementation_plan']}")
    assert state['selected_agents'] == ['mock-developer'], "Planning failed mock mode check"
    print("   ✓ Planning node passed")
    
    print("\n3. Testing implementing_node with mock_mode=True...")
    state = await implementing_node(state)
    print(f"   Implementation results: {state['implementation_results']}")
    print(f"   Files modified: {state['code_diff'][:50]}...")
    assert state['implementation_results']['files_modified'] == 1, "Implementing failed mock mode check"
    print("   ✓ Implementing node passed")
    
    print("\n4. Testing testing_node with mock_mode=True...")
    state = await testing_node(state)
    print(f"   Test results: {state['test_results']}")
    assert state['test_results']['passed'] == 1, "Testing failed mock mode check"
    assert state['test_results']['failed'] == 0, "Testing should have no failures in mock mode"
    print("   ✓ Testing node passed")
    
    print("\n5. Testing reviewing_node with mock_mode=True...")
    state = await reviewing_node(state)
    print(f"   Review results: {state['review_results']}")
    assert state['review_results']['decision'] == 'approved', "Reviewing failed mock mode check"
    assert len(state['review_results']['findings']) == 0, "Reviewing should have no findings in mock mode"
    print("   ✓ Reviewing node passed")
    
    print("\n6. Testing verifying_node with mock_mode=True...")
    state = await verifying_node(state)
    print(f"   Verification results: {state['verification_results']}")
    assert state['verification_results']['accepted'] == True, "Verifying failed mock mode check"
    print("   ✓ Verifying node passed")
    
    print("\n✅ All mock mode tests passed!")
    return True

async def test_normal_mode():
    """Test normal mode workflow nodes"""
    print("\n\nTesting normal mode workflow nodes...")
    
    # Test state with mock mode disabled
    state = {
        "chat_id": "test-chat-2",
        "user_id": "test-user",
        "task": "Add a new feature",
        "status": "CREATED",
        "current_phase": "CREATED",
        "mock_mode": False,
        "repair_count": 0,
        "max_repair_count": 2,
    }
    
    print("\n1. Testing scouting_node with mock_mode=False...")
    state = await scouting_node(state)
    print(f"   Repository summary: {state['repository_summary']}")
    assert state['repository_summary']['framework'] == 'Gin', "Scouting failed normal mode check"
    print("   ✓ Scouting node passed")
    
    print("\n2. Testing planning_node with mock_mode=False...")
    state = await planning_node(state)
    print(f"   Selected agents: {state['selected_agents']}")
    assert state['selected_agents'] == ['go-developer', 'test-engineer'], "Planning failed normal mode check"
    print("   ✓ Planning node passed")
    
    print("\n3. Testing implementing_node with mock_mode=False...")
    state = await implementing_node(state)
    print(f"   Implementation results: {state['implementation_results']}")
    assert state['implementation_results']['files_modified'] == 2, "Implementing failed normal mode check"
    print("   ✓ Implementing node passed")
    
    print("\n4. Testing testing_node with mock_mode=False...")
    state = await testing_node(state)
    print(f"   Test results: {state['test_results']}")
    assert state['test_results']['total_tests'] == 8, "Testing failed normal mode check"
    print("   ✓ Testing node passed")
    
    print("\n5. Testing reviewing_node with mock_mode=False...")
    state = await reviewing_node(state)
    print(f"   Review results: {state['review_results']}")
    assert state['review_results']['decision'] == 'changes_required', "Reviewing failed normal mode check"
    print("   ✓ Reviewing node passed")
    
    print("\n6. Testing verifying_node with mock_mode=False (first iteration)...")
    state = await verifying_node(state)
    print(f"   Verification results: {state['verification_results']}")
    assert state['verification_results']['accepted'] == False, "Verifying should fail on first iteration in normal mode"
    print("   ✓ Verifying node passed (expected failure)")
    
    print("\n7. Testing repairing_node...")
    state = await repairing_node(state)
    print(f"   Repair count: {state['repair_count']}")
    assert state['repair_count'] == 1, "Repairing failed"
    print("   ✓ Repairing node passed")
    
    print("\n8. Testing verifying_node with mock_mode=False (after repair)...")
    state = await verifying_node(state)
    print(f"   Verification results: {state['verification_results']}")
    assert state['verification_results']['accepted'] == True, "Verifying should pass after repair in normal mode"
    print("   ✓ Verifying node passed")
    
    print("\n✅ All normal mode tests passed!")
    return True

async def main():
    """Run all tests"""
    try:
        await test_mock_mode()
        await test_normal_mode()
        print("\n" + "="*50)
        print("🎉 ALL TESTS PASSED!")
        print("="*50)
        return 0
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
