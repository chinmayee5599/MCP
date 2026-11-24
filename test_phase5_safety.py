"""Phase 5 Safety & Human Control Verification Suite

Tests the non-negotiable human control and safety architecture:
Scenario A: User approves -> transitions PROPOSED -> EXECUTING -> SUCCESS.
Scenario B: User rejects -> transitions PROPOSED -> REJECTED, no write tool executes.
Scenario C: User cancels -> transitions PROPOSED -> CANCELLED, proposal voided.
Scenario D: Tool fails after approval -> transitions EXECUTING -> FAILURE, retry enabled.
Scenario E: User clicks approve twice (Double-click / Idempotency) -> second click safely blocked.
Scenario F: Invalid / expired action is submitted -> rejected with safe validation error.
Scenario G: Transparency Disclosures & User Overrides -> all 5 required transparency fields verified.
"""

import sys
import time
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.agent import TenantShieldAgent, AgentStatus
from app.action_manager import action_manager, ActionLifecycleState, ActionManager
from app.main import (
    run_agent_audit,
    approve_agent_action,
    reject_agent_action,
    cancel_agent_action,
    get_action_details,
    AgentAuditRequest,
    HumanApprovalRequest,
)


def test_scenario_a_user_approves():
    print("\n--- Scenario A: User Approves (Full Controlled Execution) ---")
    agent = TenantShieldAgent()

    # Step 1: Run audit to stage action
    res = agent.run("Landlord in Los Angeles kept $800 25 days after move out.")
    assert res.status == AgentStatus.AWAITING_APPROVAL
    proposal = res.proposed_action
    assert proposal is not None
    assert proposal.action_id.startswith("act_")
    assert proposal.approved is False
    print(f"  [✓] Action proposed: {proposal.action_id} (Status: AWAITING_APPROVAL).")

    # Step 2: Verify all 5 Transparency Disclosures
    assert len(proposal.what) > 0, "Missing 'what' disclosure"
    assert len(proposal.why) > 0, "Missing 'why' disclosure"
    assert len(proposal.consequences_if_approved) > 0, "Missing 'consequences_if_approved' disclosure"
    assert len(proposal.what_will_not_happen) > 0, "Missing 'what_will_not_happen' disclosure"
    assert "will NOT automatically" in proposal.what_will_not_happen
    assert "dispute_amount" in proposal.data_involved
    print("  [✓] All 5 mandatory transparency disclosures verified.")

    # Step 3: User Approves with optional field overrides
    overrides = {
        "tenant_name": "Alice Johnson",
        "landlord_name": "Pacific View Management",
        "rental_address": "123 Ocean Blvd, Santa Monica, CA",
        "demand_deadline_days": 14,
    }
    exec_res = agent.execute_action(
        action_type=proposal.action_type,
        approved=True,
        user_overrides=overrides,
        action_id=proposal.action_id,
    )

    assert exec_res["success"] is True
    assert exec_res["status"] in ("SUCCESS", "AUTHORIZED_AND_COMPILED")
    assert exec_res["approved"] is True
    doc = exec_res["document"]
    assert "Alice Johnson" in doc["tenant"]
    assert "Pacific View Management" in doc["recipient"]
    assert doc["payment_deadline_days"] == 14
    print("  [✓] User approval processed: Tool executed and formal demand letter compiled with overrides.")


def test_scenario_b_user_rejects():
    print("\n--- Scenario B: User Rejects (Safe Rejection, Zero Tool Side-Effects) ---")
    agent = TenantShieldAgent()

    res = agent.run("Landlord in California kept $600.")
    proposal = res.proposed_action
    assert proposal is not None

    # User explicitly declines the action
    reject_res = agent.reject_action(action_id=proposal.action_id, reason="I negotiated directly with landlord.")
    assert reject_res["success"] is True
    assert reject_res["status"] == "REJECTED"

    # Verify state in ActionManager
    stored_prop = action_manager.get_proposal(proposal.action_id)
    assert stored_prop.state == ActionLifecycleState.REJECTED
    assert stored_prop.rejection_reason == "I negotiated directly with landlord."
    assert stored_prop.execution_result is None
    print("  [✓] User rejection confirmed: State transitioned to REJECTED with zero tool side-effects.")


def test_scenario_c_user_cancels():
    print("\n--- Scenario C: User Cancels (Action Proposal Voided) ---")
    agent = TenantShieldAgent()

    res = agent.run("Landlord in California kept $500.")
    proposal = res.proposed_action
    assert proposal is not None

    # User cancels
    cancel_res = agent.cancel_action(action_id=proposal.action_id)
    assert cancel_res["success"] is True
    assert cancel_res["status"] == "CANCELLED"

    stored_prop = action_manager.get_proposal(proposal.action_id)
    assert stored_prop.state == ActionLifecycleState.CANCELLED
    print("  [✓] Cancellation confirmed: Action state transitioned to CANCELLED.")


def test_scenario_d_tool_fails_after_approval_and_retry():
    print("\n--- Scenario D: Tool Fails After Approval & Retry Flow ---")

    class TemporarilyFailingNoticeClient:
        def __init__(self):
            self.attempts = 0

        def call_tool(self, tool_name: str, arguments: Dict[str, Any]):
            self.attempts += 1
            if self.attempts == 1:
                return {
                    "isError": True,
                    "error": "Temporary document storage lock timeout",
                }
            return {
                "isError": False,
                "data": {"status": "STAGED_FORMAL_NOTICE", "document_title": "Recovered Demand Letter"},
            }

    failing_client = TemporarilyFailingNoticeClient()
    custom_mgr = ActionManager(notice_client=failing_client)

    proposal = custom_mgr.create_proposal(
        action_type="STAGE_LEGAL_DEMAND_LETTER",
        target="Landlord",
        what="Test action",
        why="Test reason",
        data_involved={"dispute_amount": 500.0, "violations": ["Breach"], "statutory_citation": "Code"},
        consequences_if_approved="Document will compile",
        what_will_not_happen="Will not sue",
    )

    # 1. First execution attempt -> Fails
    res_fail = custom_mgr.approve_and_execute(proposal.action_id)
    assert res_fail["success"] is False
    assert res_fail["status"] == "FAILURE"
    assert res_fail["can_retry"] is True
    assert proposal.state == ActionLifecycleState.FAILURE
    print("  [✓] Tool failure gracefully captured: State transitioned to FAILURE with retry enabled.")

    # 2. Retry execution -> Succeeds
    res_retry = custom_mgr.retry_action(proposal.action_id)
    assert res_retry["success"] is True
    assert res_retry["status"] == "SUCCESS"
    assert proposal.state == ActionLifecycleState.SUCCESS
    assert proposal.retry_count == 1
    print("  [✓] Retry executed successfully: State transitioned to SUCCESS without re-audit.")


def test_scenario_e_user_clicks_approve_twice():
    print("\n--- Scenario E: Double-Click / Duplicate Execution Protection ---")
    agent = TenantShieldAgent()

    res = agent.run("Landlord in California kept $700 24 days after move out.")
    proposal = res.proposed_action
    assert proposal is not None

    # First Click: Should succeed
    res1 = agent.execute_action("STAGE_LEGAL_DEMAND_LETTER", approved=True, action_id=proposal.action_id)
    assert res1["success"] is True

    # Second Click: MUST be rejected immediately
    res2 = agent.execute_action("STAGE_LEGAL_DEMAND_LETTER", approved=True, action_id=proposal.action_id)
    assert res2["success"] is False
    assert res2["status"] == "INVALID_STATE"
    assert "Duplicate or repeated execution prevented" in res2["message"]
    print("  [✓] Second approval click safely blocked: Duplicate tool execution prevented.")


def test_scenario_f_invalid_and_stale_actions():
    print("\n--- Scenario F: Invalid & Stale (Expired) Action Handling ---")

    # 1. Non-existent action ID
    invalid_res = action_manager.approve_and_execute("act_non_existent_12345")
    assert invalid_res["success"] is False
    assert invalid_res["status"] == "INVALID_ACTION"
    print("  [✓] Nonexistent action ID rejected safely with INVALID_ACTION.")

    # 2. Stale / Expired Proposal (Simulated with 0.1s TTL)
    short_lived_proposal = action_manager.create_proposal(
        action_type="STAGE_LEGAL_DEMAND_LETTER",
        target="Landlord",
        what="Short lived",
        why="TTL test",
        data_involved={},
        consequences_if_approved="None",
        what_will_not_happen="None",
        ttl_seconds=0.01,
    )
    time.sleep(0.02)  # Wait for TTL to expire

    expired_res = action_manager.approve_and_execute(short_lived_proposal.action_id)
    assert expired_res["success"] is False
    assert expired_res["status"] == "EXPIRED"
    assert "expired" in expired_res["message"]
    print("  [✓] Stale approval request rejected cleanly due to TTL expiration.")


def main():
    print("=" * 65)
    print(" TENANTSHIELD - PHASE 5 SAFETY & HUMAN CONTROL VERIFICATION")
    print("=" * 65)

    test_scenario_a_user_approves()
    test_scenario_b_user_rejects()
    test_scenario_c_user_cancels()
    test_scenario_d_tool_fails_after_approval_and_retry()
    test_scenario_e_user_clicks_approve_twice()
    test_scenario_f_invalid_and_stale_actions()

    print("\n" + "=" * 65)
    print(" ALL 6 PHASE 5 SAFETY SCENARIOS PASSED WITH 100% SUCCESS!")
    print("=" * 65)
    return 0


if __name__ == "__main__":
    sys.exit(main())
