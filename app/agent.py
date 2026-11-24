"""TenantShield AI Agent Core — Phase 4

Full Multi-Tool MCP Orchestration with Strict Human-in-the-Loop Governance:
1. READ: Queries 'get_statutory_deadlines' (Statutory timeline & forfeiture rules)
2. READ/ANALYZE: Queries 'evaluate_wear_and_tear' (Useful life benchmarks & depreciation)
3. SYNTHESIS: Compares results, calculates recoverable sums, and formulates proposed action
4. GATING: Halts execution at AWAITING_APPROVAL
5. ACTION/WRITE: Upon explicit human approval, executes 'stage_formal_demand_letter' on formal_notice_mcp
"""

import re
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field

from app.mcp_client import tenancy_mcp_client, notice_mcp_client, MCPRegistry
from app.action_manager import action_manager, ActionLifecycleState, ProposedActionDetails


class AgentStatus(str, Enum):
    IDLE = "IDLE"
    ANALYZING = "ANALYZING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    AUTHORIZED = "AUTHORIZED"
    REJECTED = "REJECTED"
    RESOLVED = "RESOLVED"
    ERROR = "ERROR"


class ProposedAction(BaseModel):
    action_id: str = Field(default="", description="Unique identifier for the action proposal")
    action_type: str = Field(..., description="Action identifier: STAGE_LEGAL_DEMAND_LETTER")
    risk_level: str = Field(default="HIGH", description="Risk level: HIGH")
    target: str = Field(..., description="Entity affected by the action")
    dispute_amount: float = Field(default=0.0, description="Amount to be reclaimed")
    statutory_penalties: float = Field(default=0.0, description="Eligible statutory bad-faith penalties")
    statutory_citation: str = Field(..., description="Governing legal citation")
    violations: List[str] = Field(default_factory=list, description="Itemized legal violations")
    description: str = Field(..., description="Action summary")
    
    # 5 Mandatory Transparency Disclosures
    what: str = Field(default="", description="What the AI proposes to do")
    why: str = Field(default="", description="Why the AI proposes this action")
    data_involved: Dict[str, Any] = Field(default_factory=dict, description="Data parameters involved")
    consequences_if_approved: str = Field(default="", description="What will happen if approved")
    what_will_not_happen: str = Field(default="", description="What will NOT happen")

    requires_approval: bool = True
    approved: bool = False
    editable_fields: List[str] = Field(default_factory=lambda: [
        "tenant_name", "landlord_name", "rental_address", "move_out_date", "demand_deadline_days"
    ])
    staged_document: Optional[Dict[str, Any]] = None


class AgentResponse(BaseModel):
    user_goal: str
    status: AgentStatus
    decision_summaries: List[str] = Field(default_factory=list)
    tools_invoked: List[Dict[str, Any]] = Field(default_factory=list)
    findings: Dict[str, Any] = Field(default_factory=dict)
    itemized_audits: List[Dict[str, Any]] = Field(default_factory=list)
    proposed_action: Optional[ProposedAction] = None
    error: Optional[str] = None


class TenantShieldAgent:
    """Intelligent agent orchestrator executing genuine multi-tool MCP workflows."""

    MAX_TOOL_CALLS = 5

    def __init__(self, tenancy_client=None, notice_client=None, mcp_client=None):
        self.tenancy_client = tenancy_client or mcp_client or tenancy_mcp_client
        self.notice_client = notice_client or notice_mcp_client
        self._last_staged_action: Optional[ProposedAction] = None

    def _extract_jurisdiction(self, text: str) -> Optional[str]:
        lowered = text.lower()
        jurisdiction_keywords = [
            ("los angeles", "California"),
            ("san francisco", "California"),
            ("san diego", "California"),
            ("california", "California"),
            ("ca", "California"),
            ("new york city", "New York"),
            ("new york", "New York"),
            ("nyc", "New York"),
            ("ny", "New York"),
        ]
        for kw, canonical in jurisdiction_keywords:
            if re.search(r"\b" + re.escape(kw) + r"\b", lowered):
                return canonical
        return None

    def _extract_tenancy_years(self, text: str) -> float:
        year_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:years?|yrs?)", text.lower())
        if year_match:
            try:
                return float(year_match.group(1))
            except ValueError:
                pass
        month_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:months?|mos?)", text.lower())
        if month_match:
            try:
                return round(float(month_match.group(1)) / 12.0, 2)
            except ValueError:
                pass
        return 1.0  # Default to 1.0 year if unspecified

    def _extract_days_elapsed(self, text: str) -> Optional[int]:
        match = re.search(r"(\d+)\s*(?:calendar\s*)?days", text.lower())
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                pass
        return None

    def _extract_line_items(self, text: str) -> List[Dict[str, Any]]:
        """Parses itemized deductions and amounts from free-form text."""
        items = []
        # Pattern e.g. "$600 for wall painting", "$450 for carpet cleaning"
        patterns = [
            r"\$\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{2})?)\s+(?:for\s+)?([a-zA-Z\s]+?)(?:,|\.|\band\b|$)",
            r"([a-zA-Z\s]+?):\s*\$\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{2})?)",
        ]

        for p in patterns:
            matches = re.findall(p, text, re.IGNORECASE)
            for m in matches:
                if len(m) == 2:
                    if m[0].replace(",", "").replace(".", "").isdigit():
                        amt_str, desc = m[0], m[1].strip()
                    else:
                        desc, amt_str = m[0].strip(), m[1]
                    try:
                        amt = float(amt_str.replace(",", ""))
                        if amt > 0 and len(desc) > 2 and not any(i["category"] == desc for i in items):
                            items.append({"category": desc, "amount": amt})
                    except ValueError:
                        continue

        # Fallback if no structured breakdown found but amounts exist
        if not items:
            amounts = re.findall(r"\$\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{2})?)", text)
            if amounts:
                try:
                    total_amt = float(amounts[0].replace(",", ""))
                    items.append({"category": "general deductions", "amount": total_amt})
                except ValueError:
                    pass

        return items

    def run(self, user_goal: str, context: Optional[Dict[str, Any]] = None) -> AgentResponse:
        """Executes the complete multi-tool MCP audit workflow."""
        context = context or {}
        decision_summaries: List[str] = []
        tools_invoked: List[Dict[str, Any]] = []
        itemized_audits: List[Dict[str, Any]] = []
        visited_calls: Set[str] = set()

        # Step 1: Input Validation
        if not user_goal or not user_goal.strip():
            return AgentResponse(
                user_goal=user_goal or "",
                status=AgentStatus.ERROR,
                decision_summaries=["Received empty user goal. Cannot formulate action plan."],
                error="Invalid Request: User goal cannot be empty.",
            )

        # Step 2: Extraction
        jurisdiction = context.get("jurisdiction") or self._extract_jurisdiction(user_goal)
        days_elapsed = context.get("days_elapsed") or self._extract_days_elapsed(user_goal)
        tenancy_years = context.get("tenancy_years") or self._extract_tenancy_years(user_goal)
        line_items = context.get("line_items") or self._extract_line_items(user_goal)

        if not jurisdiction:
            decision_summaries.append(
                "I analyzed your request but could not identify a supported jurisdiction. "
                "Supported jurisdictions: California (CA, Los Angeles, San Francisco) and New York (NY, NYC)."
            )
            return AgentResponse(
                user_goal=user_goal,
                status=AgentStatus.ERROR,
                decision_summaries=decision_summaries,
                error="Unknown Jurisdiction: Please specify California or New York.",
            )

        # -----------------------------------------------------------------
        # STEP 3: Call Tool A (READ) -> get_statutory_deadlines
        # -----------------------------------------------------------------
        call_sig_a = f"get_statutory_deadlines:{jurisdiction.lower()}"
        visited_calls.add(call_sig_a)

        try:
            deadline_result = self.tenancy_client.call_tool(
                "get_statutory_deadlines",
                {"jurisdiction": jurisdiction},
            )
            tools_invoked.append({
                "tool": "get_statutory_deadlines",
                "arguments": {"jurisdiction": jurisdiction},
                "isError": deadline_result.get("isError", False),
            })
        except Exception as e:
            return AgentResponse(
                user_goal=user_goal,
                status=AgentStatus.ERROR,
                decision_summaries=[f"Failed to connect to Tenancy Law MCP Server: {str(e)}"],
                error=f"MCP Service Unavailable: {str(e)}",
            )

        if deadline_result.get("isError"):
            err_msg = deadline_result.get("error", "Failed to retrieve statutory deadlines")
            return AgentResponse(
                user_goal=user_goal,
                status=AgentStatus.ERROR,
                decision_summaries=[f"Statutory Law MCP Tool returned error: {err_msg}"],
                tools_invoked=tools_invoked,
                error=err_msg,
            )

        statute_data = deadline_result.get("data")
        if not isinstance(statute_data, dict) or "statutory_deadline_days" not in statute_data:
            return AgentResponse(
                user_goal=user_goal,
                status=AgentStatus.ERROR,
                decision_summaries=["Tool returned unexpected or incomplete statutory schema."],
                tools_invoked=tools_invoked,
                error="Malformed Tool Response: Missing required statutory fields.",
            )

        statutory_deadline = statute_data["statutory_deadline_days"]
        citation = statute_data.get("statute_citation", "State Housing Statute")
        forfeiture_rule = statute_data.get("forfeiture_on_deadline_breach", False)
        penalty_multiplier = statute_data.get("bad_faith_penalty_multiplier", 1.0)
        display_name = statute_data.get("display_name", jurisdiction)

        decision_summaries.append(
            f"I checked {citation} and found that landlords in {display_name} must return security deposits "
            f"and provide an itemized statement within {statutory_deadline} calendar days."
        )

        deadline_violated = False
        if days_elapsed is not None and days_elapsed > statutory_deadline:
            deadline_violated = True
            decision_summaries.append(
                f"Notice was delivered {days_elapsed} days after move-out, which exceeds the {statutory_deadline}-day statutory limit. "
                f"Under {citation}, the landlord has forfeited the legal right to retain any portion of your deposit."
            )

        # -----------------------------------------------------------------
        # STEP 4: Call Tool B (READ/ANALYZE) -> evaluate_wear_and_tear
        # -----------------------------------------------------------------
        total_billed = 0.0
        total_unlawful_substantive = 0.0
        violations_list = []

        if deadline_violated:
            violations_list.append(
                f"Statutory Deadline Breach: Notice was delivered on Day {days_elapsed}, exceeding the mandatory "
                f"{statutory_deadline}-day limit under {citation}. Under state law, this triggers automatic forfeiture."
            )

        for item in line_items:
            cat = item["category"]
            amt = item["amount"]
            total_billed += amt

            call_sig_b = f"evaluate_wear_and_tear:{cat}:{amt}:{tenancy_years}"
            if call_sig_b in visited_calls:
                continue  # Repeated execution safeguard
            visited_calls.add(call_sig_b)

            if len(tools_invoked) >= self.MAX_TOOL_CALLS:
                break  # Max tool calls limit safeguard

            try:
                wear_result = self.tenancy_client.call_tool(
                    "evaluate_wear_and_tear",
                    {
                        "item_category": cat,
                        "tenancy_years": tenancy_years,
                        "amount": amt,
                        "jurisdiction": jurisdiction,
                    },
                )
                tools_invoked.append({
                    "tool": "evaluate_wear_and_tear",
                    "arguments": {"item_category": cat, "tenancy_years": tenancy_years, "amount": amt},
                    "isError": wear_result.get("isError", False),
                })

                if not wear_result.get("isError") and isinstance(wear_result.get("data"), dict):
                    w_data = wear_result["data"]
                    itemized_audits.append(w_data)
                    unlawful = w_data.get("unlawful_charge", 0.0)
                    total_unlawful_substantive += unlawful

                    if unlawful > 0:
                        decision_summaries.append(
                            f"I analyzed the deduction of ${amt:,.2f} for '{cat}' over {tenancy_years:.1f} years of occupancy "
                            f"and found that under {citation}, ${unlawful:,.2f} constitutes ordinary wear and tear."
                        )
                        violations_list.append(
                            f"Unlawful Wear & Tear Deduction: ${unlawful:,.2f} for '{cat}' exceeds allowable useful life standards "
                            f"under {citation}."
                        )
                else:
                    # Partial tool failure: record and continue gracefully
                    decision_summaries.append(f"Could not complete wear-and-tear audit for '{cat}'; relying on deadline audit.")
            except Exception as e:
                # Partial tool failure recovery
                decision_summaries.append(f"Wear-and-tear tool temporarily unavailable for '{cat}': {str(e)}")

        # -----------------------------------------------------------------
        # STEP 5: Synthesis & Dispute Determination
        # -----------------------------------------------------------------
        # Safe fallback check for amounts mentioned in text
        fallback_amounts = re.findall(r"\$\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{2})?)", user_goal)
        fallback_amount = float(fallback_amounts[0].replace(",", "")) if fallback_amounts else 0.0

        # If deadline violated, 100% of deposit is recoverable under forfeiture
        if deadline_violated:
            final_dispute_amount = total_billed if total_billed > 0 else fallback_amount
        else:
            final_dispute_amount = total_unlawful_substantive if total_unlawful_substantive > 0 else (total_billed if total_billed > 0 else fallback_amount)

        potential_penalties = round(final_dispute_amount * penalty_multiplier, 2) if final_dispute_amount > 0 else 0.0

        if potential_penalties > 0:
            decision_summaries.append(
                f"You are also eligible to petition for statutory bad-faith damages up to ${potential_penalties:,.2f} "
                f"({penalty_multiplier:.0f}x deposit amount)."
            )

        # -----------------------------------------------------------------
        # STEP 6: Propose Consequential Action & Halt at Approval Gate
        # -----------------------------------------------------------------
        proposed_action = None
        if final_dispute_amount > 0:
            decision_summaries.append(
                f"The best option is to issue a formal legal demand letter citing {citation} for the return of "
                f"${final_dispute_amount:,.2f}."
            )
            decision_summaries.append(
                "This action will generate a legally binding formal demand notice with statutory citations. "
                "Approval is required before continuing."
            )

            what_desc = f"Compile and stage a formal legal demand notice demanding the full return of ${final_dispute_amount:,.2f}."
            why_desc = (
                f"Notice received on Day {days_elapsed or 'N/A'} breached the statutory deadline under {citation}. "
                f"Furthermore, deductions totaling ${total_unlawful_substantive:,.2f} violate normal wear-and-tear guidelines."
            )
            consequences = (
                f"A certified-mail ready formal demand letter citing {citation} will be compiled and made available. "
                f"It demands payment within 10 calendar days before small claims filing."
            )
            w_not_happen = (
                "TenantShield will NOT automatically email or send mail to your landlord without your explicit consent. "
                "It will NOT file court petitions automatically, and will NOT charge your bank account."
            )

            # Register with Action Manager
            action_prop = action_manager.create_proposal(
                action_type="STAGE_LEGAL_DEMAND_LETTER",
                target="Landlord / Property Management",
                what=what_desc,
                why=why_desc,
                data_involved={
                    "jurisdiction": display_name,
                    "statutory_citation": citation,
                    "dispute_amount": final_dispute_amount,
                    "statutory_penalties": potential_penalties,
                    "total_claim": final_dispute_amount + potential_penalties,
                    "violations": violations_list if violations_list else [f"Unlawful deposit withholding under {citation}"],
                    "days_elapsed": days_elapsed,
                    "statutory_deadline_days": statutory_deadline,
                    "demand_deadline_days": 10,
                },
                consequences_if_approved=consequences,
                what_will_not_happen=w_not_happen,
                risk_level="HIGH",
            )

            proposed_action = ProposedAction(
                action_id=action_prop.action_id,
                action_type="STAGE_LEGAL_DEMAND_LETTER",
                risk_level="HIGH",
                target="Landlord / Property Management",
                dispute_amount=final_dispute_amount,
                statutory_penalties=potential_penalties,
                statutory_citation=citation,
                violations=violations_list if violations_list else [f"Unlawful deposit withholding under {citation}"],
                description=(
                    f"Draft and stage formal demand letter demanding full refund of ${final_dispute_amount:,.2f} "
                    f"due to statutory violations under {citation}."
                ),
                what=what_desc,
                why=why_desc,
                data_involved=action_prop.data_involved,
                consequences_if_approved=consequences,
                what_will_not_happen=w_not_happen,
                requires_approval=True,
                approved=False,
            )
            self._last_staged_action = proposed_action
            final_status = AgentStatus.AWAITING_APPROVAL
        else:
            decision_summaries.append(
                "Based on the provided information, no statutory deadline breach or unlawful wear-and-tear deductions were detected."
            )
            final_status = AgentStatus.RESOLVED

        return AgentResponse(
            user_goal=user_goal,
            status=final_status,
            decision_summaries=decision_summaries,
            tools_invoked=tools_invoked,
            findings={
                "jurisdiction": display_name,
                "statutory_citation": citation,
                "statutory_deadline_days": statutory_deadline,
                "days_elapsed": days_elapsed,
                "deadline_violated": deadline_violated,
                "total_billed": total_billed,
                "dispute_amount": final_dispute_amount,
                "recoverable_principal": final_dispute_amount,
                "statutory_penalties_eligible": potential_penalties,
                "total_claim": final_dispute_amount + potential_penalties,
            },
            itemized_audits=itemized_audits,
            proposed_action=proposed_action,
        )

    def execute_action(
        self,
        action_type: str,
        approved: bool,
        user_overrides: Optional[Dict[str, Any]] = None,
        action_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """ACTION/WRITE EXECUTION: Safely delegated to ActionManager with idempotency."""
        # Resolve action_id if not explicitly provided
        act_id = action_id or (self._last_staged_action.action_id if self._last_staged_action else None)

        if not approved:
            if act_id:
                action_manager.reject_action(act_id, reason="Declined by user.")
            return {
                "success": False,
                "status": "REJECTED_BY_USER",
                "message": "Action cancelled by user. No document compiled or dispatched.",
                "approved": False,
            }

        if not act_id:
            return {
                "success": False,
                "status": "ERROR",
                "message": "No staged action available to authorize.",
                "approved": False,
            }

        result = action_manager.approve_and_execute(act_id, user_overrides=user_overrides)
        if result.get("success"):
            result["status"] = "AUTHORIZED_AND_COMPILED"
            if self._last_staged_action:
                self._last_staged_action.approved = True
                self._last_staged_action.staged_document = result.get("document")

        return result

    def reject_action(self, action_id: Optional[str] = None, reason: Optional[str] = None) -> Dict[str, Any]:
        """Explicit action rejection."""
        act_id = action_id or (self._last_staged_action.action_id if self._last_staged_action else None)
        if not act_id:
            return {"success": False, "status": "ERROR", "message": "No active action found to reject."}
        return action_manager.reject_action(act_id, reason=reason)

    def cancel_action(self, action_id: Optional[str] = None) -> Dict[str, Any]:
        """Explicit action cancellation."""
        act_id = action_id or (self._last_staged_action.action_id if self._last_staged_action else None)
        if not act_id:
            return {"success": False, "status": "ERROR", "message": "No active action found to cancel."}
        return action_manager.cancel_action(act_id)


agent = TenantShieldAgent()
