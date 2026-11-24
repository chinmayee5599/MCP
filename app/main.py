from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
import time

from app.config import settings
from app.mcp_client import tenancy_mcp_client, notice_mcp_client, MCPRegistry
from app.agent import agent, AgentResponse, AgentStatus

# Initialize FastAPI application
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=settings.DESCRIPTION,
    debug=settings.DEBUG,
)

# CORS middleware for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files directory
app.mount("/static", StaticFiles(directory=str(settings.STATIC_DIR)), name="static")


# -------------------------------------------------------------------------
# Request & Response Schemas
# -------------------------------------------------------------------------

class MCPToolExecutionRequest(BaseModel):
    tool_name: str = Field(..., description="The exact registered name of the MCP tool")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Arguments to pass to the MCP tool")


class MCPToolExecutionResponse(BaseModel):
    isError: bool
    tool: str
    data: Optional[Any] = None
    error: Optional[str] = None


class AgentAuditRequest(BaseModel):
    user_goal: str = Field(..., description="User's dispute statement or goal")
    context: Optional[Dict[str, Any]] = Field(default=None, description="Optional parsed context parameters")


class HumanApprovalRequest(BaseModel):
    action_type: Optional[str] = Field(default="STAGE_LEGAL_DEMAND_LETTER", description="Action to authorize, e.g. STAGE_LEGAL_DEMAND_LETTER")
    approved: Optional[bool] = Field(default=True, description="Whether the human user approves the proposed action")
    action_id: Optional[str] = Field(default=None, description="Unique action ID generated during audit")
    user_overrides: Optional[Dict[str, Any]] = Field(default=None, description="Optional customizations, e.g. names and addresses")
    reason: Optional[str] = Field(default=None, description="Optional reason if rejecting")


# -------------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------------

@app.get("/", summary="Frontend Root Page")
def index():
    """Serves the foundational frontend HTML page."""
    html_path = settings.TEMPLATES_DIR / "index.html"
    return FileResponse(html_path)


@app.get("/health", summary="Basic Health Check")
def health_check():
    """Lightweight health check endpoint for monitoring."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "timestamp": int(time.time()),
    }


@app.get("/api/status", summary="Detailed System Status")
def system_status():
    """Detailed backend status for frontend integration verification."""
    mcp_active = False
    registered_tools = []
    try:
        tenancy_mcp_client.connect()
        notice_mcp_client.connect()
        mcp_active = tenancy_mcp_client.is_connected and notice_mcp_client.is_connected
        registered_tools = [t["name"] for t in MCPRegistry.list_all_tools()]
    except Exception as e:
        print(f"[Warning] Failed to probe MCP clients: {e}")

    return {
        "status": "online",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "phase": "Phase 4 - Complete MCP Ecosystem",
        "mcp_ready": True,
        "mcp_active": mcp_active,
        "mcp_servers_available": [
            "tenancy_law_mcp (connected via stdio JSON-RPC 2.0)",
            "formal_notice_mcp (connected via stdio JSON-RPC 2.0)",
            "local_document_mcp (staged document parser)",
        ],
        "registered_mcp_tools": registered_tools,
        "agent_ready": True,
        "debug_mode": settings.DEBUG,
    }


@app.get("/api/mcp/tools", summary="List All Discovered MCP Tools")
def list_mcp_tools():
    """Returns the list of tools discovered across all active MCP servers."""
    try:
        tools = MCPRegistry.list_all_tools()
        return {
            "servers": ["tenancy_law_mcp", "formal_notice_mcp"],
            "tool_count": len(tools),
            "tools": tools,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to query MCP tools: {str(e)}")


@app.post("/api/mcp/execute", response_model=MCPToolExecutionResponse, summary="Execute MCP Tool Directly")
def execute_mcp_tool(req: MCPToolExecutionRequest):
    """Executes an MCP tool via the appropriate MCP Client Session over stdio JSON-RPC 2.0."""
    try:
        # Prevent unauthorized direct execution of consequential action tools without approval
        if req.tool_name == "stage_formal_demand_letter":
            return MCPToolExecutionResponse(
                isError=True,
                tool=req.tool_name,
                error="Security Gate: Direct execution of 'stage_formal_demand_letter' is restricted. Must use /api/agent/approve-action.",
            )

        client = MCPRegistry.get_client_for_tool(req.tool_name)
        result = client.call_tool(req.tool_name, req.arguments)
        return result
    except Exception as e:
        return MCPToolExecutionResponse(
            isError=True,
            tool=req.tool_name,
            error=f"MCP Client Execution Exception: {str(e)}",
        )


@app.post("/api/agent/audit", response_model=AgentResponse, summary="Run Complete Multi-Tool Agent Audit")
def run_agent_audit(req: AgentAuditRequest):
    """Executes the constrained multi-tool agent reasoning and MCP audit loop."""
    return agent.run(user_goal=req.user_goal, context=req.context)


@app.post("/api/agent/approve-action", summary="Human Approval & Consequential Action Execution")
def approve_agent_action(req: HumanApprovalRequest):
    """Gated execution endpoint: Executes write/action tools only after explicit human approval."""
    res = agent.execute_action(
        action_type=req.action_type,
        approved=req.approved,
        user_overrides=req.user_overrides,
        action_id=req.action_id,
    )
    # Ensure backwards-compatible status codes for testing
    if not req.approved:
        res["status"] = "REJECTED_BY_USER"
    elif req.approved and res.get("status") in ("AUTHORIZED_AND_COMPILED", "SUCCESS"):
        res["status"] = "AUTHORIZED_AND_COMPILED"
    return res


@app.post("/api/agent/reject-action", summary="Reject Proposed Action")
def reject_agent_action(req: HumanApprovalRequest):
    """Explicitly declines an action proposal with zero side-effects."""
    return agent.reject_action(action_id=req.action_id, reason=req.reason)


@app.post("/api/agent/cancel-action", summary="Cancel Proposed Action")
def cancel_agent_action(req: HumanApprovalRequest):
    """Cancels an active action proposal."""
    return agent.cancel_action(action_id=req.action_id)


@app.get("/api/agent/action/{action_id}", summary="Get Action Proposal Details")
def get_action_details(action_id: str):
    """Retrieves current state and transparency disclosures for an action proposal."""
    from app.action_manager import action_manager
    proposal = action_manager.get_proposal(action_id)
    if not proposal:
        raise HTTPException(status_code=404, detail=f"Action '{action_id}' not found.")
    return proposal


@app.on_event("shutdown")
def shutdown_event():
    """Cleans up background MCP server subprocesses on shutdown."""
    print("[Shutdown] Closing active MCP client sessions...")
    MCPRegistry.disconnect_all()
