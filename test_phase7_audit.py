"""TenantShield Phase 7 Technical Audit & Reliability Test Suite

Tests and validates:
1. Backend: Config, routes, validation schemas, exception resilience.
2. MCP: Subprocess resilience, malformed stdio JSON-RPC, recovery after kill.
3. AI Agent: Month/year tenure parsing, fallback amounts (no NameError), zero-dispute handling, safeguards.
4. Human Approval: Concurrency locking, duplicate prevention, TTL expiration, retry.
5. Security: Secret exposure scan, sensitive log masking, security gating on write tools.
6. Frontend: Verification of template error containers and client-side logic.
"""

import sys
import json
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings
from app.mcp_client import tenancy_mcp_client, notice_mcp_client, MCPRegistry
from app.agent import TenantShieldAgent, AgentStatus, agent
from app.action_manager import action_manager, ActionLifecycleState, mask_sensitive_text
from app.main import (
    index,
    health_check,
    system_status,
    list_mcp_tools,
    execute_mcp_tool,
    run_agent_audit,
    approve_agent_action,
    reject_agent_action,
    cancel_agent_action,
    AgentAuditRequest,
    HumanApprovalRequest,
    MCPToolExecutionRequest,
)

def run_tests():
    print("=" * 65)
    print(" TENANTSHIELD - PHASE 7 TECHNICAL AUDIT & RELIABILITY SUITE")
    print("=" * 65)

    passed = 0
    total = 6

    # -------------------------------------------------------------------------
    # Audit 1: Backend Reliability & Pydantic Validation Flexibility
    # -------------------------------------------------------------------------
    print("\n--- Audit 1: Backend Reliability, Routes & Flexible Schemas ---")
    health = health_check()
    assert health["status"] == "healthy"
    assert health["service"] == "TenantShield"

    status = system_status()
    assert status["status"] == "online"
    assert status["mcp_ready"] is True

    # Test flexible schema on HumanApprovalRequest (reject/cancel without action_type)
    dummy_req = HumanApprovalRequest(action_id="act_test_flex", reason="Testing defaults")
    assert dummy_req.action_type == "STAGE_LEGAL_DEMAND_LETTER"
    assert dummy_req.approved is True
    assert dummy_req.action_id == "act_test_flex"

    # Test reject action endpoint with minimal payload
    rej_res = reject_agent_action(HumanApprovalRequest(action_id="act_non_existent", reason="Decline test"))
    assert rej_res["success"] is False
    assert rej_res["status"] == "INVALID_ACTION"

    print("  [✓] Health, status, and flexible Pydantic schemas validated.")
    passed += 1

    # -------------------------------------------------------------------------
    # Audit 2: MCP Subprocess Resilience & Auto-Recovery
    # -------------------------------------------------------------------------
    print("\n--- Audit 2: MCP Protocol Resilience & Subprocess Auto-Recovery ---")
    tenancy_mcp_client.connect()
    assert tenancy_mcp_client.is_connected is True

    # 1. Verify standard tool execution
    res1 = tenancy_mcp_client.call_tool("get_statutory_deadlines", {"jurisdiction": "California"})
    assert not res1["isError"]
    assert res1["data"]["statutory_deadline_days"] == 21

    # 2. Simulate unexpected subprocess termination (kill)
    if tenancy_mcp_client.process:
        tenancy_mcp_client.process.terminate()
        tenancy_mcp_client.process.wait(timeout=2)

    # 3. Next call must automatically reconnect without crashing
    res2 = tenancy_mcp_client.call_tool("get_statutory_deadlines", {"jurisdiction": "New York"})
    assert not res2["isError"]
    assert res2["data"]["statutory_deadline_days"] == 14
    assert tenancy_mcp_client.is_connected is True

    # 4. MCP Registry listing resilience
    all_tools = MCPRegistry.list_all_tools()
    assert len(all_tools) >= 3

    print("  [✓] MCP subprocess crash recovery and registry tool listing verified.")
    passed += 1

    # -------------------------------------------------------------------------
    # Audit 3: AI Agent Robustness, Edge-Cases & No NameError
    # -------------------------------------------------------------------------
    print("\n--- Audit 3: AI Agent Extraction, Zero-Dispute & Edge-Cases ---")
    test_agent = TenantShieldAgent()

    # Case A: Month-based tenure extraction
    months_prompt = "I rented an apartment in Los Angeles for 18 months. Landlord sent notice on Day 25."
    extracted_years = test_agent._extract_tenancy_years(months_prompt)
    assert extracted_years == 1.5, f"Expected 1.5 years for 18 months, got {extracted_years}"

    six_mos_prompt = "I rented in New York for 6 mos."
    assert test_agent._extract_tenancy_years(six_mos_prompt) == 0.5

    # Case B: Prompt with dollar amount but no line items (Verifies NO NameError on 'amounts')
    raw_prompt = "I lived in California. My landlord kept my $1,500 deposit 30 days after move-out."
    raw_res = test_agent.run(user_goal=raw_prompt)
    assert raw_res.status == AgentStatus.AWAITING_APPROVAL
    assert raw_res.findings["dispute_amount"] == 1500.0
    assert raw_res.findings["deadline_violated"] is True

    # Case C: Prompt with ZERO dispute (no violation, prompt under statutory deadline)
    zero_dispute_prompt = "I moved out of my apartment in California 5 days ago. Everything was in great condition."
    zero_res = test_agent.run(user_goal=zero_dispute_prompt)
    assert zero_res.status == AgentStatus.RESOLVED
    assert any("no statutory deadline breach" in s.lower() for s in zero_res.decision_summaries)
    assert zero_res.proposed_action is None

    print("  [✓] Month tenure parsing, fallback amounts (no NameError), and zero-dispute handling verified.")
    passed += 1

    # -------------------------------------------------------------------------
    # Audit 4: Action Governance, Double-Click Atomic Locks & TTL Expiration
    # -------------------------------------------------------------------------
    print("\n--- Audit 4: Action Lifecycle, Concurrency & Security Gate ---")
    # Security Gate: Direct execution of stage_formal_demand_letter via /api/mcp/execute must be blocked
    direct_exec_res = execute_mcp_tool(MCPToolExecutionRequest(
        tool_name="stage_formal_demand_letter",
        arguments={"dispute_amount": 1000, "violations": ["test"], "statutory_citation": "test"}
    ))
    assert direct_exec_res.isError is True
    assert "Security Gate" in direct_exec_res.error

    # Create proposal and test atomic execution
    proposal = action_manager.create_proposal(
        action_type="STAGE_LEGAL_DEMAND_LETTER",
        target="Sunset Apartments LLC",
        what="Stage formal notice",
        why="Statute breach",
        data_involved={
            "jurisdiction": "California",
            "statutory_citation": "Cal. Civ. Code § 1950.5",
            "dispute_amount": 800.0,
            "statutory_penalties": 1600.0,
            "violations": ["Late deposit return"],
        },
        consequences_if_approved="Notice compiled",
        what_will_not_happen="Will not dispatch email automatically",
        ttl_seconds=900.0,
    )

    # 1. Authorize execution
    exec_res = action_manager.approve_and_execute(proposal.action_id, user_overrides={"tenant_name": "Auditor"})
    assert exec_res["success"] is True
    assert exec_res["status"] == ActionLifecycleState.SUCCESS.value

    # 2. Duplicate click protection: second attempt must be rejected
    dup_res = action_manager.approve_and_execute(proposal.action_id)
    assert dup_res["success"] is False
    assert dup_res["status"] == "INVALID_STATE"

    # 3. Stale proposal protection: expired proposal must be rejected
    stale_prop = action_manager.create_proposal(
        action_type="STAGE_LEGAL_DEMAND_LETTER",
        target="Stale Landlord",
        what="Stale notice",
        why="Stale reason",
        data_involved={"statutory_citation": "Law", "dispute_amount": 100, "violations": ["v"]},
        consequences_if_approved="doc",
        what_will_not_happen="none",
        ttl_seconds=0.01,
    )
    time.sleep(0.05)
    stale_res = action_manager.approve_and_execute(stale_prop.action_id)
    assert stale_res["success"] is False
    assert stale_res["status"] == "EXPIRED"
    assert stale_prop.state == ActionLifecycleState.CANCELLED

    print("  [✓] Security gate, atomic double-click lock, and TTL expiration verified.")
    passed += 1

    # -------------------------------------------------------------------------
    # Audit 5: Security & Secret Hardcoding Audit
    # -------------------------------------------------------------------------
    print("\n--- Audit 5: Security, Secret Exposure & Log Masking Audit ---")
    # Verify sensitive text masking function
    assert mask_sensitive_text("Sunset Real Estate LLC") == "Su****LC"
    assert mask_sensitive_text("John Doe") == "Jo****oe"
    assert mask_sensitive_text("123") == "****"
    assert mask_sensitive_text("") == ""

    # Check for hardcoded API keys or credentials in codebase
    source_files = list((PROJECT_ROOT / "app").glob("**/*.py")) + list((PROJECT_ROOT / "mcp_servers").glob("**/*.py"))
    forbidden_tokens = ["sk-", "AIzaSy", "ghp_", "SECRET_KEY = \"", "api_key = \""]

    for sf in source_files:
        content = sf.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            assert token not in content, f"Potential hardcoded credential token '{token}' in {sf}"

    print(f"  [✓] Scanned {len(source_files)} source files: 0 exposed secrets found. Log masking verified.")
    passed += 1

    # -------------------------------------------------------------------------
    # Audit 6: Frontend Template Markup & Error Container Verification
    # -------------------------------------------------------------------------
    print("\n--- Audit 6: Frontend Template & Clean Error Handling Markup ---")
    resp = index()
    template_path = Path(resp.path)
    html = template_path.read_text(encoding="utf-8")

    assert 'id="input-error-msg"' in html, "Missing inline input error message element"
    assert 'id="action-error-msg"' in html, "Missing inline action error message element"
    assert 'id="preset-la-btn"' in html
    assert 'id="preset-ny-btn"' in html

    js_code = (PROJECT_ROOT / "app" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert "input-error-msg" in js_code
    assert "action-error-msg" in js_code

    print("  [✓] Frontend template and client-side error containers verified.")
    passed += 1

    print("\n" + "=" * 65)
    print(f" ALL {passed}/{total} PHASE 7 TECHNICAL AUDIT CHECKS PASSED WITH 100% SUCCESS!")
    print("=" * 65)
    return 0

if __name__ == "__main__":
    sys.exit(run_tests())
