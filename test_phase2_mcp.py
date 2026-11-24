"""Phase 2 MCP Foundation Verification Suite

Tests:
1. Standalone MCP Server stdio JSON-RPC 2.0 protocol handshake.
2. Tool discovery and schema verification for 'get_statutory_deadlines'.
3. Tool execution with valid jurisdiction (California -> 21 days, § 1950.5).
4. Tool execution with alias (NYC -> 14 days, § 7-108).
5. Input validation and error handling with invalid jurisdiction ('Atlantis').
6. Input validation with empty / malformed arguments.
7. Backend MCP Client Session integration and lifecycle management.
8. FastAPI route handlers: GET /api/mcp/tools and POST /api/mcp/execute.
"""

import sys
import json
import subprocess
from pathlib import Path

# Setup paths
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings
from app.mcp_client import MCPClientSession
from app.main import list_mcp_tools, execute_mcp_tool, MCPToolExecutionRequest


def test_standalone_mcp_server_stdio():
    print("\n--- Test 1: Standalone MCP Server stdio JSON-RPC 2.0 Handshake ---")
    server_path = settings.MCP_SERVERS_DIR / "tenancy_law_server.py"
    assert server_path.exists(), f"Server script missing: {server_path}"

    proc = subprocess.Popen(
        [sys.executable, str(server_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    try:
        # 1. Initialize
        init_req = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "TestClient", "version": "1.0"},
            },
        })
        proc.stdin.write(init_req + "\n")
        proc.stdin.flush()

        init_res = json.loads(proc.stdout.readline().strip())
        assert init_res["id"] == 1, "RPC ID mismatch"
        assert init_res["result"]["protocolVersion"] == "2024-11-05", "Incorrect MCP protocol version"
        assert init_res["result"]["serverInfo"]["name"] == "tenancy_law_mcp", "Incorrect server name"
        print("  [✓] 'initialize' handshake completed successfully.")

        # 2. tools/list
        list_req = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        proc.stdin.write(list_req + "\n")
        proc.stdin.flush()

        list_res = json.loads(proc.stdout.readline().strip())
        tools = list_res["result"]["tools"]
        assert len(tools) >= 1, f"Expected at least 1 tool, got {len(tools)}"
        assert any(t["name"] == "get_statutory_deadlines" for t in tools), "Tool name missing"
        tool_0 = next(t for t in tools if t["name"] == "get_statutory_deadlines")
        assert "jurisdiction" in tool_0["inputSchema"]["required"], "Schema missing 'jurisdiction'"
        print("  [✓] 'tools/list' discovered 'get_statutory_deadlines' with valid JSON schema.")

        # 3. tools/call (Valid)
        call_req = json.dumps({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "get_statutory_deadlines",
                "arguments": {"jurisdiction": "California"},
            },
        })
        proc.stdin.write(call_req + "\n")
        proc.stdin.flush()

        call_res = json.loads(proc.stdout.readline().strip())
        assert call_res["result"]["isError"] is False, "Execution failed unexpectedly"
        ca_data = json.loads(call_res["result"]["content"][0]["text"])
        assert ca_data["statutory_deadline_days"] == 21, "CA statutory deadline must be 21 days"
        assert "1950.5" in ca_data["statute_citation"], "CA citation mismatch"
        print("  [✓] 'tools/call' for California returned 21 days deadline and Civil Code § 1950.5 citation.")

        # 4. tools/call (Invalid Jurisdiction Error Handling)
        err_req = json.dumps({
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "get_statutory_deadlines",
                "arguments": {"jurisdiction": "Atlantis"},
            },
        })
        proc.stdin.write(err_req + "\n")
        proc.stdin.flush()

        err_res = json.loads(proc.stdout.readline().strip())
        assert err_res["result"]["isError"] is True, "Expected isError: True for invalid jurisdiction"
        err_text = err_res["result"]["content"][0]["text"]
        assert "Unsupported jurisdiction 'Atlantis'" in err_text, "Missing helpful error text"
        print("  [✓] 'tools/call' for invalid jurisdiction returned safe handled error message.")

    finally:
        proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=2)


def test_backend_mcp_client_session():
    print("\n--- Test 2: Backend MCP Client Session & Alias Handling ---")
    client = MCPClientSession(
        server_script=settings.MCP_SERVERS_DIR / "tenancy_law_server.py",
        server_name="test_tenancy_client",
    )

    try:
        # Test connection & discovery
        connected = client.connect()
        assert connected is True, "Client failed to connect"
        tools = client.list_tools()
        assert len(tools) >= 1, "Failed to discover tools via client"
        print(f"  [✓] Client session connected to {client.server_info['name']} v{client.server_info['version']}.")

        # Test New York via alias NYC
        nyc_result = client.call_tool("get_statutory_deadlines", {"jurisdiction": "NYC"})
        assert nyc_result["isError"] is False, f"Failed NYC call: {nyc_result}"
        ny_data = nyc_result["data"]
        assert ny_data["statutory_deadline_days"] == 14, "NY statutory deadline must be 14 days"
        assert "7-108" in ny_data["statute_citation"], "NY citation mismatch"
        assert ny_data["forfeiture_on_deadline_breach"] is True, "Expected forfeiture rule"
        print("  [✓] Alias 'NYC' resolved to New York with 14-day statutory deadline and forfeiture rule.")

        # Test validation error on empty string
        empty_result = client.call_tool("get_statutory_deadlines", {"jurisdiction": ""})
        assert empty_result["isError"] is True, "Expected isError: True for empty string"
        assert "non-empty" in empty_result["error"]
        print("  [✓] Empty jurisdiction string rejected with clean validation error.")

    finally:
        client.disconnect()


def test_fastapi_mcp_endpoints():
    print("\n--- Test 3: FastAPI MCP Endpoints Integration ---")
    
    # 1. GET /api/mcp/tools
    tools_response = list_mcp_tools()
    assert tools_response["tool_count"] >= 1, "Expected at least 1 registered tool"
    assert any(t["name"] == "get_statutory_deadlines" for t in tools_response["tools"])
    print(f"  [✓] GET /api/mcp/tools returned {tools_response['tool_count']} registered tools.")

    # 2. POST /api/mcp/execute (Valid)
    exec_req = MCPToolExecutionRequest(
        tool_name="get_statutory_deadlines",
        arguments={"jurisdiction": "California"},
    )
    exec_res = execute_mcp_tool(exec_req)
    assert exec_res["isError"] is False, "Execution failed"
    assert exec_res["data"]["canonical_name"] == "california"
    print(f"  [✓] POST /api/mcp/execute returned verified statutory data for {exec_res['data']['display_name']}.")

    # 3. POST /api/mcp/execute (Invalid Tool Name)
    bad_tool_req = MCPToolExecutionRequest(
        tool_name="non_existent_tool",
        arguments={},
    )
    bad_tool_res = execute_mcp_tool(bad_tool_req)
    is_err = bad_tool_res.isError if hasattr(bad_tool_res, "isError") else bad_tool_res["isError"]
    err_msg = bad_tool_res.error if hasattr(bad_tool_res, "error") else bad_tool_res["error"]
    assert is_err is True
    assert "not found" in err_msg or "Unknown" in err_msg
    print("  [✓] POST /api/mcp/execute with unknown tool rejected safely.")


def main():
    print("=" * 65)
    print(" TENANTSHIELD - PHASE 2 MCP FOUNDATION VERIFICATION SUITE")
    print("=" * 65)

    test_standalone_mcp_server_stdio()
    test_backend_mcp_client_session()
    test_fastapi_mcp_endpoints()

    print("\n" + "=" * 65)
    print(" ALL PHASE 2 MCP TESTS PASSED WITH 100% SUCCESS!")
    print("=" * 65)
    return 0


if __name__ == "__main__":
    sys.exit(main())
