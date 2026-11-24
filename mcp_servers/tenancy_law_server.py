"""Tenancy Law MCP Server (tenancy_law_mcp)

Standard Model Context Protocol (MCP) server implementing JSON-RPC 2.0 over stdio.
Provides deterministic legal intelligence regarding statutory deposit return deadlines,
wear-and-tear classifications, and bad-faith penalty multipliers.
"""

import sys
import json
import re
from pathlib import Path
from typing import Any, Dict, Optional

# Protocol Constants
MCP_PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "tenancy_law_mcp"
SERVER_VERSION = "0.2.0"

BASE_DIR = Path(__file__).resolve().parent.parent
LAWS_FILE = BASE_DIR / "test_data" / "mock_laws.json"


def load_laws_database() -> Dict[str, Any]:
    """Loads the statutory tenancy laws, wear benchmarks, and aliases from disk."""
    if not LAWS_FILE.exists():
        return {"jurisdictions": {}, "wear_and_tear_benchmarks": {}, "aliases": {}}
    with open(LAWS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


LAWS_DB = load_laws_database()


# -------------------------------------------------------------------------
# Tool 1: get_statutory_deadlines (READ)
# -------------------------------------------------------------------------

TOOL_GET_STATUTORY_DEADLINES = {
    "name": "get_statutory_deadlines",
    "description": (
        "Retrieves jurisdiction-specific statutory deposit refund deadlines, "
        "statutory forfeiture rules, bad-faith penalty multipliers, allowable "
        "deductions, and prohibited wear-and-tear standards."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "jurisdiction": {
                "type": "string",
                "description": "The state or city jurisdiction (e.g., 'California', 'CA', 'New York', 'NYC')",
            }
        },
        "required": ["jurisdiction"],
    },
}


def execute_get_statutory_deadlines(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Executes the get_statutory_deadlines tool with strict validation."""
    if not isinstance(arguments, dict):
        return {
            "isError": True,
            "error": "Invalid arguments: expected a JSON object with 'jurisdiction' key.",
        }

    raw_jurisdiction = arguments.get("jurisdiction")
    if not raw_jurisdiction or not isinstance(raw_jurisdiction, str):
        return {
            "isError": True,
            "error": "Validation Error: 'jurisdiction' must be a non-empty string.",
        }

    normalized = raw_jurisdiction.strip().lower()
    if not normalized:
        return {
            "isError": True,
            "error": "Validation Error: 'jurisdiction' cannot be empty or whitespace.",
        }

    # Resolve alias
    aliases = LAWS_DB.get("aliases", {})
    canonical_key = aliases.get(normalized)

    jurisdictions = LAWS_DB.get("jurisdictions", {})
    if not canonical_key or canonical_key not in jurisdictions:
        available = list(jurisdictions.keys())
        return {
            "isError": True,
            "error": (
                f"Unsupported jurisdiction '{raw_jurisdiction}'. "
                f"Currently supported jurisdictions: {', '.join(available)} (or aliases: CA, NY, NYC, LA)."
            ),
        }

    data = jurisdictions[canonical_key]
    return {
        "isError": False,
        "result": data,
    }


# -------------------------------------------------------------------------
# Tool 2: evaluate_wear_and_tear (READ / ANALYZE)
# -------------------------------------------------------------------------

TOOL_EVALUATE_WEAR_AND_TEAR = {
    "name": "evaluate_wear_and_tear",
    "description": (
        "Audits an itemized landlord deduction (e.g. painting, carpet, cleaning, nail holes) "
        "against the tenant's duration of occupancy, useful life benchmarks, and statutory wear-and-tear rules."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "item_category": {
                "type": "string",
                "description": "Description or category of the deduction item (e.g., 'painting', 'carpet cleaning', 'wall scuffs')",
            },
            "tenancy_years": {
                "type": "number",
                "description": "Duration of the tenancy in years (e.g. 3.0)",
            },
            "amount": {
                "type": "number",
                "description": "Amount deducted by the landlord in USD (e.g. 600.0)",
            },
            "jurisdiction": {
                "type": "string",
                "description": "Jurisdiction, e.g. 'California' or 'New York'",
            },
        },
        "required": ["item_category", "tenancy_years", "amount", "jurisdiction"],
    },
}


def execute_evaluate_wear_and_tear(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Executes the evaluate_wear_and_tear analysis with strict validation."""
    if not isinstance(arguments, dict):
        return {"isError": True, "error": "Invalid arguments: expected JSON object."}

    item_category = arguments.get("item_category")
    tenancy_years = arguments.get("tenancy_years")
    amount = arguments.get("amount")
    jurisdiction = arguments.get("jurisdiction")

    # Strict Validation
    if not item_category or not isinstance(item_category, str):
        return {"isError": True, "error": "Validation Error: 'item_category' must be a non-empty string."}

    if tenancy_years is None or not isinstance(tenancy_years, (int, float)) or tenancy_years < 0:
        return {"isError": True, "error": "Validation Error: 'tenancy_years' must be a non-negative number."}

    if amount is None or not isinstance(amount, (int, float)) or amount < 0:
        return {"isError": True, "error": "Validation Error: 'amount' must be a non-negative number."}

    if not jurisdiction or not isinstance(jurisdiction, str):
        return {"isError": True, "error": "Validation Error: 'jurisdiction' must be a non-empty string."}

    normalized_jur = jurisdiction.strip().lower()
    canonical_jur = LAWS_DB.get("aliases", {}).get(normalized_jur, normalized_jur)
    if canonical_jur not in LAWS_DB.get("jurisdictions", {}):
        return {"isError": True, "error": f"Validation Error: Unsupported jurisdiction '{jurisdiction}'."}

    statute_info = LAWS_DB["jurisdictions"][canonical_jur]
    citation = statute_info["statute_citation"]

    # Match item category against benchmarks
    benchmarks = LAWS_DB.get("wear_and_tear_benchmarks", {})
    matched_benchmark = None
    item_lower = item_category.strip().lower()

    for cat_key, benchmark in benchmarks.items():
        if cat_key in item_lower:
            matched_benchmark = benchmark
            break
        for kw in benchmark.get("keywords", []):
            if re.search(r"\b" + re.escape(kw) + r"\b", item_lower):
                matched_benchmark = benchmark
                break
        if matched_benchmark:
            break

    # If category not explicitly in benchmark, default to generic maintenance
    if not matched_benchmark:
        matched_benchmark = benchmarks.get("hardware_and_fixtures", {
            "canonical_category": "general_maintenance",
            "useful_life_years": 3.0,
            "statutory_standard": "Standard residential wear and tear cannot be billed to tenant.",
            "auto_wear_threshold_years": 2.0,
        })

    cat_name = matched_benchmark.get("canonical_category", "general_maintenance")
    useful_life = float(matched_benchmark.get("useful_life_years", 3.0))
    threshold_years = float(matched_benchmark.get("auto_wear_threshold_years", 2.0))
    standard_text = matched_benchmark.get("statutory_standard", "")

    # Evaluation logic
    tenancy_float = float(tenancy_years)
    amount_float = float(amount)

    if tenancy_float >= threshold_years:
        # 100% Ordinary Wear and Tear
        classification = "ORDINARY_WEAR_AND_TEAR"
        lawful = False
        allowable_charge = 0.0
        unlawful_charge = amount_float
        explanation = (
            f"After {tenancy_float:.1f} years of occupancy, {cat_name} exceeds its statutory threshold "
            f"({threshold_years:.1f} years). Under {citation}, repainting/restoration is 100% ordinary "
            f"wear and tear and the landlord cannot deduct any portion of this ${amount_float:,.2f} cost."
        )
    else:
        # Proration calculation
        remaining_ratio = max(0.0, (useful_life - tenancy_float) / useful_life)
        max_allowable = round(amount_float * remaining_ratio, 2)
        allowable_charge = max_allowable
        unlawful_charge = round(amount_float - allowable_charge, 2)
        lawful = unlawful_charge == 0.0
        classification = "PRORATED_DEPRECIATION"
        explanation = (
            f"Based on a {useful_life:.1f}-year useful life, the asset has {remaining_ratio * 100:.0f}% useful life remaining. "
            f"Maximum allowable charge is ${allowable_charge:,.2f}. The remaining ${unlawful_charge:,.2f} is an unlawful markup."
        )

    return {
        "isError": False,
        "result": {
            "item_category": cat_name,
            "raw_input_item": item_category,
            "tenancy_years": tenancy_float,
            "billed_amount": amount_float,
            "allowable_charge": allowable_charge,
            "unlawful_charge": unlawful_charge,
            "is_lawful": lawful,
            "classification": classification,
            "useful_life_years": useful_life,
            "statutory_citation": citation,
            "legal_standard": standard_text,
            "explanation": explanation,
        },
    }


# Map of available tools on tenancy_law_mcp
TOOLS = {
    "get_statutory_deadlines": {
        "definition": TOOL_GET_STATUTORY_DEADLINES,
        "handler": execute_get_statutory_deadlines,
    },
    "evaluate_wear_and_tear": {
        "definition": TOOL_EVALUATE_WEAR_AND_TEAR,
        "handler": execute_evaluate_wear_and_tear,
    },
}


# -------------------------------------------------------------------------
# MCP JSON-RPC 2.0 Request Handlers
# -------------------------------------------------------------------------

def handle_initialize(params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        "instructions": "Authoritative municipal and state tenancy law intelligence server.",
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
