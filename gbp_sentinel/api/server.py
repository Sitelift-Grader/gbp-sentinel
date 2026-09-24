"""FastAPI REST API and Web Dashboard for GBP SMOKER / Sentinel."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .. import config, db_v2
from ..case_management import CaseManager
from ..evidence_engine import EvidenceEngine
from ..network_engine import NetworkEngine
from ..policy_kb import GbpPolicyKB

app = FastAPI(
    title="GBP SMOKER — Google Maps Spam & Network Investigation Engine",
    description="Investigation, entity resolution, and monitoring engine for Google Business Profiles",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = str(config.DATA_DIR / "sentinel_v2.db")


# Pydantic Schemas
class ReviewRequest(BaseModel):
    finding_id: int
    reviewer: str = "Compliance Officer"
    action: str  # 'APPROVE' or 'REJECT'
    dismissal_reason: str = ""
    context_notes: str = ""
    case_id: Optional[int] = None


class CaseCreateRequest(BaseModel):
    title: str
    network_id: Optional[int] = None
    business_ids: Optional[List[int]] = None
    priority: str = "MEDIUM"
    reviewer_name: str = "Compliance Officer"
    notes: str = ""


# API Endpoints
@app.get("/api/stats")
def get_stats():
    total_businesses = db_v2.count_rows("businesses", db_path=DB_PATH)
    potential_issues = db_v2.count_rows("businesses", where="suspicion_score >= 30", db_path=DB_PATH)
    networks_count = db_v2.count_rows("networks", db_path=DB_PATH)
    high_priority_cases = db_v2.count_rows("cases", where="priority = 'HIGH' OR priority = 'CRITICAL'", db_path=DB_PATH)
    evidence_count = db_v2.count_rows("evidence", db_path=DB_PATH)
    cases_submitted = db_v2.count_rows("submissions", where="status = 'submitted'", db_path=DB_PATH)
    cases_pending = db_v2.count_rows("cases", where="status IN ('DISCOVERED', 'NEEDS_REVIEW')", db_path=DB_PATH)
    observed_actions = db_v2.count_rows("outcomes", where="outcome_type IN ('PROFILE_REMOVED', 'PROFILE_SUSPENDED', 'DUPLICATE_REMOVED')", db_path=DB_PATH)
    recurrent_signals = db_v2.count_rows("monitoring_events", where="event_type = 'REINCARNATION_SIGNAL'", db_path=DB_PATH)

    return {
        "total_businesses_scanned": total_businesses,
        "potential_policy_issues": potential_issues,
        "networks_detected": networks_count,
        "high_priority_cases": high_priority_cases,
        "evidence_items": evidence_count,
        "cases_submitted": cases_submitted,
        "cases_pending": cases_pending,
        "cases_with_observed_action": observed_actions,
        "recurrence_signals": recurrent_signals,
    }


@app.get("/api/businesses")
def list_businesses(
    search: Optional[str] = None,
    city: Optional[str] = None,
    min_score: int = Query(0, ge=0, le=100),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    where_parts = ["suspicion_score >= ?"]
    params = [min_score]

    if search:
        where_parts.append("(name LIKE ? OR address LIKE ? OR domain LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

    if city:
        where_parts.append("city LIKE ?")
        params.append(f"%{city}%")

    where_sql = " AND ".join(where_parts)
    rows = db_v2.list_rows(
        "businesses",
        where=where_sql,
        params=tuple(params),
        order_by="suspicion_score DESC, id ASC",
        limit=limit,
        offset=offset,
        db_path=DB_PATH,
    )
    total = db_v2.count_rows("businesses", where=where_sql, params=tuple(params), db_path=DB_PATH)
    return {"total": total, "items": rows, "limit": limit, "offset": offset}


@app.get("/api/businesses/{business_id}")
def get_business(business_id: int):
    biz = db_v2.get("businesses", business_id, db_path=DB_PATH)
    if not biz:
        raise HTTPException(status_code=404, detail="Business not found")

    snapshots = db_v2.list_rows("business_snapshots", where="business_id = ?", params=(business_id,), order_by="snapshot_timestamp DESC", db_path=DB_PATH)
    evidence = db_v2.list_rows("evidence", where="business_id = ?", params=(business_id,), order_by="id DESC", db_path=DB_PATH)
    findings = db_v2.list_rows("policy_findings", where="business_id = ?", params=(business_id,), order_by="id DESC", db_path=DB_PATH)
    relationships = db_v2.list_rows("relationships", where="source_business_id = ? OR target_business_id = ?", params=(business_id, business_id), db_path=DB_PATH)

    return {
        "business": biz,
        "snapshots": snapshots,
        "evidence": evidence,
        "findings": findings,
        "relationships": relationships,
    }


@app.get("/api/networks")
def list_networks():
    rows = db_v2.list_rows("networks", order_by="suspicion_score DESC, member_count DESC", db_path=DB_PATH)
    for r in rows:
        if r.get("score_breakdown_json"):
            try:
                r["score_breakdown"] = json.loads(r["score_breakdown_json"])
            except Exception:
                r["score_breakdown"] = {}
    return {"items": rows, "total": len(rows)}


@app.get("/api/networks/{network_id}")
def get_network(network_id: int):
    net = db_v2.get("networks", network_id, db_path=DB_PATH)
    if not net:
        raise HTTPException(status_code=404, detail="Network not found")

    if net.get("score_breakdown_json"):
        try:
            net["score_breakdown"] = json.loads(net["score_breakdown_json"])
        except Exception:
            net["score_breakdown"] = {}

    engine = NetworkEngine(DB_PATH)
    cy_elements = engine.to_cytoscape_elements(network_id)

    members = db_v2.list_rows("network_members", where="network_id = ?", params=(network_id,), db_path=DB_PATH)
    member_ids = [m["business_id"] for m in members]

    businesses = []
    if member_ids:
        placeholders = ", ".join("?" for _ in member_ids)
        businesses = db_v2.list_rows("businesses", where=f"id IN ({placeholders})", params=tuple(member_ids), db_path=DB_PATH)

    return {
        "network": net,
        "businesses": businesses,
        "graph": cy_elements,
    }


@app.get("/api/evidence")
def list_evidence(limit: int = 50, offset: int = 0):
    rows = db_v2.list_rows("evidence", order_by="id DESC", limit=limit, offset=offset, db_path=DB_PATH)
    total = db_v2.count_rows("evidence", db_path=DB_PATH)
    return {"total": total, "items": rows}


@app.get("/api/cases")
def list_cases():
    rows = db_v2.list_rows("cases", order_by="created_at DESC", db_path=DB_PATH)
    return {"total": len(rows), "items": rows}


@app.get("/api/cases/{case_id}")
def get_case(case_id: int):
    cm = CaseManager(DB_PATH)
    summary = cm.get_case_summary(case_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Case not found")
    return summary


@app.post("/api/review")
def review_finding(req: ReviewRequest):
    cm = CaseManager(DB_PATH)
    res = cm.review_finding(
        finding_id=req.finding_id,
        reviewer=req.reviewer,
        action=req.action,
        dismissal_reason=req.dismissal_reason,
        context_notes=req.context_notes,
        case_id=req.case_id,
    )
    return res


@app.get("/api/policies")
def list_policies():
    conn = db_v2.get_connection(DB_PATH)
    kb = GbpPolicyKB(conn)
    policies = kb.list_policies()
    conn.close()
    return {"total": len(policies), "items": [p.__dict__ for p in policies]}


# Interactive Web Dashboard
@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
def serve_dashboard():
    return HTMLResponse(content=_DASHBOARD_HTML)


_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>GBP SMOKER — Google Maps Spam & Network Investigation Engine</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.30.2/cytoscape.min.js"></script>
  <style>
    body { background-color: #0B0F19; color: #E2E8F0; font-family: system-ui, -apple-system, sans-serif; }
    .card { background-color: #111827; border: 1px solid #1F2937; border-radius: 0.5rem; }
    #cy { width: 100%; height: 500px; background-color: #0F172A; border-radius: 0.5rem; }
  </style>
</head>
<body class="min-h-screen p-6">
  <header class="mb-8 border-b border-gray-800 pb-5 flex justify-between items-center">
    <div>
      <div class="flex items-center space-x-3">
        <span class="px-2.5 py-1 text-xs font-semibold bg-red-900/60 text-red-300 rounded border border-red-700/50">FORENSIC ENGINE</span>
        <h1 class="text-2xl font-bold tracking-tight text-white">GBP SMOKER</h1>
      </div>
      <p class="text-sm text-gray-400 mt-1">Google Maps netwerk- en beleidsonderzoeksplatform voor Nederland</p>
    </div>
    <div class="flex space-x-3">
      <button onclick="loadStats()" class="px-3.5 py-1.5 text-xs font-medium bg-gray-800 hover:bg-gray-700 text-gray-200 rounded border border-gray-700 transition">Verversen</button>
      <span class="px-3 py-1.5 text-xs font-mono text-emerald-400 bg-emerald-950/40 border border-emerald-800/40 rounded flex items-center">● Engine online</span>
    </div>
  </header>

  <!-- Metric Counters -->
  <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4 mb-8" id="statsGrid">
    <div class="card p-4">
      <div class="text-xs font-medium text-gray-400">Totaal gescand</div>
      <div class="text-2xl font-bold text-white mt-1" id="statScanned">-</div>
      <div class="text-[11px] text-gray-500 mt-1">Geïmporteerde Maps-profielen</div>
    </div>
    <div class="card p-4 border-amber-900/30">
      <div class="text-xs font-medium text-amber-400">Mogelijke policy issues</div>
      <div class="text-2xl font-bold text-amber-300 mt-1" id="statIssues">-</div>
      <div class="text-[11px] text-gray-500 mt-1">Suspicion score ≥ 30</div>
    </div>
    <div class="card p-4 border-indigo-900/30">
      <div class="text-xs font-medium text-indigo-400">Netwerken ontdekt</div>
      <div class="text-2xl font-bold text-indigo-300 mt-1" id="statNetworks">-</div>
      <div class="text-[11px] text-gray-500 mt-1">Gekoppelde clusters</div>
    </div>
    <div class="card p-4">
      <div class="text-xs font-medium text-gray-400">Dossiers / Cases</div>
      <div class="text-2xl font-bold text-white mt-1" id="statCases">-</div>
      <div class="text-[11px] text-gray-500 mt-1">Onderzoeksdossiers</div>
    </div>
    <div class="card p-4 border-emerald-900/30">
      <div class="text-xs font-medium text-emerald-400">Ingediend bij Google</div>
      <div class="text-2xl font-bold text-emerald-300 mt-1" id="statSubmitted">-</div>
      <div class="text-[11px] text-gray-500 mt-1">Officiële Redressal Case IDs</div>
    </div>
  </div>

  <!-- Main Workspace Tabs -->
  <div class="mb-6 flex border-b border-gray-800 space-x-6 text-sm">
    <button onclick="switchTab('networks')" id="tabBtn-networks" class="pb-3 font-medium border-b-2 border-indigo-500 text-indigo-400">Netwerken & graaf</button>
    <button onclick="switchTab('businesses')" id="tabBtn-businesses" class="pb-3 font-medium border-b-2 border-transparent text-gray-400 hover:text-gray-200">Bedrijven & profielen</button>
    <button onclick="switchTab('policies')" id="tabBtn-policies" class="pb-3 font-medium border-b-2 border-transparent text-gray-400 hover:text-gray-200">Beleidskennisbank</button>
    <button onclick="switchTab('cases')" id="tabBtn-cases" class="pb-3 font-medium border-b-2 border-transparent text-gray-400 hover:text-gray-200">Case management</button>
  </div>

  <!-- Tab 1: Networks & Graph -->
  <div id="tab-networks" class="space-y-6">
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div class="card p-4 lg:col-span-1 max-h-[600px] overflow-y-auto">
        <h3 class="text-sm font-semibold text-white mb-3">Gedetecteerde syndicates</h3>
        <div id="networksList" class="space-y-2 text-xs">Laden...</div>
      </div>
      <div class="card p-4 lg:col-span-2">
        <div class="flex justify-between items-center mb-3">
          <h3 class="text-sm font-semibold text-white" id="selectedNetworkTitle">Selecteer een netwerk om de graaf te bekijken</h3>
          <span class="text-xs text-gray-400" id="networkMeta"></span>
        </div>
        <div id="cy"></div>
        <div class="mt-3 p-3 bg-gray-900/60 rounded border border-gray-800 text-xs text-gray-400" id="networkExplanation">
          Kies een netwerk links om de onderlinge verbanden (telefoon, domein, adres) in de graaf te inspecteren.
        </div>
      </div>
    </div>
  </div>

  <!-- Tab 2: Businesses Table -->
  <div id="tab-businesses" class="hidden space-y-4">
    <div class="flex justify-between items-center">
      <input type="text" id="bizSearch" onkeyup="if(event.key==='Enter') searchBusinesses()" placeholder="Zoek op bedrijfsnaam, plaats of domein..." class="bg-gray-900 border border-gray-700 px-3 py-1.5 rounded text-xs text-gray-200 w-80 focus:outline-none focus:border-indigo-500">
      <div class="text-xs text-gray-400" id="bizCountLabel"></div>
    </div>
    <div class="card overflow-x-auto">
      <table class="w-full text-left text-xs text-gray-300">
        <thead class="bg-gray-800/60 text-gray-400 uppercase text-[10px]">
          <tr>
            <th class="p-3">Bedrijf</th>
            <th class="p-3">Plaats</th>
            <th class="p-3">Telefoon</th>
            <th class="p-3">Domein</th>
            <th class="p-3 text-center">Score</th>
            <th class="p-3">Acties</th>
          </tr>
        </thead>
        <tbody id="bizTableBody" class="divide-y divide-gray-800">
          <tr><td colspan="6" class="p-4 text-center text-gray-500">Laden...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Tab 3: Policy KB -->
  <div id="tab-policies" class="hidden space-y-4">
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4" id="policiesGrid">Laden...</div>
  </div>

  <!-- Tab 4: Cases -->
  <div id="tab-cases" class="hidden space-y-4">
    <div class="card p-4 overflow-x-auto">
      <table class="w-full text-left text-xs text-gray-300">
        <thead class="bg-gray-800/60 text-gray-400 uppercase text-[10px]">
          <tr>
            <th class="p-3">Case ID</th>
            <th class="p-3">Titel</th>
            <th class="p-3">Prioriteit</th>
            <th class="p-3">Status</th>
            <th class="p-3">Behandelaar</th>
            <th class="p-3">Aanmaakdatum</th>
          </tr>
        </thead>
        <tbody id="casesTableBody" class="divide-y divide-gray-800">
          <tr><td colspan="6" class="p-4 text-center text-gray-500">Laden...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <script>
    let currentCy = null;

    async function loadStats() {
      try {
        const res = await fetch('/api/stats');
        const d = await res.json();
        document.getElementById('statScanned').innerText = d.total_businesses_scanned;
        document.getElementById('statIssues').innerText = d.potential_policy_issues;
        document.getElementById('statNetworks').innerText = d.networks_detected;
        document.getElementById('statCases').innerText = d.high_priority_cases;
        document.getElementById('statSubmitted').innerText = d.cases_submitted;
      } catch (e) {
        console.error(e);
      }
    }

    async function loadNetworks() {
      try {
        const res = await fetch('/api/networks');
        const d = await res.json();
        const list = document.getElementById('networksList');
        list.innerHTML = '';
        d.items.forEach((net, idx) => {
          const item = document.createElement('div');
          item.className = 'p-2.5 rounded bg-gray-900 hover:bg-gray-800 cursor-pointer border border-gray-800 transition flex justify-between items-center';
          item.onclick = () => selectNetwork(net.id);
          item.innerHTML = `
            <div>
              <div class="font-medium text-white text-[13px]">${net.name}</div>
              <div class="text-[11px] text-gray-500">${net.network_code} • ${net.member_count} profielen • ${net.network_type}</div>
            </div>
            <span class="px-2 py-0.5 rounded text-[11px] font-bold ${net.suspicion_score >= 70 ? 'bg-red-950 text-red-400 border border-red-800' : 'bg-amber-950 text-amber-400 border border-amber-800'}">
              ${net.suspicion_score}
            </span>
          `;
          list.appendChild(item);
          if (idx === 0) selectNetwork(net.id);
        });
      } catch (e) {
        console.error(e);
      }
    }

    async function selectNetwork(networkId) {
      try {
        const res = await fetch(`/api/networks/${networkId}`);
        const d = await res.json();
        document.getElementById('selectedNetworkTitle').innerText = `${d.network.name} (${d.network.network_code})`;
        document.getElementById('networkMeta').innerText = `Suspicion Score: ${d.network.suspicion_score}/100`;

        let reasonsHtml = `<strong class="text-white">Onderbouwing prioriteringsscore:</strong><ul class="list-disc pl-4 mt-1 space-y-0.5">`;
        if (d.network.score_breakdown && d.network.score_breakdown.reasons) {
          d.network.score_breakdown.reasons.forEach(r => {
            reasonsHtml += `<li>+${r.points} pt: ${r.reason}</li>`;
          });
        }
        reasonsHtml += `</ul><div class="mt-2 text-[10px] text-gray-500 italic">Disclaimers: ${d.network.score_breakdown ? d.network.score_breakdown.disclaimer : ''}</div>`;
        document.getElementById('networkExplanation').innerHTML = reasonsHtml;

        renderCytoscape(d.graph);
      } catch (e) {
        console.error(e);
      }
    }

    function renderCytoscape(graphData) {
      if (currentCy) currentCy.destroy();

      const elements = [];
      graphData.nodes.forEach(n => {
        let bg = '#3B82F6';
        if (n.data.type === 'domain') bg = '#10B981';
        if (n.data.type === 'phone') bg = '#F59E0B';
        if (n.data.type === 'address') bg = '#8B5CF6';
        elements.push({ data: { ...n.data, bg } });
      });
      graphData.edges.forEach(e => elements.push(e));

      currentCy = cytoscape({
        container: document.getElementById('cy'),
        elements: elements,
        style: [
          {
            selector: 'node',
            style: {
              'background-color': 'data(bg)',
              'label': 'data(label)',
              'color': '#E2E8F0',
              'font-size': '10px',
              'text-valign': 'bottom',
              'text-margin-y': 4
            }
          },
          {
            selector: 'edge',
            style: {
              'width': 1.5,
              'line-color': '#475569',
              'target-arrow-color': '#475569',
              'target-arrow-shape': 'triangle',
              'curve-style': 'bezier',
              'label': 'data(label)',
              'font-size': '8px',
              'color': '#94A3B8'
            }
          }
        ],
        layout: { name: 'cose', animate: false }
      });
    }

    async function searchBusinesses() {
      const q = document.getElementById('bizSearch').value;
      loadBusinesses(q);
    }

    async function loadBusinesses(search = '') {
      try {
        const res = await fetch(`/api/businesses?limit=30${search ? '&search=' + encodeURIComponent(search) : ''}`);
        const d = await res.json();
        document.getElementById('bizCountLabel').innerText = `Weergave van ${d.items.length} van ${d.total} profielen`;
        const tbody = document.getElementById('bizTableBody');
        tbody.innerHTML = '';
        d.items.forEach(b => {
          const tr = document.createElement('tr');
          tr.className = 'hover:bg-gray-800/40';
          tr.innerHTML = `
            <td class="p-3 font-medium text-white">${b.name}</td>
            <td class="p-3 text-gray-400">${b.city || '-'}</td>
            <td class="p-3 font-mono">${b.normalized_phone || '-'}</td>
            <td class="p-3 text-gray-400">${b.domain || '-'}</td>
            <td class="p-3 text-center">
              <span class="px-2 py-0.5 rounded text-[11px] font-bold ${b.suspicion_score >= 50 ? 'bg-amber-950 text-amber-300' : 'bg-gray-800 text-gray-400'}">
                ${b.suspicion_score}
              </span>
            </td>
            <td class="p-3">
              <a href="${b.google_maps_url}" target="_blank" class="text-indigo-400 hover:underline">Maps link</a>
            </td>
          `;
          tbody.appendChild(tr);
        });
      } catch (e) {
        console.error(e);
      }
    }

    async function loadPolicies() {
      try {
        const res = await fetch('/api/policies');
        const d = await res.json();
        const grid = document.getElementById('policiesGrid');
        grid.innerHTML = '';
        d.items.forEach(p => {
          const card = document.createElement('div');
          card.className = 'card p-4 space-y-2';
          card.innerHTML = `
            <div class="flex justify-between items-start">
              <div>
                <span class="text-[11px] font-mono font-semibold text-indigo-400">${p.policy_id}</span>
                <h4 class="text-sm font-bold text-white mt-0.5">${p.title}</h4>
              </div>
              <span class="px-2 py-0.5 rounded text-[10px] font-semibold ${p.severity === 'CRITICAL' ? 'bg-red-950 text-red-300 border border-red-800' : 'bg-gray-800 text-gray-300'}">${p.severity}</span>
            </div>
            <p class="text-xs text-gray-400 leading-relaxed">${p.description}</p>
            <div class="pt-2 border-t border-gray-800 flex justify-between items-center text-[11px] text-gray-500">
              <span>Geverifieerd: ${p.last_verified}</span>
              <a href="${p.official_source_url}" target="_blank" class="text-indigo-400 hover:underline">Officiële Google bron</a>
            </div>
          `;
          grid.appendChild(card);
        });
      } catch (e) {
        console.error(e);
      }
    }

    async function loadCases() {
      try {
        const res = await fetch('/api/cases');
        const d = await res.json();
        const tbody = document.getElementById('casesTableBody');
        tbody.innerHTML = '';
        d.items.forEach(c => {
          const tr = document.createElement('tr');
          tr.className = 'hover:bg-gray-800/40';
          tr.innerHTML = `
            <td class="p-3 font-mono font-medium text-indigo-400">${c.case_code}</td>
            <td class="p-3 text-white">${c.title}</td>
            <td class="p-3"><span class="px-2 py-0.5 rounded text-[10px] font-bold ${c.priority === 'HIGH' ? 'bg-red-950 text-red-300' : 'bg-gray-800 text-gray-300'}">${c.priority}</span></td>
            <td class="p-3 font-medium text-emerald-400">${c.status}</td>
            <td class="p-3 text-gray-400">${c.reviewer_name || '-'}</td>
            <td class="p-3 text-gray-500">${c.created_at ? c.created_at.substring(0, 10) : '-'}</td>
          `;
          tbody.appendChild(tr);
        });
      } catch (e) {
        console.error(e);
      }
    }

    function switchTab(tab) {
      ['networks', 'businesses', 'policies', 'cases'].forEach(t => {
        document.getElementById(`tab-${t}`).classList.add('hidden');
        document.getElementById(`tabBtn-${t}`).className = 'pb-3 font-medium border-b-2 border-transparent text-gray-400 hover:text-gray-200';
      });
      document.getElementById(`tab-${tab}`).classList.remove('hidden');
      document.getElementById(`tabBtn-${tab}`).className = 'pb-3 font-medium border-b-2 border-indigo-500 text-indigo-400';

      if (tab === 'businesses') loadBusinesses();
      if (tab === 'policies') loadPolicies();
      if (tab === 'cases') loadCases();
    }

    // Init
    loadStats();
    loadNetworks();
  </script>
</body>
</html>
"""
