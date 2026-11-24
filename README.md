# TenantShield

> **The Autonomous Security Deposit & Lease Rights Defender**  
> *Make MCP Matter — Less Magic, More Utility*

TenantShield empowers everyday residential tenants to audit unlawful security deposit deductions against municipal civil codes, useful life standards, and statutory return deadlines via specialized **Model Context Protocol (MCP)** tools running over local `stdio` pipes with strict human-in-the-loop action governance.

---

## The 5-Step Visual MCP Architecture

```text
User Dispute Statement
       │
       ▼
[1. Goal Parse] ──► Extracts jurisdiction, tenancy tenure, elapsed days, line items
       │
       ▼
[2. Tool A (READ)] ──► get_statutory_deadlines on tenancy_law_mcp (stdio)
       │
       ▼
[3. Tool B (ANALYZE)] ──► evaluate_wear_and_tear on tenancy_law_mcp (stdio)
       │
       ▼
[4. Human Gate (SAFETY)] ──► Halts execution pending explicit human authorization (5 disclosures)
       │
       ├─► [DECLINE] ──► Action cancelled with zero side-effects
       │
       └─► [AUTHORIZE]
             │
             ▼
[5. Tool C (WRITE)] ──► stage_formal_demand_letter on formal_notice_mcp (stdio)
             │
             ▼
Courtroom-Ready Formal Legal Notice Compiled & Staged
```

---

## Hackathon Demo Presets (1-Click)

1. **📍 Los Angeles Preset ($1,050 Deduction):**
   - 3-year tenancy in Los Angeles; notice sent 26 days after move-out deducting $600 for wall painting and $450 for carpet cleaning.
   - Triggers automatic statutory forfeiture under **California Civil Code § 1950.5(g)(1)** (21-day limit breached).
   - Identifies 100% ordinary wear-and-tear for 3-year paint and carpet useful life.
   - Calculates **$1,050.00** recoverable principal + **$2,100.00** statutory bad-faith penalties (2.0x multiplier) = **$3,150.00 total claim**.
   - Halts at Human Approval Gate; compiles certified demand notice upon authorization.

2. **📍 New York City Preset ($900 Deduction):**
   - 2-year tenancy in NYC; notice sent 20 days after move-out deducting $500 for repainting and $400 for routine carpet cleaning.
   - Triggers statutory forfeiture under **N.Y. Gen. Oblig. Law § 7-108(1-a)(e)** (14-day limit breached).
   - Demonstrates safe rejection flow if user declines the action proposal.

---

## 5 Mandatory Transparency Disclosures

Before any consequential action executes, TenantShield presents:
1. **What the AI wants to do:** Compiles and stages a certified-mail ready formal demand letter.
2. **Why this action is recommended:** Cites specific statutory deadline breaches and useful life depreciation.
3. **What will happen if approved:** The document is compiled with tenant overrides and made available for copy/export.
4. **What will NOT happen:** TenantShield will **never** contact landlords without consent, file court claims, or charge bank accounts.
5. **Human Override Drawer:** Editable tenant name, landlord name, rental address, and demand deadline (days).

---

## Quickstart

```powershell
# 1. Navigate to project directory
cd "C:\Users\Chinmayee RS\Downloads\tenantshield"

# 2. Run the application
python run.py
```

Open in browser:
- **Interactive UI:** [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **API Status:** [http://127.0.0.1:8000/api/status](http://127.0.0.1:8000/api/status)
- **OpenAPI Docs:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## Verification Test Suites

```powershell
# Run the complete test battery (Phases 1 through 6)
python test_foundation.py
python test_phase2_mcp.py
python test_phase3_agent.py
python test_phase4_orchestration.py
python test_phase5_safety.py
python test_phase6_frontend.py
```
