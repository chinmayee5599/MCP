"""Formal Notice MCP Server (formal_notice_mcp)

Dedicated MCP server implementing JSON-RPC 2.0 over stdio for ACTION/WRITE operations.
Assembles, formats, and stages courtroom-ready formal legal demand letters.
"""

import sys
import json
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

MCP_PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "formal_notice_mcp"
SERVER_VERSION = "0.1.0"

TOOL_STAGE_FORMAL_DEMAND = {
    "name": "stage_formal_demand_letter",
    "description": (
        "ACTION/WRITE TOOL: Assembles, formats, and stages a courtroom-ready formal legal demand letter "
        "to the landlord citing statutory code violations, deadlines, itemized unlawful deductions, "
        "and statutory bad-faith damages. Requires human approval before final dispatch."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "tenant_name": {
                "type": "string",
                "description": "Full name of the tenant",
            },
            "landlord_name": {
                "type": "string",
                "description": "Full name of the landlord or property management entity",
            },
            "rental_address": {
                "type": "string",
                "description": "Rental property address under lease",
            },
            "move_out_date": {
                "type": "string",
                "description": "Date tenant surrendered possession (e.g. 'October 1, 2026')",
            },
            "dispute_amount": {
                "type": "number",
                "description": "Total principal deposit amount unlawfully withheld (must be > 0)",
            },
            "statutory_penalties": {
                "type": "number",
                "description": "Eligible statutory bad-faith penalties under law",
            },
            "violations": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of specific statutory and factual violations detected",
            },
            "statutory_citation": {
                "type": "string",
                "description": "Governing state statute (e.g. 'California Civil Code § 1950.5')",
            },
            "demand_deadline_days": {
                "type": "integer",
                "description": "Number of calendar days given to remit refund before filing in Small Claims Court (default 10)",
            },
        },
        "required": ["dispute_amount", "violations", "statutory_citation"],
    },
}


def execute_stage_formal_demand(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Compiles a formal legal demand letter with strict input validation."""
    if not isinstance(arguments, dict):
        return {"isError": True, "error": "Invalid arguments: expected JSON object."}

    dispute_amount = arguments.get("dispute_amount")
    violations = arguments.get("violations")
    statutory_citation = arguments.get("statutory_citation")

    # Strict Validation
    if dispute_amount is None or not isinstance(dispute_amount, (int, float)) or dispute_amount <= 0:
        return {"isError": True, "error": "Validation Error: 'dispute_amount' must be a positive number greater than 0."}

    if not violations or not isinstance(violations, list) or len(violations) == 0:
        return {"isError": True, "error": "Validation Error: 'violations' must be a non-empty list of violation statements."}

    if not statutory_citation or not isinstance(statutory_citation, str):
        return {"isError": True, "error": "Validation Error: 'statutory_citation' must be a non-empty string."}

    tenant_name = arguments.get("tenant_name") or "Tenant"
    landlord_name = arguments.get("landlord_name") or "Landlord / Property Management"
    rental_address = arguments.get("rental_address") or "[Rental Property Address]"
    move_out_date = arguments.get("move_out_date") or "[Move-Out Date]"
    statutory_penalties = float(arguments.get("statutory_penalties") or 0.0)
    demand_days = int(arguments.get("demand_deadline_days") or 10)

    amount_float = float(dispute_amount)
    total_claim = amount_float + statutory_penalties

    today_str = datetime.now().strftime("%B %d, %Y")
    deadline_date = (datetime.now() + timedelta(days=demand_days)).strftime("%B %d, %Y")

    # Format violations list
    violations_text = "\n".join([f"  • {v}" for v in violations])

    # Assemble Courtroom-Ready Formal Notice Text
    letter_text = f"""
================================================================================
                    FORMAL LEGAL NOTICE & DEMAND FOR PAYMENT
                    PURSUANT TO {statutory_citation.upper()}
================================================================================

DATE: {today_str}
VIA: CERTIFIED MAIL & ELECTRONIC DELIVERY

TO:
{landlord_name}
RE: Former Tenancy at {rental_address}

FROM:
{tenant_name}

SUBJECT: FINAL DEMAND FOR IMMEDIATE RETURN OF SECURITY DEPOSIT UNDER {statutory_citation}

Dear {landlord_name},

Please take formal notice that this letter serves as a final demand for the immediate return 
of security deposit funds unlawfully withheld following the surrender of the premises 
located at {rental_address} on {move_out_date}.

FACTUAL & STATUTORY BASIS OF DISPUTE:
An independent audit of your deduction statement has identified the following statutory violations:
{violations_text}

Under {statutory_citation}, landlords are legally prohibited from withholding funds for 
ordinary wear and tear, and failure to strictly comply with mandatory statutory deadlines 
constitutes an automatic forfeiture of the right to retain any portion of the deposit.

MONETARY RECOVERY DEMAND:
  1. Principal Security Deposit Unlawfully Withheld:  ${amount_float:,.2f}
  2. Statutory Bad-Faith Damages Claimed:             ${statutory_penalties:,.2f}
  -------------------------------------------------------------
  TOTAL DEMAND:                                      ${total_claim:,.2f}

DEMAND FOR REMEDY:
Full payment of ${amount_float:,.2f} must be received by no later than {deadline_date} 
({demand_days} calendar days from receipt of this notice). Payment should be delivered via 
certified check or direct electronic transfer.

NOTICE OF LEGAL PROCEEDINGS:
If full payment is not remitted by {deadline_date}, I will immediately initiate formal legal action 
in Small Claims Court. In addition to the principal deposit of ${amount_float:,.2f}, I will petition 
the court for the maximum statutory bad-faith penalty of ${statutory_penalties:,.2f}, statutory interest, 
and all recoverable court filing and service fees.

Sincerely,

________________________________________
{tenant_name}
Former Tenant, {rental_address}
================================================================================
""".strip()

    return {
        "isError": False,
        "result": {
            "status": "STAGED_FORMAL_NOTICE",
            "document_title": f"Formal Legal Demand Letter ({statutory_citation})",
            "recipient": landlord_name,
            "tenant": tenant_name,
            "rental_address": rental_address,
            "statutory_citation": statutory_citation,
            "dispute_amount": amount_float,
            "statutory_penalties": statutory_penalties,
            "total_demand": total_claim,
            "payment_deadline_days": demand_days,
            "payment_deadline_date": deadline_date,
            "full_letter_text": letter_text,
            "requires_human_approval": True,
            "timestamp": int(time.time()),
        },
    }


TOOLS = {
    "stage_formal_demand_letter": {
        "definition": TOOL_STAGE_FORMAL_DEMAND,
        "handler": execute_stage_formal_demand,
    }
}


def handle_initialize(params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        "instructions": "Formal document compilation and action staging MCP server.",
    }


def handle_tools_list(params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return {"tools": [tool["definition"] for tool in TOOLS.values()]}


def handle_tools_call(params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not params or not isinstance(params, dict):
        return {"content": [{"type": "text", "text": "Error: Missing parameters for tools/call"}], "isError": True}

    tool_name = params.get("name")
    arguments = params.get("arguments", {})

    if tool_name not in TOOLS:
        return {"content": [{"type": "text", "text": f"Error: Tool '{tool_name}' not found."}], "isError": True}

    execution_result = TOOLS[tool_name]["handler"](arguments)
    if execution_result.get("isError"):
        return {"content": [{"type": "text", "text": execution_result["error"]}], "isError": True}

    return {
        "content": [{"type": "text", "text": json.dumps(execution_result["result"], indent=2)}],
        "isError": False,
    }


def process_json_rpc(request_str: str) -> Optional[str]:
    try:
        request = json.loads(request_str)
    except json.JSONDecodeError as e:
        return json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {str(e)}"}})

    if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
        return json.dumps({"jsonrpc": "2.0", "id": request.get("id"), "error": {"code": -32600, "message": "Invalid Request"}})

    req_id = request.get("id")
    method = request.get("method")
    params = request.get("params")

    if req_id is None:
        return None

    try:
        if method == "initialize":
            result = handle_initialize(params)
        elif method == "tools/list":
            result = handle_tools_list(params)
        elif method == "tools/call":
            result = handle_tools_call(params)
        elif method == "ping":
            result = {}
        else:
            return json.dumps({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method not found: '{method}'"}})
        return json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result})
    except Exception as e:
        return json.dumps({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32603, "message": f"Internal RPC error: {str(e)}"}})


def run_stdio_server():
    sys.stderr.write(f"[{SERVER_NAME}] Starting MCP Stdio Server v{SERVER_VERSION}...\n")
    sys.stderr.flush()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        response = process_json_rpc(line)
        if response:
            sys.stdout.write(response + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    run_stdio_server()
