"""TenantShield MCP Client Session Manager

Manages the lifecycle of local MCP server subprocesses communicating via JSON-RPC 2.0 over stdio.
Enables backend services and agent layers to discover tools and invoke executions securely.
"""

import sys
import json
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings


class MCPClientSession:
    """Manages an active stdio connection to an MCP server with timeout and health handling."""

    DEFAULT_TIMEOUT_SECONDS = 10.0

    def __init__(self, server_script: Path, server_name: str):
        self.server_script = server_script
        self.server_name = server_name
        self.process: Optional[subprocess.Popen] = None
        self._request_id = 0
        self._lock = threading.RLock()
        self.server_info: Dict[str, Any] = {}
        self.available_tools: List[Dict[str, Any]] = []
        self.is_connected = False

    def connect(self) -> bool:
        """Starts the MCP server subprocess and performs the initialize handshake."""
        with self._lock:
            if self.is_connected and self.process and self.process.poll() is None:
                return True

            if not self.server_script.exists():
                raise FileNotFoundError(f"MCP server script not found: {self.server_script}")

            # Start MCP server subprocess
            self.process = subprocess.Popen(
                [sys.executable, str(self.server_script)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            # 1. Send MCP Initialize Request
            init_response = self._send_request_locked(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "TenantShieldBackend",
                        "version": settings.VERSION,
                    },
                },
            )

            if not init_response or "result" not in init_response:
                self.disconnect()
                raise RuntimeError(f"Failed to initialize MCP server '{self.server_name}': {init_response}")

            self.server_info = init_response["result"].get("serverInfo", {})

            # 2. Send initialized notification (no id)
            init_notif = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
            self._write_line(init_notif)

            # 3. Discover available tools
            tools_response = self._send_request_locked("tools/list", {})
            if tools_response and "result" in tools_response:
                self.available_tools = tools_response["result"].get("tools", [])

            self.is_connected = True
            return True

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _write_line(self, line: str):
        if not self.process or not self.process.stdin:
            raise RuntimeError("MCP process stdin is not available")
        self.process.stdin.write(line + "\n")
        self.process.stdin.flush()

    def _send_request_locked(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Internal synchronous JSON-RPC request/response over stdio with error capture."""
        req_id = self._next_id()
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
        }
        if params is not None:
            payload["params"] = params

        request_str = json.dumps(payload)
        self._write_line(request_str)

        if not self.process or not self.process.stdout:
            raise RuntimeError("MCP process stdout is not available")

        response_line = self.process.stdout.readline()
        if not response_line:
            err_output = self.process.stderr.read() if self.process.stderr else "Unknown error"
            raise RuntimeError(f"MCP server closed stdout unexpectedly. Stderr: {err_output}")

        return json.loads(response_line.strip())

    def list_tools(self) -> List[Dict[str, Any]]:
        """Returns the list of tools discovered on this MCP server."""
        with self._lock:
            if not self.is_connected or not self.process or self.process.poll() is not None:
                try:
                    self.connect()
                except Exception:
                    return []
            return self.available_tools

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Calls a tool on the MCP server with arguments and returns structured output."""
        with self._lock:
            if not self.is_connected or not self.process or self.process.poll() is not None:
                try:
                    self.connect()
                except Exception as e:
                    return {
                        "isError": True,
                        "tool": tool_name,
                        "error": f"Failed to connect to MCP server '{self.server_name}': {str(e)}",
                    }

            try:
                response = self._send_request_locked(
                    "tools/call",
                    {
                        "name": tool_name,
                        "arguments": arguments,
                    },
                )
            except Exception as e:
                self.disconnect()
                return {
                    "isError": True,
                    "tool": tool_name,
                    "error": f"MCP communication failure on '{self.server_name}': {str(e)}",
                }

            if "error" in response:
                return {
                    "isError": True,
                    "error": response["error"].get("message", "Unknown RPC error"),
                    "raw": response,
                }

            result = response.get("result", {})
            is_error = result.get("isError", False)
            content = result.get("content", [])

            # Extract text payload
            text_result = ""
            if content and isinstance(content, list) and len(content) > 0:
                text_result = content[0].get("text", "")

            # Attempt parsing text as JSON if possible
            parsed_data = None
            if not is_error:
                try:
                    parsed_data = json.loads(text_result)
                except Exception:
                    parsed_data = text_result

            return {
                "isError": is_error,
                "tool": tool_name,
                "data": parsed_data,
                "error": text_result if is_error else None,
            }

    def disconnect(self):
        """Cleanly terminates the MCP server subprocess."""
        with self._lock:
            if self.process:
                try:
                    if self.process.stdin:
                        self.process.stdin.close()
                    self.process.terminate()
                    self.process.wait(timeout=2)
                except Exception:
                    self.process.kill()
                finally:
                    self.process = None
            self.is_connected = False


# Server 1: Tenancy Law & Legal Intelligence (READ / ANALYZE)
tenancy_mcp_client = MCPClientSession(
    server_script=settings.MCP_SERVERS_DIR / "tenancy_law_server.py",
    server_name="tenancy_law_mcp",
)

# Server 2: Formal Notice & Document Compilation (WRITE / ACTION)
notice_mcp_client = MCPClientSession(
    server_script=settings.MCP_SERVERS_DIR / "notice_server.py",
    server_name="formal_notice_mcp",
)


class MCPRegistry:
    """Multi-server router directing tool calls to appropriate MCP server."""

    @staticmethod
    def get_client_for_tool(tool_name: str) -> MCPClientSession:
        if tool_name in ("get_statutory_deadlines", "evaluate_wear_and_tear"):
            return tenancy_mcp_client
        elif tool_name == "stage_formal_demand_letter":
            return notice_mcp_client
        else:
            raise ValueError(f"Unknown MCP tool '{tool_name}' — not registered in any MCP server.")

    @staticmethod
    def list_all_tools() -> List[Dict[str, Any]]:
        tools = []
        for client in (tenancy_mcp_client, notice_mcp_client):
            try:
                tools.extend(client.list_tools())
            except Exception as e:
                print(f"[Warning] Tool listing failed for {client.server_name}: {e}")
        return tools

    @staticmethod
    def disconnect_all():
        tenancy_mcp_client.disconnect()
        notice_mcp_client.disconnect()
