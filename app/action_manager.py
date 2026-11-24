"""TenantShield Action Safety & Human Approval Manager — Phase 5

Enforces the non-negotiable principle:
AI can recommend and prepare actions; the human controls consequential execution.

Implements the complete action lifecycle:
PROPOSED -> [APPROVED / REJECTED / CANCELLED] -> EXECUTING -> [SUCCESS / FAILURE] -> (RETRY)

Protections:
- Concurrency / Double-Click Prevention (Atomic Lock per Action)
- Duplicate Execution Rejection (Idempotency)
- Stale Approval Expiration (TTL-based expiration)
- Invalid / Tampered Action Detection
- Safe Failure Capture & Transient Error Retry
- Sensitive Data Masking in Logs
"""

import time
import uuid
import logging
import threading
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.mcp_client import notice_mcp_client

# Configure safe logging (no secrets, masked PII)
logger = logging.getLogger("tenantshield.safety")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[SAFETY] %(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)


class ActionLifecycleState(str, Enum):
    PROPOSED = "PROPOSED"
    CONFIRMED = "CONFIRMED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    EXECUTING = "EXECUTING"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"


class ProposedActionDetails(BaseModel):
    action_id: str = Field(default_factory=lambda: f"act_{uuid.uuid4().hex[:12]}")
    created_at: float = Field(default_factory=time.time)
    expires_at: float = Field(default_factory=lambda: time.time() + 900.0)  # 15 minutes TTL
    action_type: str = Field(..., description="Action identifier: STAGE_LEGAL_DEMAND_LETTER")
    risk_level: str = Field(default="HIGH", description="Risk level: HIGH")
    target: str = Field(..., description="Entity affected by the action")
    
    # 5 Mandatory Transparency Disclosures
    what: str = Field(..., description="Exact description of what the AI proposes to do")
    why: str = Field(..., description="Factual and statutory justification for this action")
    data_involved: Dict[str, Any] = Field(default_factory=dict, description="Itemized data and parameters involved")
    consequences_if_approved: str = Field(..., description="What will happen once authorized")
    what_will_not_happen: str = Field(..., description="Explicit boundaries of what this action will NOT do")

    # State & Governance
    state: ActionLifecycleState = ActionLifecycleState.PROPOSED
    editable_fields: List[str] = Field(default_factory=lambda: [
        "tenant_name", "landlord_name", "rental_address", "move_out_date", "demand_deadline_days"
    ])
    rejection_reason: Optional[str] = None
    execution_result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    idempotency_key: str = Field(default_factory=lambda: uuid.uuid4().hex)


def mask_sensitive_text(text: str) -> str:
    """Masks potentially sensitive names/addresses for safe logging."""
    if not text:
        return text
    if len(text) <= 4:
        return "****"
    return text[:2] + "****" + text[-2:]


class ActionManager:
    """Thread-safe manager for all consequential action proposals and approvals."""

    def __init__(self, notice_client=notice_mcp_client):
        self.notice_client = notice_client
        self._proposals: Dict[str, ProposedActionDetails] = {}
        self._locks: Dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()

    def _get_action_lock(self, action_id: str) -> threading.Lock:
        with self._global_lock:
            if action_id not in self._locks:
                self._locks[action_id] = threading.Lock()
            return self._locks[action_id]

    def create_proposal(
        self,
        action_type: str,
        target: str,
        what: str,
        why: str,
        data_involved: Dict[str, Any],
        consequences_if_approved: str,
        what_will_not_happen: str,
        risk_level: str = "HIGH",
        ttl_seconds: float = 900.0,
    ) -> ProposedActionDetails:
        """Registers a new consequential action proposal awaiting human review."""
        proposal = ProposedActionDetails(
            action_type=action_type,
            risk_level=risk_level,
            target=target,
            what=what,
            why=why,
            data_involved=data_involved,
            consequences_if_approved=consequences_if_approved,
            what_will_not_happen=what_will_not_happen,
            expires_at=time.time() + ttl_seconds,
        )
        with self._global_lock:
            self._proposals[proposal.action_id] = proposal

        logger.info(
            f"Action proposed: {proposal.action_id} | Type: {action_type} | Target: {mask_sensitive_text(target)}"
        )
        return proposal

    def get_proposal(self, action_id: str) -> Optional[ProposedActionDetails]:
        return self._proposals.get(action_id)

    def approve_and_execute(
        self,
        action_id: str,
        user_overrides: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Approves and safely executes a proposed action with full protection against duplicate clicks."""
        proposal = self.get_proposal(action_id)
        if not proposal:
            logger.warning(f"Attempted execution of invalid/nonexistent action: {action_id}")
            return {
                "success": False,
                "status": "INVALID_ACTION",
                "message": f"Action ID '{action_id}' does not exist or has already been pruned.",
            }

        action_lock = self._get_action_lock(action_id)
        
        # Concurrency / Double-Click Lock
        if not action_lock.acquire(blocking=False):
            logger.warning(f"Blocked duplicate concurrent click on action {action_id}")
            return {
                "success": False,
                "status": "CONCURRENT_EXECUTION_BLOCKED",
                "message": "Action is currently being processed. Please wait for completion.",
            }

        try:
            # 1. State Check: Must be PROPOSED or FAILURE (if retrying)
            if proposal.state not in (ActionLifecycleState.PROPOSED, ActionLifecycleState.FAILURE):
                logger.warning(
                    f"Blocked execution of action {action_id} in invalid state: {proposal.state}"
                )
                return {
                    "success": False,
                    "status": "INVALID_STATE",
                    "current_state": proposal.state.value,
                    "message": (
                        f"Action cannot be executed because its current status is '{proposal.state.value}'. "
                        f"Duplicate or repeated execution prevented."
                    ),
                }

            # 2. Stale Approval / Expiration Check
            if time.time() > proposal.expires_at:
                proposal.state = ActionLifecycleState.CANCELLED
                proposal.error_message = "Proposal expired before human approval was granted."
                logger.warning(f"Blocked stale action approval for {action_id} (expired {time.time() - proposal.expires_at:.1f}s ago)")
                return {
                    "success": False,
                    "status": "EXPIRED",
                    "message": "This approval request has expired (15-minute safety TTL). Please run a fresh audit.",
                }

            # 3. Transition to EXECUTING
            proposal.state = ActionLifecycleState.EXECUTING
            logger.info(f"Action {action_id} authorized by user. Commencing MCP execution...")

            # 4. Prepare parameters with user overrides
            overrides = user_overrides or {}
            data = proposal.data_involved

            tool_args = {
                "tenant_name": overrides.get("tenant_name", data.get("tenant_name", "Tenant")),
                "landlord_name": overrides.get("landlord_name", data.get("landlord_name", "Landlord / Property Management")),
                "rental_address": overrides.get("rental_address", data.get("rental_address", "Rental Property Address")),
                "move_out_date": overrides.get("move_out_date", data.get("move_out_date", "Move-Out Date")),
                "dispute_amount": float(overrides.get("dispute_amount", data.get("dispute_amount", 0.0))),
                "statutory_penalties": float(overrides.get("statutory_penalties", data.get("statutory_penalties", 0.0))),
                "violations": data.get("violations", []),
                "statutory_citation": data.get("statutory_citation", "State Housing Law"),
                "demand_deadline_days": int(overrides.get("demand_deadline_days", data.get("demand_deadline_days", 10))),
            }

            # 5. Execute Action/Write MCP Tool
            try:
                mcp_res = self.notice_client.call_tool("stage_formal_demand_letter", tool_args)
            except Exception as e:
                proposal.state = ActionLifecycleState.FAILURE
                proposal.error_message = f"MCP Client connection failure: {str(e)}"
                logger.error(f"Execution failed on action {action_id}: {str(e)}")
                return {
                    "success": False,
                    "status": ActionLifecycleState.FAILURE.value,
                    "error": proposal.error_message,
                    "can_retry": True,
                    "message": "Failed to communicate with the Formal Notice MCP Server. You may retry this action.",
                }

            # 6. Check Tool Result
            if mcp_res.get("isError"):
                proposal.state = ActionLifecycleState.FAILURE
                proposal.error_message = mcp_res.get("error", "Tool returned an error")
                logger.error(f"Action tool error for {action_id}: {proposal.error_message}")
                return {
                    "success": False,
                    "status": ActionLifecycleState.FAILURE.value,
                    "error": proposal.error_message,
                    "can_retry": True,
                    "message": f"Action Tool Error: {proposal.error_message}",
                }

            # 7. Success State Transition
            doc_data = mcp_res.get("data", {})
            proposal.state = ActionLifecycleState.SUCCESS
            proposal.execution_result = doc_data
            proposal.error_message = None
            logger.info(f"Action {action_id} successfully executed. Document compiled.")

            return {
                "success": True,
                "status": ActionLifecycleState.SUCCESS.value,
                "approved": True,
                "action_id": action_id,
                "document": doc_data,
                "message": "Action authorized and completed. Formal legal notice compiled successfully.",
            }

        finally:
            action_lock.release()

    def reject_action(self, action_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
        """User rejects the proposed action. Safe state transition, zero side effects."""
        proposal = self.get_proposal(action_id)
        if not proposal:
            return {"success": False, "status": "INVALID_ACTION", "message": f"Action ID '{action_id}' not found."}

        action_lock = self._get_action_lock(action_id)
        with action_lock:
            if proposal.state not in (ActionLifecycleState.PROPOSED, ActionLifecycleState.FAILURE):
                return {
                    "success": False,
                    "status": "INVALID_STATE",
                    "message": f"Cannot reject action in state '{proposal.state.value}'.",
                }

            proposal.state = ActionLifecycleState.REJECTED
            proposal.rejection_reason = reason or "Declined by user."
            logger.info(f"Action {action_id} rejected by user. Reason: {proposal.rejection_reason}")

            return {
                "success": True,
                "status": ActionLifecycleState.REJECTED.value,
                "action_id": action_id,
                "message": "Action was successfully declined. No documents compiled or dispatched.",
            }

    def cancel_action(self, action_id: str) -> Dict[str, Any]:
        """User or system cancels the proposed action."""
        proposal = self.get_proposal(action_id)
        if not proposal:
            return {"success": False, "status": "INVALID_ACTION", "message": f"Action ID '{action_id}' not found."}

        action_lock = self._get_action_lock(action_id)
        with action_lock:
            proposal.state = ActionLifecycleState.CANCELLED
            logger.info(f"Action {action_id} cancelled.")
            return {
                "success": True,
                "status": ActionLifecycleState.CANCELLED.value,
                "action_id": action_id,
                "message": "Action proposal cancelled.",
            }

    def retry_action(self, action_id: str, user_overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Retries a failed action without requiring a full re-audit."""
        proposal = self.get_proposal(action_id)
        if not proposal:
            return {"success": False, "status": "INVALID_ACTION", "message": f"Action ID '{action_id}' not found."}

        if proposal.state != ActionLifecycleState.FAILURE:
            return {
                "success": False,
                "status": "INVALID_STATE",
                "message": f"Only failed actions can be retried. Current state: '{proposal.state.value}'.",
            }

        proposal.retry_count += 1
        logger.info(f"Retrying action {action_id} (Attempt #{proposal.retry_count})...")
        return self.approve_and_execute(action_id, user_overrides)


# Global singleton instance
action_manager = ActionManager()
