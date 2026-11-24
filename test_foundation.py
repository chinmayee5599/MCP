"""Phase 1 Foundation Verification Test Suite

Performs automated verification of:
1. Configuration loading & path resolution
2. FastAPI app instance and route registration
3. Health check endpoint (/health) structure and status
4. System status endpoint (/api/status) metadata and MCP server readiness
5. Frontend template (/templates/index.html) content and branding
6. Static assets (/static/css/style.css, /static/js/app.js) and frontend integration script
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings
from app.main import app, health_check, system_status, index

def run_tests():
    print("=" * 65)
    print(" TENANTSHIELD - PHASE 1 FOUNDATION VERIFICATION SUITE")
    print("=" * 65)

    passed = 0
    total = 6

    # 1. Config & Environment Verification
    print("[1/6] Verifying Settings & Path Resolution ...", end=" ", flush=True)
    assert settings.PROJECT_NAME == "TenantShield", "Incorrect PROJECT_NAME"
    assert settings.VERSION == "0.1.0", "Incorrect VERSION"
    assert settings.STATIC_DIR.exists(), f"Static dir missing: {settings.STATIC_DIR}"
    assert settings.TEMPLATES_DIR.exists(), f"Templates dir missing: {settings.TEMPLATES_DIR}"
    assert settings.MCP_SERVERS_DIR.exists(), f"MCP servers dir missing: {settings.MCP_SERVERS_DIR}"
    print("PASSED")
    passed += 1

    # 2. FastAPI Route Registration
    print("[2/6] Verifying FastAPI Route Registrations ...", end=" ", flush=True)
    registered_routes = {route.path: route.name for route in app.routes}
    assert "/health" in registered_routes, "Missing /health route"
    assert "/api/status" in registered_routes, "Missing /api/status route"
    assert "/" in registered_routes, "Missing / route"
    assert "/static" in registered_routes or any("/static" in r for r in registered_routes), "Missing /static mount"
    print(f"PASSED ({len(app.routes)} routes verified)")
    passed += 1

    # 3. Health Check Endpoint
    print("[3/6] Verifying Health Endpoint (/health) ...", end=" ", flush=True)
    health = health_check()
    assert isinstance(health, dict), "Health response must be a dict"
    assert health.get("status") == "healthy", f"Unexpected status: {health.get('status')}"
    assert health.get("service") == "TenantShield", f"Unexpected service: {health.get('service')}"
    assert "timestamp" in health, "Missing timestamp in health response"
    print(f"PASSED (status: {health['status']}, service: {health['service']})")
    passed += 1

    # 4. Detailed System Status Endpoint
    print("[4/6] Verifying System Status Endpoint (/api/status) ...", end=" ", flush=True)
    status = system_status()
    assert isinstance(status, dict), "Status response must be a dict"
    assert status.get("status") == "online", f"Unexpected status: {status.get('status')}"
    assert status.get("project") == "TenantShield", f"Unexpected project: {status.get('project')}"
    assert status.get("mcp_ready") is True, "MCP readiness flag should be True"
    assert len(status.get("mcp_servers_available", [])) == 3, "Expected 3 scheduled MCP servers"
    print(f"PASSED (status: {status['status']}, servers: {status['mcp_servers_available']})")
    passed += 1

    # 5. Frontend Index Template
    print("[5/6] Verifying Frontend Template (index.html) ...", end=" ", flush=True)
    response = index()
    template_path = Path(response.path)
    assert template_path.exists(), f"Template file does not exist: {template_path}"
    html_content = template_path.read_text(encoding="utf-8")
    assert "TenantShield" in html_content, "Missing brand in HTML"
    assert "Make MCP Matter" in html_content, "Missing hackathon theme in HTML"
    assert "/static/js/app.js" in html_content, "Missing script tag in HTML"
    assert "connection-status-badge" in html_content, "Missing status badge in HTML"
    print(f"PASSED ({len(html_content)} bytes verified)")
    passed += 1

    # 6. Static Assets (CSS & JS)
    print("[6/6] Verifying Static Assets & Client Script ...", end=" ", flush=True)
    js_path = settings.STATIC_DIR / "js" / "app.js"
    css_path = settings.STATIC_DIR / "css" / "style.css"
    assert js_path.exists(), f"Missing app.js at {js_path}"
    assert css_path.exists(), f"Missing style.css at {css_path}"
    js_content = js_path.read_text(encoding="utf-8")
    assert "/api/status" in js_content, "Client JS must query /api/status"
    assert "checkBackendStatus" in js_content, "Missing checkBackendStatus function in app.js"
    print("PASSED (app.js and style.css validated)")
    passed += 1

    print("=" * 65)
    print(f" RESULT: {passed}/{total} VERIFICATION CHECKS PASSED SUCCESSFULLY")
    print("=" * 65)
    return 0

if __name__ == "__main__":
    sys.exit(run_tests())
