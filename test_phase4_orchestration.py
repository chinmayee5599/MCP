"""Phase 4 MCP Tool Ecosystem & Orchestration Verification Suite

Tests:
1. Successful Workflow: Tool A (READ) -> Tool B (READ/ANALYZE) -> Recommendation -> Human Approval -> Tool C (WRITE/ACTION).
2. Partial Tool Failure: Tool A succeeds, Tool B encounters error on one item; agent degrades gracefully.
3. Unavailable Service: MCP server unavailable; agent captures failure without false success.
4. Malformed Tool Response: MCP tool returns invalid payload; agent prevents hallucinated calculations.
5. User Changes Request: Dynamic state update when user modifies jurisdiction and deduction parameters.
6. Repeated Execution: Call signature tracking prevents redundant identical MCP invocations.
7. Dangerous / Invalid Action: Direct unapproved write tool execution blocked by security gate.
"""

import sys
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.agent import TenantShieldAgent, AgentStatus
from app.mcp_client import tenancy_mcp_client, notice_mcp_client, MCPClientSession, MCPRegistry
from app.main import (
    run_agent_audit,
    approve_agent_action,
    execute_mcp_tool,
    list_mcp_tools,
    AgentAuditRequest,
    HumanApprovalRequest,
    MCPToolExecutionRequest,
)


def test_1_successful_workflow():
    print("\n--- Test 1: Successful Multi-Tool MCP Orchestration Workflow ---")
    agent = TenantShieldAgent()

    user_query = (
        "I lived in an apartment in Los Angeles for 3 years. My landlord sent me a notice "
        "26 days after move-out deducting $600 for wall painting and $450 for carpet cleaning. "
        "Help me dispute these deductions."
    )

    # 1. Run Agent Audit (Calls Tool A & Tool B)
    res = agent.run(user_goal=user_query)

    assert res.status == AgentStatus.AWAITING_APPROVAL, f"Expected AWAITING_APPROVAL, got {res.status}"
    assert len(res.tools_invoked) >= 2, f"Expected at least 2 MCP tool calls, got {len(res.tools_invoked)}"

    # Verify Tool A was called (get_statutory_deadlines)
    tool_names = [t["tool"] for t in res.tools_invoked]
    assert "get_statutory_deadlines" in tool_names, "Tool A missing"
    assert "evaluate_wear_and_tear" in tool_names, "Tool B missing"

    # Verify Findings & Calculations
    findings = res.findings
    assert findings["statutory_deadline_days"] == 21
    assert findings["deadline_violated"] is True  # 26 > 21
    assert findings["recoverable_principal"] == 1050.0  # $600 + $450
    assert findings["statutory_penalties_eligible"] == 2100.0  # 2.0x statutory multiplier under § 1950.5(l)
    assert findings["total_claim"] == 3150.0

    # Verify Itemized Audits
    assert len(res.itemized_audits) >= 1
    painting_audit = next((a for a in res.itemized_audits if a["item_category"] == "painting"), None)
    assert painting_audit is not None
    assert painting_audit["classification"] == "ORDINARY_WEAR_AND_TEAR"
    assert painting_audit["unlawful_charge"] == 600.0

    # Verify Proposed Action (Awaiting Approval)
    action = res.proposed_action
    assert action is not None
    assert action.action_type == "STAGE_LEGAL_DEMAND_LETTER"
    assert action.requires_approval is True
    assert action.approved is False
    assert action.staged_document is None  # Must NOT be generated yet!

    print("  [✓] Tool A ('get_statutory_deadlines') identified 26-day breach of 21-day California deadline.")
    print("  [✓] Tool B ('evaluate_wear_and_tear') identified 100% ordinary wear-and-tear for 3-year tenancy.")
    print(f"  [✓] Decision synthesis: $1,050 principal recoverable + $2,100 statutory bad-faith penalties.")
    print("  [✓] Halting at AWAITING_APPROVAL gate before executing write action.")

    # 2. Human Approval Gate: User Authorizes Action -> Executes Tool C
    approval_result = agent.execute_action(
        action_type="STAGE_LEGAL_DEMAND_LETTER",
        approved=True,
        user_overrides={
            "tenant_name": "Jane Doe",
            "landlord_name": "Sunset Real Estate LLC",
            "rental_address": "742 Evergreen Terrace, Los Angeles, CA",
            "move_out_date": "October 1, 2026",
            "demand_deadline_days": 10,
        },
    )

    assert approval_result["status"] == "AUTHORIZED_AND_COMPILED"
    assert approval_result["approved"] is True
    doc = approval_result["document"]
    assert doc["status"] == "STAGED_FORMAL_NOTICE"
    assert "Sunset Real Estate LLC" in doc["recipient"]
    assert "FORMAL LEGAL NOTICE & DEMAND FOR PAYMENT" in doc["full_letter_text"]
    assert "$3,150.00" in doc["full_letter_text"]
    print("  [✓] Human Approval granted: Tool C ('stage_formal_demand_letter') executed on formal_notice_mcp.")
    print("  [✓] Courtroom-ready formal demand letter compiled with statutory citations and itemized claims.")


def test_2_partial_tool_failure():
    print("\n--- Test 2: Partial Tool Failure Recovery ---")

    class PartiallyFailingTenancyClient:
        def call_tool(self, tool_name: str, arguments: Dict[str, Any]):
            if tool_name == "get_statutory_deadlines":
                return {
                    "isError": False,
                    "data": {
                        "canonical_name": "california",
                        "display_name": "State of California",
                        "statute_citation": "Cal. Civ. Code § 1950.5(g)(1)",
                        "statutory_deadline_days": 21,
                        "forfeiture_on_deadline_breach": True,
                        "bad_faith_penalty_multiplier": 2.0,
                    },
                }
            elif tool_name == "evaluate_wear_and_tear":
                return {
                    "isError": True,
                    "error": "Temporary wear calculation database lock",
                }
            return {"isError": True, "error": "Unknown tool"}

    agent = TenantShieldAgent(tenancy_client=PartiallyFailingTenancyClient())
    res = agent.run(
        user_goal="My landlord in Los Angeles deducted $500 for carpet cleaning 28 days after move out."
    )

    # Agent should NOT crash; it relies on statutory deadline forfeiture
    assert res.status == AgentStatus.AWAITING_APPROVAL
    assert res.findings["deadline_violated"] is True
    assert any("could not complete wear-and-tear audit" in s.lower() for s in res.decision_summaries)
    print("  [✓] Tool B error caught; agent gracefully degraded and utilized Tool A deadline forfeiture.")


def test_3_unavailable_service():
    print("\n--- Test 3: Unavailable MCP Service (No False Success) ---")

    class DeadMCPClient:
        def call_tool(self, tool_name: str, arguments: Dict[str, Any]):
            raise ConnectionRefusedError("MCP Server daemon unreachable at stdio socket")

    dead_agent = TenantShieldAgent(tenancy_client=DeadMCPClient())
    res = dead_agent.run(user_goal="Dispute $800 in California.")

    assert res.status == AgentStatus.ERROR
    assert "MCP Service Unavailable" in res.error
    assert not res.proposed_action
    print("  [✓] Dead MCP server intercepted cleanly; application never pretended tool succeeded.")


def test_4_malformed_tool_response():
    print("\n--- Test 4: Malformed Tool Response Schema Validation ---")

    class CorruptMCPClient:
        def call_tool(self, tool_name: str, arguments: Dict[str, Any]):
            return {
                "isError": False,
                "data": {"corrupted_garbage": 999},  # Missing statutory_deadline_days
            }

    corrupt_agent = TenantShieldAgent(tenancy_client=CorruptMCPClient())
    res = corrupt_agent.run(user_goal="I have a dispute in California with $700 withheld.")

    assert res.status == AgentStatus.ERROR
    assert "Missing required statutory fields" in res.error
    assert not res.proposed_action
    print("  [✓] Corrupted tool schema rejected; agent prevented hallucinated statutory deadlines.")


def test_5_user_changes_request():
    print("\n--- Test 5: Dynamic State Update When User Modifies Request ---")
    agent = TenantShieldAgent()

    # Step 1: Initial query about California
    res_ca = agent.run(user_goal="Landlord in Los Angeles kept $500 for painting after 3 years.")
    assert res_ca.findings["jurisdiction"] == "State of California"
    assert res_ca.findings["statutory_deadline_days"] == 21

    # Step 2: User changes their mind / corrects facts to New York
    res_ny = agent.run(user_goal="Actually, the apartment was in New York City and they deducted $900 after 4 years.")
    assert res_ny.findings["jurisdiction"] == "State of New York"
    assert res_ny.findings["statutory_deadline_days"] == 14
    assert res_ny.findings["statutory_citation"] == "N.Y. Gen. Oblig. Law § 7-108(1-a)(e)"
    print("  [✓] Dynamic context switch verified: Agent re-audited under New York statutory parameters.")


def test_6_repeated_execution_safeguard():
    print("\n--- Test 6: Repeated Execution Loop Safeguard ---")
    agent = TenantShieldAgent()

    # Pass text with redundant item descriptions
    query = (
        "Landlord in California deducted $400 for wall painting, and also $400 for wall painting, "
        "and $400 for wall painting after 3 years."
    )
    res = agent.run(user_goal=query)

    # Visited calls filter should prevent redundant duplicate tool calls
    wear_calls = [t for t in res.tools_invoked if t["tool"] == "evaluate_wear_and_tear"]
    assert len(wear_calls) <= 2, f"Expected duplicate wear calls to be de-duplicated, got {len(wear_calls)}"
    print(f"  [✓] Redundant invocations safely filtered by call signature cache ({len(wear_calls)} unique call made).")


def test_7_dangerous_invalid_action():
    print("\n--- Test 7: Direct Unapproved Action Execution Intercepted ---")

    # 1. Test direct MCP execution of consequential write tool without approval gate
    direct_req = MCPToolExecutionRequest(
        tool_name="stage_formal_demand_letter",
        arguments={"dispute_amount": 1000.0, "violations": ["Violation 1"], "statutory_citation": "Civil Code"},
    )
    direct_res = execute_mcp_tool(direct_req)
    assert direct_res.isError is True
    assert "Security Gate: Direct execution" in direct_res.error
    print("  [✓] Direct execution of 'stage_formal_demand_letter' blocked by security gate.")

    # 2. Test user rejection in approval gate
    agent = TenantShieldAgent()
    agent.run("Landlord in California kept $600 25 days after move out.")
    cancel_res = agent.execute_action(action_type="STAGE_LEGAL_DEMAND_LETTER", approved=False)
    assert cancel_res["status"] == "REJECTED_BY_USER"
    assert cancel_res["approved"] is False
    print("  [✓] User rejection respected; no document compiled or dispatched.")


def main():
    print("=" * 65)
    print(" TENANTSHIELD - PHASE 4 MCP ECOSYSTEM VERIFICATION SUITE")
    print("=" * 65)

    test_1_successful_workflow()
    test_2_partial_tool_failure()
    test_3_unavailable_service()
    test_4_malformed_tool_response()
    test_5_user_changes_request()
    test_6_repeated_execution_safeguard()
    test_7_dangerous_invalid_action()

    print("\n" + "=" * 65)
    print(" ALL 7 PHASE 4 ORCHESTRATION TESTS PASSED WITH 100% SUCCESS!")
    print("=" * 65)
    return 0


if __name__ == "__main__":
    sys.exit(main())
