/**
 * TenantShield Frontend Client Application
 * Phase 8 — Hackathon Visual Polish & Enhanced MCP Pipeline Visualizer
 *
 * Visualizes the 5-step MCP lifecycle:
 * 1. Goal Parse (Client -> Agent)
 * 2. Tool A (READ): get_statutory_deadlines via tenancy_law_mcp stdio
 * 3. Tool B (ANALYZE): evaluate_wear_and_tear via tenancy_law_mcp stdio
 * 4. Human Approval Gate: Halts execution pending explicit human authorization
 * 5. Tool C (WRITE): stage_formal_demand_letter via formal_notice_mcp stdio
 */

// Application State
let currentAuditResponse = null;
let currentActionId = null;
let currentActionType = "STAGE_LEGAL_DEMAND_LETTER";
let isAuditing = false;
let isAuthorizing = false;

// -----------------------------------------------------------------------------
// MCP Server & Backend Health Probe
// -----------------------------------------------------------------------------

async function checkBackendAndMCPStatus() {
    const mcpStatusDot = document.getElementById('mcp-status-dot');
    const mcpStatusText = document.getElementById('mcp-status-text');

    try {
        const response = await fetch('/api/status');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();

        if (data.mcp_active) {
            if (mcpStatusDot) mcpStatusDot.className = 'w-2.5 h-2.5 rounded-full bg-emerald-400';
            if (mcpStatusText) {
                mcpStatusText.textContent = `MCP Active (2 stdio servers, ${data.registered_mcp_tools ? data.registered_mcp_tools.length : 3} tools)`;
                mcpStatusText.className = 'text-emerald-400 font-medium';
            }
        } else {
            if (mcpStatusDot) mcpStatusDot.className = 'w-2.5 h-2.5 rounded-full bg-amber-400 animate-pulse';
            if (mcpStatusText) {
                mcpStatusText.textContent = 'MCP Servers Initializing...';
                mcpStatusText.className = 'text-amber-300 font-medium';
            }
        }
    } catch (error) {
        console.error('Failed to probe MCP / backend status:', error);
        if (mcpStatusDot) mcpStatusDot.className = 'w-2.5 h-2.5 rounded-full bg-rose-500';
        if (mcpStatusText) {
            mcpStatusText.textContent = 'Backend / MCP Disconnected';
            mcpStatusText.className = 'text-rose-400 font-medium';
        }
    }
}

// Global alias for foundation test suite compatibility
function checkBackendStatus() {
    return checkBackendAndMCPStatus();
}

// -----------------------------------------------------------------------------
// Enhanced Visual Stepper Controller
// -----------------------------------------------------------------------------

function updateStepperState(stepNumber, state, customDesc = null, customStatus = null) {
    const card = document.getElementById(`step-card-${stepNumber}`);
    if (!card) return;

    const dot = card.querySelector('.step-dot');
    const desc = card.querySelector('.step-desc');
    const status = card.querySelector('.step-status');

    if (customDesc && desc) {
        desc.textContent = customDesc;
    }

    // Reset base classes
    card.className = 'p-3.5 rounded-xl border transition-all text-xs flex flex-col justify-between';

    if (state === 'pending') {
        card.classList.add('border-slate-800', 'bg-slate-950/60');
        if (dot) dot.className = 'w-2 h-2 rounded-full bg-slate-600 step-dot';
        if (status) {
            status.textContent = customStatus || 'IDLE';
            status.className = 'text-slate-500 font-semibold step-status';
        }
    } else if (state === 'active') {
        card.classList.add('border-amber-500/60', 'bg-amber-950/20', 'step-glow-amber', 'ring-1', 'ring-amber-500/40');
        if (dot) dot.className = 'w-2 h-2 rounded-full bg-amber-400 animate-ping step-dot';
        if (status) {
            status.textContent = customStatus || 'PROCESSING';
            status.className = 'text-amber-300 font-bold step-status animate-pulse';
        }
    } else if (state === 'completed') {
        card.classList.add('border-emerald-500/50', 'bg-emerald-950/20', 'step-glow-emerald');
        if (dot) dot.className = 'w-2 h-2 rounded-full bg-emerald-400 step-dot';
        if (status) {
            status.textContent = customStatus || '✓ VERIFIED';
            status.className = 'text-emerald-400 font-semibold step-status';
        }
    } else if (state === 'gated') {
        card.classList.add('border-amber-400/90', 'bg-amber-950/40', 'ring-2', 'ring-amber-400/50', 'step-glow-amber');
        if (dot) dot.className = 'w-2.5 h-2.5 rounded-full bg-amber-400 animate-pulse step-dot';
        if (status) {
            status.textContent = customStatus || '🔒 HUMAN AUTHORIZATION REQUIRED';
            status.className = 'text-amber-300 font-bold step-status';
        }
    } else if (state === 'authorized') {
        card.classList.add('border-emerald-500/60', 'bg-emerald-950/30', 'step-glow-emerald');
        if (dot) dot.className = 'w-2 h-2 rounded-full bg-emerald-400 step-dot';
        if (status) {
            status.textContent = customStatus || '🔓 AUTHORIZED';
            status.className = 'text-emerald-300 font-bold step-status';
        }
    } else if (state === 'rejected') {
        card.classList.add('border-rose-800/80', 'bg-rose-950/20');
        if (dot) dot.className = 'w-2 h-2 rounded-full bg-rose-400 step-dot';
        if (status) {
            status.textContent = customStatus || 'DECLINED';
            status.className = 'text-rose-400 font-semibold step-status';
        }
    }
}

function resetStepper() {
    const badge = document.getElementById('pipeline-status-badge');
    if (badge) {
        badge.textContent = 'idle';
        badge.className = 'text-[11px] font-mono text-slate-500 lowercase';
    }

    for (let i = 1; i <= 5; i++) {
        updateStepperState(i, 'pending');
    }
}

function resetSafetyBanner() {
    const lockIcon = document.getElementById('safety-lock-icon');
    const lockTitle = document.getElementById('safety-lock-title');
    const lockSubtitle = document.getElementById('safety-lock-subtitle');
    const lockDesc = document.getElementById('safety-lock-desc');

    if (lockIcon) lockIcon.textContent = '🔒';
    if (lockTitle) lockTitle.textContent = 'ACTION LOCKED';
    if (lockSubtitle) lockSubtitle.textContent = 'Gated by ActionManager';
    if (lockDesc) lockDesc.textContent = 'AI recommendation ready. Human authorization required before the write tool can execute.';
}

// -----------------------------------------------------------------------------
// Presets Loader
// -----------------------------------------------------------------------------

function loadPreset(presetKey) {
    const disputeInput = document.getElementById('dispute-input');
    const jurisdictionSelect = document.getElementById('jurisdiction-select');
    const tenantName = document.getElementById('override-tenant-name');
    const landlordName = document.getElementById('override-landlord-name');
    const rentalAddress = document.getElementById('override-rental-address');
    const demandDays = document.getElementById('override-demand-days');

    if (presetKey === 'la') {
        if (disputeInput) {
            disputeInput.value = "I lived in an apartment in Los Angeles for 3 years. My landlord sent me a notice 26 days after move-out deducting $600 for wall painting and $450 for carpet cleaning. Help me get my deposit back.";
        }
        if (jurisdictionSelect) jurisdictionSelect.value = "California";
        if (tenantName) tenantName.value = "Jane Doe";
        if (landlordName) landlordName.value = "Sunset Real Estate LLC";
        if (rentalAddress) rentalAddress.value = "742 Evergreen Terrace, Los Angeles, CA";
        if (demandDays) demandDays.value = 10;
    } else if (presetKey === 'ny') {
        if (disputeInput) {
            disputeInput.value = "I rented an apartment in New York City for 2 years. 20 days after move-out, my landlord sent an itemized notice deducting $500 for wall repainting and $400 for standard carpet cleaning.";
        }
        if (jurisdictionSelect) jurisdictionSelect.value = "New York";
        if (tenantName) tenantName.value = "John Smith";
        if (landlordName) landlordName.value = "Manhattan Premier Properties Inc.";
        if (rentalAddress) rentalAddress.value = "123 Hudson Street, Apt 4B, New York, NY";
        if (demandDays) demandDays.value = 10;
    }

    // Hide old findings and error notices if present to reset stage
    const inputErrorMsg = document.getElementById('input-error-msg');
    if (inputErrorMsg) inputErrorMsg.classList.add('hidden');
    const findingsSection = document.getElementById('findings-section');
    if (findingsSection) findingsSection.classList.add('hidden');
    const resultDocSection = document.getElementById('result-document-section');
    if (resultDocSection) resultDocSection.classList.add('hidden');
    const rejectedBanner = document.getElementById('rejected-banner');
    if (rejectedBanner) rejectedBanner.classList.add('hidden');

    resetStepper();
    resetSafetyBanner();
}

// -----------------------------------------------------------------------------
// Audit Execution
// -----------------------------------------------------------------------------

async function runLegalAudit() {
    if (isAuditing) return;

    const disputeInput = document.getElementById('dispute-input');
    const jurisdictionSelect = document.getElementById('jurisdiction-select');
    const runBtn = document.getElementById('run-audit-btn');
    const btnText = document.getElementById('audit-btn-text');
    const spinner = document.getElementById('audit-spinner');
    const badge = document.getElementById('pipeline-status-badge');

    const userGoal = disputeInput ? disputeInput.value.trim() : "";
    const inputErrorMsg = document.getElementById('input-error-msg');
    if (inputErrorMsg) inputErrorMsg.classList.add('hidden');

    if (!userGoal) {
        if (inputErrorMsg) {
            inputErrorMsg.textContent = "Please describe your tenancy dispute statement or click one of the demo presets above.";
            inputErrorMsg.classList.remove('hidden');
        }
        if (disputeInput) {
            disputeInput.focus();
            disputeInput.classList.add('border-rose-500', 'ring-1', 'ring-rose-500');
            setTimeout(() => {
                disputeInput.classList.remove('border-rose-500', 'ring-1', 'ring-rose-500');
            }, 2500);
        }
        return;
    }

    const jurisdiction = jurisdictionSelect ? jurisdictionSelect.value : "California";

    // UI Loading state
    isAuditing = true;
    if (runBtn) runBtn.disabled = true;
    if (btnText) btnText.textContent = 'Auditing via MCP...';
    if (spinner) spinner.classList.remove('hidden');

    // Reset UI sections
    const findingsSection = document.getElementById('findings-section');
    const resultDocSection = document.getElementById('result-document-section');
    const rejectedBanner = document.getElementById('rejected-banner');
    if (resultDocSection) resultDocSection.classList.add('hidden');
    if (rejectedBanner) rejectedBanner.classList.add('hidden');
    resetSafetyBanner();

    // Stepper: step 1 active
    if (badge) {
        badge.textContent = 'analyzing goals & statute';
        badge.className = 'text-[11px] font-mono text-amber-400 lowercase animate-pulse';
    }
    updateStepperState(1, 'active', 'Extracting jurisdiction & deductions...', 'PROCESSING');
    updateStepperState(2, 'pending');
    updateStepperState(3, 'pending');
    updateStepperState(4, 'pending');
    updateStepperState(5, 'pending');

    try {
        // Visual stepper progression tracking real tool execution phases
        setTimeout(() => updateStepperState(2, 'active', 'get_statutory_deadlines on tenancy_law_mcp', 'PROCESSING'), 250);
        setTimeout(() => updateStepperState(3, 'active', 'evaluate_wear_and_tear useful life check', 'PROCESSING'), 500);

        const response = await fetch('/api/agent/audit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_goal: userGoal,
                context: { jurisdiction: jurisdiction }
            }),
        });

        if (!response.ok) {
            throw new Error(`Server returned HTTP ${response.status}`);
        }

        const data = await response.json();
        currentAuditResponse = data;

        // Render findings
        renderAuditResults(data);

    } catch (err) {
        console.error('Audit failed:', err);
        if (inputErrorMsg) {
            inputErrorMsg.textContent = `Legal Audit Issue: ${err.message}`;
            inputErrorMsg.classList.remove('hidden');
        }
        if (badge) {
            badge.textContent = 'error in pipeline';
            badge.className = 'text-[11px] font-mono text-rose-400 lowercase';
        }
    } finally {
        isAuditing = false;
        if (runBtn) runBtn.disabled = false;
        if (btnText) btnText.textContent = 'Run MCP Legal Audit';
        if (spinner) spinner.classList.add('hidden');
    }
}

// -----------------------------------------------------------------------------
// Render Audit Results & Populate Gating Card
// -----------------------------------------------------------------------------

function renderAuditResults(data) {
    const findingsSection = document.getElementById('findings-section');
    const badge = document.getElementById('pipeline-status-badge');
    const kpiPrincipal = document.getElementById('kpi-principal');
    const kpiPrincipalSub = document.getElementById('kpi-principal-sub');
    const kpiPenalties = document.getElementById('kpi-penalties');
    const kpiPenaltiesSub = document.getElementById('kpi-penalties-sub');
    const kpiTotal = document.getElementById('kpi-total');
    const kpiTotalSub = document.getElementById('kpi-total-sub');
    const deadlineAlert = document.getElementById('deadline-violation-alert');
    const deadlineText = document.getElementById('deadline-violation-text');
    const auditTableBody = document.getElementById('audit-table-body');
    const summariesList = document.getElementById('decision-summaries-list');
    const approvalCard = document.getElementById('approval-card');

    const findings = data.findings || {};
    const itemized = data.itemized_audits || [];
    const summaries = data.decision_summaries || [];
    const proposed = data.proposed_action;

    // 1. Update Stepper Statuses
    updateStepperState(1, 'completed', 'Goals & jurisdiction identified', '✓ PARSED');
    updateStepperState(2, 'completed', `${findings.statutory_citation || 'Statute'} deadline checked`, '✓ VERIFIED');
    updateStepperState(3, 'completed', `${itemized.length} deduction(s) evaluated against useful life`, '✓ VERIFIED');

    if (proposed && proposed.requires_approval) {
        updateStepperState(4, 'gated', 'Halted: Human Authorization Required', '🔒 HUMAN AUTHORIZATION REQUIRED');
        updateStepperState(5, 'pending', 'stage_formal_demand_letter (Awaiting Approval)', 'IDLE');
        if (badge) {
            badge.textContent = 'awaiting human authorization';
            badge.className = 'text-[11px] font-mono text-amber-400 lowercase font-semibold';
        }
        resetSafetyBanner();
    } else {
        updateStepperState(4, 'completed', 'No Consequential Actions Proposed', '✓ COMPLETE');
        updateStepperState(5, 'completed', 'Complete', '✓ COMPLETE');
        if (badge) {
            badge.textContent = 'audit completed';
            badge.className = 'text-[11px] font-mono text-emerald-400 lowercase';
        }
    }

    // 2. Populate KPI Cards
    const principal = Number(findings.recoverable_principal || findings.dispute_amount || 0);
    const penalties = Number(findings.statutory_penalties_eligible || 0);
    const totalClaim = Number(findings.total_claim || (principal + penalties));

    if (kpiPrincipal) kpiPrincipal.textContent = `$${principal.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    if (kpiPrincipalSub) {
        kpiPrincipalSub.textContent = findings.deadline_violated
            ? "100% Forfeited by Landlord"
            : "Ordinary Wear & Tear Recovery";
    }

    if (kpiPenalties) kpiPenalties.textContent = `$${penalties.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    if (kpiPenaltiesSub) {
        const multiplier = principal > 0 ? (penalties / principal).toFixed(1) : "0.0";
        kpiPenaltiesSub.textContent = `${multiplier}x Bad-Faith Multiplier (${findings.jurisdiction || 'State'})`;
    }

    if (kpiTotal) kpiTotal.textContent = `$${totalClaim.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    if (kpiTotalSub) kpiTotalSub.textContent = "Eligible for Certified Demand & Small Claims";

    // 3. Statutory Forfeiture Violation Alert
    if (deadlineAlert && deadlineText) {
        if (findings.deadline_violated) {
            deadlineAlert.classList.remove('hidden');
            deadlineText.textContent = `Notice delivered on Day ${findings.days_elapsed || '26'} exceeds the mandatory ${findings.statutory_deadline_days || '21'}-day deadline under ${findings.statutory_citation || 'state law'}. Under statute, the landlord has forfeited all rights to retain any portion of the deposit.`;
        } else {
            deadlineAlert.classList.add('hidden');
        }
    }

    // 4. Populate Itemized Deduction Audit Table
    if (auditTableBody) {
        auditTableBody.innerHTML = '';
        if (itemized.length === 0) {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td colspan="5" class="py-3 text-slate-400 italic">No specific wear-and-tear line items detected. Audit evaluated against statutory timeline forfeiture.</td>`;
            auditTableBody.appendChild(tr);
        } else {
            itemized.forEach(row => {
                const tr = document.createElement('tr');
                tr.className = 'hover:bg-slate-800/40 transition-colors';
                const billed = Number(row.billed_amount || 0);
                const lawful = Number(row.lawful_charge || 0);
                const unlawful = Number(row.unlawful_charge || 0);
                const isViolation = unlawful > 0;

                tr.innerHTML = `
                    <td class="py-3 font-medium text-slate-200">${escapeHtml(row.item_category || 'Deduction')}</td>
                    <td class="py-3 text-slate-300">$${billed.toFixed(2)}</td>
                    <td class="py-3 text-slate-400">$${lawful.toFixed(2)}</td>
                    <td class="py-3 ${isViolation ? 'text-rose-400 font-bold' : 'text-slate-400'}">$${unlawful.toFixed(2)}</td>
                    <td class="py-3">
                        <span class="px-2 py-0.5 rounded-full text-[10px] font-sans font-semibold ${isViolation ? 'bg-amber-500/10 text-amber-300 border border-amber-500/30' : 'bg-slate-800 text-slate-400 border border-slate-700'}">
                            ${escapeHtml(row.classification || 'Ordinary Wear & Tear')}
                        </span>
                    </td>
                `;
                auditTableBody.appendChild(tr);
            });
        }
    }

    // 5. Populate Decision Summaries
    if (summariesList) {
        summariesList.innerHTML = '';
        summaries.forEach(s => {
            const li = document.createElement('li');
            li.textContent = s;
            summariesList.appendChild(li);
        });
    }

    // 6. Populate 5 Transparency Disclosures in Approval Card
    if (proposed && proposed.requires_approval) {
        currentActionId = proposed.action_id;
        currentActionType = proposed.action_type || "STAGE_LEGAL_DEMAND_LETTER";

        const discWhat = document.getElementById('disclosure-what');
        const discWhy = document.getElementById('disclosure-why');
        const discConsequences = document.getElementById('disclosure-consequences');
        const discNotHappen = document.getElementById('disclosure-not-happen');

        if (discWhat) discWhat.textContent = proposed.what || `Compile and stage a formal legal demand notice demanding the full return of $${principal.toFixed(2)}.`;
        if (discWhy) discWhy.textContent = proposed.why || `Statutory deadlines and wear-and-tear standards were breached under ${findings.statutory_citation}.`;
        if (discConsequences) discConsequences.textContent = proposed.consequences_if_approved || "A certified-mail ready formal demand letter will be compiled and made available in the application.";
        if (discNotHappen) discNotHappen.textContent = proposed.what_will_not_happen || "TenantShield will NOT automatically email or send mail to your landlord without your explicit consent. It will NOT file court petitions automatically.";

        if (approvalCard) approvalCard.classList.remove('hidden');
    } else {
        if (approvalCard) approvalCard.classList.add('hidden');
    }

    // Unhide main findings section
    if (findingsSection) {
        findingsSection.classList.remove('hidden');
        findingsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}

// -----------------------------------------------------------------------------
// AI Decision Trace Drawer Logic
// -----------------------------------------------------------------------------

function populateDecisionTrace(data) {
    const traceContent = document.getElementById('trace-content');
    if (!traceContent) return;

    if (!data) {
        traceContent.innerHTML = `
            <div class="p-6 rounded-2xl bg-slate-950/80 border border-slate-800 text-slate-400 italic text-center space-y-2">
                <span class="text-xl block">📋</span>
                <p>No active audit trace yet.</p>
                <p class="text-[11px] text-slate-500 font-sans">Click one of the demo presets above and run an audit to generate a live trace.</p>
            </div>
        `;
        return;
    }

    const findings = data.findings || {};
    const itemized = data.itemized_audits || [];
    const proposed = data.proposed_action;
    const principal = Number(findings.recoverable_principal || findings.dispute_amount || 0);
    const penalties = Number(findings.statutory_penalties_eligible || 0);
    const totalClaim = Number(findings.total_claim || (principal + penalties));

    traceContent.innerHTML = `
        <div class="relative pl-6 space-y-4">
            <div class="trace-timeline-line"></div>

            <!-- 1. USER REQUEST -->
            <div class="relative">
                <span class="absolute -left-6 top-1.5 w-3 h-3 rounded-full bg-emerald-400 ring-4 ring-slate-900"></span>
                <div class="p-3.5 rounded-xl bg-slate-950/80 border border-slate-800">
                    <div class="flex items-center justify-between text-[11px] mb-1">
                        <span class="font-bold text-slate-200">USER REQUEST</span>
                        <span class="text-slate-500 font-mono text-[10px]">INPUT PARSE</span>
                    </div>
                    <p class="text-[11px] text-slate-300 font-sans italic line-clamp-2">"${escapeHtml(data.user_goal || 'Tenancy dispute statement')}"</p>
                    <div class="mt-2.5 pt-2 border-t border-slate-800 flex items-center justify-between text-[10px]">
                        <span class="text-slate-400">Jurisdiction detected:</span>
                        <span class="font-bold text-emerald-400 font-mono">${escapeHtml(findings.jurisdiction || 'State of California')}</span>
                    </div>
                </div>
            </div>

            <!-- 2. AUDIT REQUIRED -->
            <div class="relative">
                <span class="absolute -left-6 top-1.5 w-3 h-3 rounded-full bg-teal-400 ring-4 ring-slate-900"></span>
                <div class="p-3.5 rounded-xl bg-slate-950/80 border border-slate-800">
                    <div class="flex items-center justify-between text-[11px] mb-1">
                        <span class="font-bold text-slate-200">AUDIT REQUIRED</span>
                        <span class="text-teal-400/80 font-mono text-[10px]">RULE ENGINE</span>
                    </div>
                    <p class="text-[11px] text-slate-300">Security-deposit return statutory deadlines & ordinary wear-and-tear verification.</p>
                </div>
            </div>

            <!-- 3. MCP TOOL A — READ -->
            <div class="relative">
                <span class="absolute -left-6 top-1.5 w-3 h-3 rounded-full bg-emerald-400 ring-4 ring-slate-900"></span>
                <div class="p-3.5 rounded-xl bg-slate-950/80 border border-emerald-900/40">
                    <div class="flex items-center justify-between text-[11px] mb-1">
                        <span class="font-bold text-emerald-400">MCP TOOL A — READ</span>
                        <span class="text-[10px] px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800/40 font-mono">tenancy_law_mcp</span>
                    </div>
                    <p class="text-[11px] font-mono text-slate-200 font-semibold">get_statutory_deadlines</p>
                    <p class="text-[10px] text-emerald-300/90 mt-1">✓ Statutory deadline retrieved: ${findings.statutory_deadline_days || 21} days under ${escapeHtml(findings.statutory_citation || 'Statute')}</p>
                    ${findings.deadline_violated ? `<p class="text-[10px] text-rose-400 mt-1 font-semibold">⚠️ Notice delivered on Day ${findings.days_elapsed} exceeds mandatory limit</p>` : ''}
                </div>
            </div>

            <!-- 4. MCP TOOL B — ANALYZE -->
            <div class="relative">
                <span class="absolute -left-6 top-1.5 w-3 h-3 rounded-full bg-teal-400 ring-4 ring-slate-900"></span>
                <div class="p-3.5 rounded-xl bg-slate-950/80 border border-teal-900/40">
                    <div class="flex items-center justify-between text-[11px] mb-1">
                        <span class="font-bold text-teal-400">MCP TOOL B — ANALYZE</span>
                        <span class="text-[10px] px-1.5 py-0.5 rounded bg-teal-950 text-teal-400 border border-teal-800/40 font-mono">tenancy_law_mcp</span>
                    </div>
                    <p class="text-[11px] font-mono text-slate-200 font-semibold">evaluate_wear_and_tear</p>
                    <p class="text-[10px] text-teal-300/90 mt-1">✓ Deductions analyzed: ${itemized.length} line item(s) audited against useful-life standards</p>
                </div>
            </div>

            <!-- 5. SYNTHESIS -->
            <div class="relative">
                <span class="absolute -left-6 top-1.5 w-3 h-3 rounded-full bg-amber-400 ring-4 ring-slate-900"></span>
                <div class="p-3.5 rounded-xl bg-slate-950/80 border border-amber-900/40 space-y-1.5">
                    <div class="flex items-center justify-between text-[11px]">
                        <span class="font-bold text-amber-300">SYNTHESIS</span>
                        <span class="text-amber-400/80 font-mono text-[10px]">FINANCIALS</span>
                    </div>
                    <div class="grid grid-cols-2 gap-2 pt-1 text-[11px]">
                        <div>
                            <span class="text-slate-500 block text-[10px]">Unlawfully Withheld:</span>
                            <span class="font-bold text-emerald-400 font-mono text-xs">$${principal.toFixed(2)}</span>
                        </div>
                        <div>
                            <span class="text-slate-500 block text-[10px]">Statutory Damages:</span>
                            <span class="font-bold text-teal-400 font-mono text-xs">$${penalties.toFixed(2)}</span>
                        </div>
                    </div>
                    <div class="pt-2 border-t border-slate-800/80 flex items-center justify-between text-[11px]">
                        <span class="text-slate-300 font-medium">Total Monetary Claim:</span>
                        <span class="font-bold text-white font-mono text-xs">$${totalClaim.toFixed(2)}</span>
                    </div>
                </div>
            </div>

            <!-- 6. CONSEQUENTIAL ACTION -->
            <div class="relative">
                <span class="absolute -left-6 top-1.5 w-3 h-3 rounded-full bg-amber-400 ring-4 ring-slate-900"></span>
                <div class="p-3.5 rounded-xl bg-slate-950/80 border border-slate-800">
                    <div class="flex items-center justify-between text-[11px] mb-1">
                        <span class="font-bold text-slate-200">CONSEQUENTIAL ACTION</span>
                        <span class="text-amber-400 font-mono text-[10px]">PROPOSED</span>
                    </div>
                    <p class="text-[11px] text-slate-300">Formal demand notice proposed via <span class="font-mono text-emerald-400">stage_formal_demand_letter</span> on <span class="font-mono text-slate-400">formal_notice_mcp</span>.</p>
                </div>
            </div>

            <!-- 7. HUMAN CONTROL -->
            <div class="relative">
                <span class="absolute -left-6 top-1.5 w-3 h-3 rounded-full bg-amber-400 ring-4 ring-slate-900"></span>
                <div class="p-3.5 rounded-xl bg-amber-950/30 border border-amber-500/40">
                    <div class="flex items-center justify-between text-[11px] mb-1">
                        <span class="font-bold text-amber-300">HUMAN CONTROL</span>
                        <span class="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 font-mono">GATE</span>
                    </div>
                    <p class="text-[11px] text-amber-200/90 font-medium">🔒 Human authorization strictly required before write tool execution.</p>
                </div>
            </div>
        </div>
    `;
}

function openTraceDrawer() {
    const container = document.getElementById('trace-drawer-container');
    if (!container) return;
    populateDecisionTrace(currentAuditResponse);
    container.classList.remove('hidden');
    requestAnimationFrame(() => {
        container.classList.add('open');
    });
}

function closeTraceDrawer() {
    const container = document.getElementById('trace-drawer-container');
    if (!container) return;
    container.classList.remove('open');
    setTimeout(() => {
        container.classList.add('hidden');
    }, 280);
}

// -----------------------------------------------------------------------------
// Human-in-the-Loop Action Approval Execution
// -----------------------------------------------------------------------------

async function approveAction() {
    if (isAuthorizing) return;

    if (!currentActionId && currentAuditResponse && currentAuditResponse.proposed_action) {
        currentActionId = currentAuditResponse.proposed_action.action_id;
    }

    const approveBtn = document.getElementById('approve-action-btn');
    const badge = document.getElementById('pipeline-status-badge');
    const approvalCard = document.getElementById('approval-card');
    const resultDocSection = document.getElementById('result-document-section');
    const formalLetterPre = document.getElementById('formal-letter-pre');
    const actionErrorMsg = document.getElementById('action-error-msg');
    if (actionErrorMsg) actionErrorMsg.classList.add('hidden');

    // Visual elements of the Safety Banner
    const lockIcon = document.getElementById('safety-lock-icon');
    const lockTitle = document.getElementById('safety-lock-title');
    const lockSubtitle = document.getElementById('safety-lock-subtitle');
    const lockDesc = document.getElementById('safety-lock-desc');

    // Collect user overrides from input fields
    const tenantName = (document.getElementById('override-tenant-name')?.value || 'Jane Doe').trim();
    const landlordName = (document.getElementById('override-landlord-name')?.value || 'Sunset Real Estate LLC').trim();
    const rentalAddress = (document.getElementById('override-rental-address')?.value || '742 Evergreen Terrace, Los Angeles, CA').trim();
    const demandDays = parseInt(document.getElementById('override-demand-days')?.value, 10) || 10;

    isAuthorizing = true;
    if (approveBtn) {
        approveBtn.disabled = true;
        approveBtn.innerHTML = `
            <svg class="animate-spin h-4 w-4 text-slate-950" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
            </svg>
            <span>Authorizing MCP Tool...</span>
        `;
    }

    // Step transition: 🔒 LOCKED -> 🔓 AUTHORIZED
    if (lockIcon) lockIcon.textContent = '🔓';
    if (lockTitle) lockTitle.textContent = 'USER AUTHORIZED';
    if (lockSubtitle) lockSubtitle.textContent = 'MCP Write Tool Unlocked';
    if (lockDesc) lockDesc.textContent = 'Executing write tool: stage_formal_demand_letter on formal_notice_mcp over stdio...';

    updateStepperState(4, 'authorized', 'Authorized by human user', '🔓 AUTHORIZED');
    updateStepperState(5, 'active', 'Calling stage_formal_demand_letter...', 'PROCESSING');

    if (badge) {
        badge.textContent = 'executing formal_notice_mcp write tool';
        badge.className = 'text-[11px] font-mono text-emerald-400 lowercase animate-pulse';
    }

    try {
        const response = await fetch('/api/agent/approve-action', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action_id: currentActionId,
                action_type: currentActionType,
                approved: true,
                user_overrides: {
                    tenant_name: tenantName,
                    landlord_name: landlordName,
                    rental_address: rentalAddress,
                    demand_deadline_days: demandDays,
                }
            }),
        });

        const result = await response.json();

        if (result.success || result.status === 'AUTHORIZED_AND_COMPILED' || result.status === 'SUCCESS') {
            updateStepperState(5, 'completed', 'Formal demand notice compiled', '✓ ACTION COMPLETE');
            if (badge) {
                badge.textContent = 'action complete (notice compiled)';
                badge.className = 'text-[11px] font-mono text-emerald-400 lowercase font-bold';
            }

            // Update safety banner to completed state
            if (lockIcon) lockIcon.textContent = '✓';
            if (lockTitle) lockTitle.textContent = 'ACTION COMPLETE';
            if (lockSubtitle) lockSubtitle.textContent = 'Notice Staged';
            if (lockDesc) lockDesc.textContent = 'Courtroom-ready formal notice compiled successfully via formal_notice_mcp.';

            // Extract letter text
            const doc = result.document || {};
            const letterText = doc.full_letter_text || (doc.result && doc.result.full_letter_text) || doc.raw_text || JSON.stringify(doc, null, 2);

            if (formalLetterPre) {
                formalLetterPre.textContent = letterText;
            }

            if (approvalCard) approvalCard.classList.add('hidden');
            if (resultDocSection) {
                resultDocSection.classList.remove('hidden');
                resultDocSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
        } else {
            throw new Error(result.error || result.message || 'Execution failed on notice server.');
        }

    } catch (err) {
        console.error('Action execution failed:', err);
        if (actionErrorMsg) {
            actionErrorMsg.textContent = `Action Execution Issue: ${err.message}`;
            actionErrorMsg.classList.remove('hidden');
        }
        updateStepperState(5, 'rejected', `Error: ${err.message}`);
        if (badge) {
            badge.textContent = 'tool execution failure';
            badge.className = 'text-[11px] font-mono text-rose-400 lowercase';
        }
    } finally {
        isAuthorizing = false;
        if (approveBtn) {
            approveBtn.disabled = false;
            approveBtn.innerHTML = '<span>Authorize & Execute Action</span>';
        }
    }
}

// -----------------------------------------------------------------------------
// Human-in-the-Loop Action Rejection
// -----------------------------------------------------------------------------

async function rejectAction() {
    if (!currentActionId && currentAuditResponse && currentAuditResponse.proposed_action) {
        currentActionId = currentAuditResponse.proposed_action.action_id;
    }

    const badge = document.getElementById('pipeline-status-badge');
    const approvalCard = document.getElementById('approval-card');
    const rejectedBanner = document.getElementById('rejected-banner');

    const lockIcon = document.getElementById('safety-lock-icon');
    const lockTitle = document.getElementById('safety-lock-title');
    const lockSubtitle = document.getElementById('safety-lock-subtitle');
    const lockDesc = document.getElementById('safety-lock-desc');

    try {
        await fetch('/api/agent/reject-action', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action_id: currentActionId,
                action_type: currentActionType,
                approved: false,
                reason: "Declined by user."
            }),
        });

        if (lockIcon) lockIcon.textContent = '✕';
        if (lockTitle) lockTitle.textContent = 'ACTION DECLINED';
        if (lockSubtitle) lockSubtitle.textContent = 'Zero Side-Effects';
        if (lockDesc) lockDesc.textContent = 'Action declined by user. No documents compiled or dispatched.';

        updateStepperState(4, 'rejected', 'Declined by human user', 'DECLINED');
        updateStepperState(5, 'pending', 'Execution halted (Zero side-effects)', 'HALTED');

        if (badge) {
            badge.textContent = 'action declined by user';
            badge.className = 'text-[11px] font-mono text-slate-400 lowercase';
        }

        if (approvalCard) approvalCard.classList.add('hidden');
        if (rejectedBanner) {
            rejectedBanner.classList.remove('hidden');
            rejectedBanner.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }

    } catch (err) {
        console.error('Rejection failed:', err);
    }
}

// -----------------------------------------------------------------------------
// Clipboard Copy & Download Helpers
// -----------------------------------------------------------------------------

function copyFormalNotice() {
    const pre = document.getElementById('formal-letter-pre');
    const copyBtnText = document.getElementById('copy-btn-text');

    if (!pre) return;
    const textToCopy = pre.textContent;

    navigator.clipboard.writeText(textToCopy).then(() => {
        if (copyBtnText) copyBtnText.textContent = '✓ Copied!';
        setTimeout(() => {
            if (copyBtnText) copyBtnText.textContent = 'Copy Notice';
        }, 2500);
    }).catch(err => {
        console.error('Clipboard copy failed:', err);
    });
}

function downloadFormalNotice() {
    const pre = document.getElementById('formal-letter-pre');
    if (!pre) return;
    const textToDownload = pre.textContent;
    const blob = new Blob([textToDownload], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `TenantShield_Demand_Letter_${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// -----------------------------------------------------------------------------
// DOM Initialization & Event Bindings
// -----------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
    // 1. Initial health probe
    checkBackendAndMCPStatus();

    // 2. Preset Buttons
    const presetLa = document.getElementById('preset-la-btn');
    if (presetLa) presetLa.addEventListener('click', () => loadPreset('la'));

    const presetNy = document.getElementById('preset-ny-btn');
    if (presetNy) presetNy.addEventListener('click', () => loadPreset('ny'));

    // 3. Audit Button
    const runAuditBtn = document.getElementById('run-audit-btn');
    if (runAuditBtn) runAuditBtn.addEventListener('click', runLegalAudit);

    // 4. Action Approval & Rejection Buttons
    const approveBtn = document.getElementById('approve-action-btn');
    if (approveBtn) approveBtn.addEventListener('click', approveAction);

    const rejectBtn = document.getElementById('reject-action-btn');
    if (rejectBtn) rejectBtn.addEventListener('click', rejectAction);

    // 5. Copy & Download Document Buttons
    const copyBtn = document.getElementById('copy-doc-btn');
    if (copyBtn) copyBtn.addEventListener('click', copyFormalNotice);

    const downloadBtn = document.getElementById('download-doc-btn');
    if (downloadBtn) downloadBtn.addEventListener('click', downloadFormalNotice);

    // 6. AI Decision Trace Drawer Triggers
    const openTraceBtn = document.getElementById('open-trace-btn');
    if (openTraceBtn) openTraceBtn.addEventListener('click', openTraceDrawer);

    const closeTraceBtn = document.getElementById('close-trace-btn');
    if (closeTraceBtn) closeTraceBtn.addEventListener('click', closeTraceDrawer);

    const drawerContainer = document.getElementById('trace-drawer-container');
    if (drawerContainer) {
        drawerContainer.addEventListener('click', (e) => {
            if (e.target === drawerContainer) {
                closeTraceDrawer();
            }
        });
    }

    // Keyboard ESC shortcut to close drawer
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeTraceDrawer();
        }
    });
});
