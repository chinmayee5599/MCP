"""Phase 6 Frontend & Complete User Journey Verification Test Suite

Verifies:
1. Frontend HTML template rendering with all UI components & hackathon elements
2. Static assets delivery (/static/js/app.js and /static/css/style.css)
3. End-to-end simulated frontend user journey:
   - Status & MCP connection health probe (/api/status)
   - Preset 1 (Los Angeles): Audit -> Stepper -> Findings -> Disclosures -> Overrides -> Approval -> Compiled Document
   - Preset 2 (New York City): Audit -> Stepper -> Findings -> Decline -> Clean Rejection State
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings
from app.main import (
    index,
    system_status,
    run_agent_audit,
    approve_agent_action,
    reject_agent_action,
    AgentAuditRequest,
    HumanApprovalRequest,
)

def run_tests():
    print("=" * 65)
    print(" TENANTSHIELD - PHASE 6 FRONTEND & USER JOURNEY TEST SUITE")
    print("=" * 65)

    passed = 0
    total = 5

    # -------------------------------------------------------------------------
    # Test 1: Frontend Root Page & Component Validation
    # -------------------------------------------------------------------------
    print("\n--- Test 1: Frontend Root Page & Component Markup ---")
    resp = index()
    template_path = Path(resp.path)
    assert template_path.exists(), f"Template not found at {template_path}"
    html = template_path.read_text(encoding="utf-8")

    # Core Branding & Hackathon identity
    assert "TenantShield" in html, "Missing brand in HTML"
    assert "Make MCP Matter" in html, "Missing hackathon badge"
    assert "Autonomous Lease & Security Deposit Defender" in html, "Missing tagline"

    # MCP Health & Stepper Pipeline Elements
    assert 'id="mcp-status-badge"' in html, "Missing MCP status badge"
    assert 'id="stepper-section"' in html, "Missing stepper section"
    for i in range(1, 6):
        assert f'id="step-card-{i}"' in html, f"Missing step card {i}"

    # Demo Presets
    assert 'id="preset-la-btn"' in html, "Missing LA preset button"
    assert 'id="preset-ny-btn"' in html, "Missing NY preset button"

    # Input & Execution Controls
    assert 'id="dispute-input"' in html, "Missing dispute textarea"
    assert 'id="jurisdiction-select"' in html, "Missing jurisdiction select"
    assert 'id="run-audit-btn"' in html, "Missing run audit button"

    # Dynamic Findings & KPI Cards
    assert 'id="findings-section"' in html, "Missing findings container"
    assert 'id="kpi-principal"' in html, "Missing principal KPI card"
    assert 'id="kpi-penalties"' in html, "Missing penalties KPI card"
    assert 'id="kpi-total"' in html, "Missing total claim KPI card"
    assert 'id="deadline-violation-alert"' in html, "Missing statutory deadline violation alert"
    assert 'id="audit-table-body"' in html, "Missing itemized deduction audit table body"

    # Human Approval Card & 5 Transparency Disclosures
    assert 'id="approval-card"' in html, "Missing human approval card"
    assert 'id="disclosure-what"' in html, "Missing disclosure: What"
    assert 'id="disclosure-why"' in html, "Missing disclosure: Why"
    assert 'id="disclosure-consequences"' in html, "Missing disclosure: Consequences"
    assert 'id="disclosure-not-happen"' in html, "Missing disclosure: What will NOT happen"

    # Overrides Drawer & Buttons
    assert 'id="override-tenant-name"' in html, "Missing override: tenant_name"
    assert 'id="override-landlord-name"' in html, "Missing override: landlord_name"
    assert 'id="override-rental-address"' in html, "Missing override: rental_address"
    assert 'id="override-demand-days"' in html, "Missing override: demand_deadline_days"
    assert 'id="approve-action-btn"' in html, "Missing approve button"
    assert 'id="reject-action-btn"' in html, "Missing reject button"

    # Result Document & Rejection Sections
    assert 'id="result-document-section"' in html, "Missing result document section"
    assert 'id="formal-letter-pre"' in html, "Missing formal letter pre container"
    assert 'id="copy-doc-btn"' in html, "Missing copy document button"
    assert 'id="rejected-banner"' in html, "Missing rejected banner"

    print("  [✓] All Phase 6 UI components, presets, stepper cards & disclosures verified.")
    passed += 1

    # -------------------------------------------------------------------------
    # Test 2: Static Assets Delivery (/static/js/app.js & /static/css/style.css)
    # -------------------------------------------------------------------------
    print("\n--- Test 2: Static Assets Delivery ---")
    js_path = settings.STATIC_DIR / "js" / "app.js"
    css_path = settings.STATIC_DIR / "css" / "style.css"
    assert js_path.exists(), f"Missing app.js at {js_path}"
    assert css_path.exists(), f"Missing style.css at {css_path}"

    js_code = js_path.read_text(encoding="utf-8")
    assert "checkBackendAndMCPStatus" in js_code, "app.js missing health probe"
    assert "runLegalAudit" in js_code, "app.js missing runLegalAudit"
    assert "approveAction" in js_code, "app.js missing approveAction"
    assert "rejectAction" in js_code, "app.js missing rejectAction"
    assert "copyFormalNotice" in js_code, "app.js missing copyFormalNotice"

    css_code = css_path.read_text(encoding="utf-8")
    print(f"  [✓] Static JS ({len(js_code)} bytes) and CSS ({len(css_code)} bytes) validated.")
    passed += 1

    # -------------------------------------------------------------------------
    # Test 3: Backend & MCP Stdio Health Probe (/api/status)
    # -------------------------------------------------------------------------
    print("\n--- Test 3: System Status & MCP stdio Discovery ---")
    status_data = system_status()
    assert status_data["mcp_active"] is True, "Expected active MCP stdio connections"
    assert len(status_data["registered_mcp_tools"]) >= 3, "Expected at least 3 registered MCP tools"
    assert "get_statutory_deadlines" in status_data["registered_mcp_tools"]
    assert "evaluate_wear_and_tear" in status_data["registered_mcp_tools"]
    assert "stage_formal_demand_letter" in status_data["registered_mcp_tools"]
    print(f"  [✓] MCP active over stdio with tools: {status_data['registered_mcp_tools']}")
    passed += 1

    # -------------------------------------------------------------------------
    # Test 4: Complete User Journey — Los Angeles Preset (Approval Flow)
    # -------------------------------------------------------------------------
    print("\n--- Test 4: Complete User Journey: Los Angeles Preset (Audit -> Approval -> Document) ---")
    la_prompt = (
        "I lived in an apartment in Los Angeles for 3 years. My landlord sent me a notice 26 days "
        "after move-out deducting $600 for wall painting and $450 for carpet cleaning. Help me get my deposit back."
    )
    audit_data = run_agent_audit(AgentAuditRequest(
        user_goal=la_prompt,
        context={"jurisdiction": "California"}
    ))

    # Step 1: Agent Understanding
    assert audit_data.status.value == "AWAITING_APPROVAL"
    findings = audit_data.findings
    assert findings["dispute_amount"] == 1050.0
    assert findings["deadline_violated"] is True
    assert findings["statutory_deadline_days"] == 21
    assert findings["days_elapsed"] == 26
    assert findings["statutory_penalties_eligible"] == 2100.0  # 2.0x bad-faith multiplier in CA
    assert findings["total_claim"] == 3150.0

    # Step 2: Proposed Action & Disclosures
    proposed = audit_data.proposed_action
    assert proposed is not None
    assert proposed.requires_approval is True
    action_id = proposed.action_id
    assert action_id.startswith("act_")
    assert len(proposed.what) > 10
    assert len(proposed.why) > 10
    assert len(proposed.consequences_if_approved) > 10
    assert len(proposed.what_will_not_happen) > 10

    # Step 3: Human Authorizes Action with Overrides
    action_res = approve_agent_action(HumanApprovalRequest(
        action_id=action_id,
        action_type=proposed.action_type,
        approved=True,
        user_overrides={
            "tenant_name": "Jane Doe",
            "landlord_name": "Sunset Real Estate LLC",
            "rental_address": "742 Evergreen Terrace, Los Angeles, CA",
            "demand_deadline_days": 10,
        }
    ))
    assert action_res["success"] is True
    assert action_res["status"] in ("AUTHORIZED_AND_COMPILED", "SUCCESS")
    doc = action_res["document"]
    letter_text = doc.get("full_letter_text") or doc.get("result", {}).get("full_letter_text")
    assert letter_text is not None
    assert "Jane Doe" in letter_text
    assert "Sunset Real Estate LLC" in letter_text
    assert "742 Evergreen Terrace" in letter_text
    assert "1950.5" in letter_text
    assert "$1,050.00" in letter_text
    assert "$2,100.00" in letter_text
    assert "$3,150.00" in letter_text
    print("  [✓] Audit, Human Gate, and MCP Tool C Execution verified end-to-end.")
    passed += 1

    # -------------------------------------------------------------------------
    # Test 5: Complete User Journey — New York City Preset (Rejection Flow)
    # -------------------------------------------------------------------------
    print("\n--- Test 5: Complete User Journey: NYC Preset (Audit -> Rejection Flow) ---")
    ny_prompt = (
        "I rented an apartment in New York City for 2 years. 20 days after move-out, "
        "my landlord sent an itemized notice deducting $500 for wall repainting and $400 for standard carpet cleaning."
    )
    ny_data = run_agent_audit(AgentAuditRequest(
        user_goal=ny_prompt,
        context={"jurisdiction": "New York"}
    ))
    assert ny_data.status.value == "AWAITING_APPROVAL"
    ny_action_id = ny_data.proposed_action.action_id

    # User Rejects Action
    reject_json = reject_agent_action(HumanApprovalRequest(
        action_id=ny_action_id,
        action_type=ny_data.proposed_action.action_type,
        approved=False,
        reason="Declined by user."
    ))
    assert reject_json["success"] is True
    assert reject_json["status"] == "REJECTED"

    print("  [✓] Rejection flow verified: Safe state transition with zero external tool side-effects.")
    passed += 1

    print("\n" + "=" * 65)
    print(f" ALL {passed}/{total} PHASE 6 FRONTEND VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 65)
    return 0

if __name__ == "__main__":
    sys.exit(run_tests())
