#!/usr/bin/env python3
"""
production_readiness_command_center.py

Maximum-complexity production-readiness command center for the Semantic Protocol
Runtime / Completefication stack.

Purpose
-------
This file is a self-contained, dependency-free browser cockpit that turns the
research prototype into a serious productization command surface. It does not
pretend the repository is already resale-ready; instead it exposes the exact
production-readiness domains required to make it resale-ready:

- packaging
- docs
- tests
- CI/CD
- audit vault
- proof manifests
- policy gatekeeper
- secrets scanning
- rollback
- replay
- cost ledger
- model governance
- security controls
- enterprise evidence export
- release readiness
- support readiness
- commercial readiness

Run
---
    python production_readiness_command_center.py

Open
----
    http://localhost:8899

Environment
-----------
    PORT=8899
    PRCC_WORKSPACE=/path/to/repo

Security model
--------------
The UI only exposes bounded read-only diagnostics and plan generation. It does
not expose arbitrary remote shell access. Mutating actions should still run
through CLI confirmation flows in completefication.py.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse


APP_NAME = "Production Readiness Command Center"
APP_VERSION = "0.4.0"
PORT = int(os.environ.get("PORT", "8899"))
WORKSPACE = pathlib.Path(os.environ.get("PRCC_WORKSPACE", ".")).resolve()
COMMAND_TIMEOUT = int(os.environ.get("PRCC_TIMEOUT", "25"))
MAX_OUTPUT = int(os.environ.get("PRCC_MAX_OUTPUT", "14000"))

IGNORE_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", "node_modules", "dist", "build", ".venv", "venv", "env", ".next", ".cache"}
TEXT_SUFFIXES = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".spr", ".html", ".css", ".js", ".ts"}


@dataclass
class ReadinessDomain:
    key: str
    name: str
    status: str
    score: int
    target: str
    current_gap: str
    required_artifacts: List[str]
    command: str
    enterprise_value: str


DOMAINS: List[ReadinessDomain] = [
    ReadinessDomain("packaging", "Packaging", "started", 45, "Installable package with stable CLI entry points", "pyproject exists, but module split and release metadata still need hardening", ["pyproject.toml", "CHANGELOG.md", "src/spr package", "versioning policy"], "python -m pip install -e .[dev] && spr --help", "Turns research scripts into an installable developer product"),
    ReadinessDomain("docs", "Documentation", "partial", 30, "Quickstart, tutorials, API docs, language reference, production guide", "README still research-heavy; user-facing docs need restructuring", ["docs/quickstart.md", "docs/language-reference.md", "docs/policy-model.md", "docs/production-readiness.md"], "python production_readiness_command_center.py", "Reduces buyer friction and support burden"),
    ReadinessDomain("tests", "Testing", "started", 35, "Parser, policy, planner, lowerer, runtime, CLI, regression tests", "Baseline tests exist, coverage not comprehensive", ["tests/test_parser.py", "tests/test_policy.py", "tests/test_planner.py", "tests/test_runtime.py"], "pytest -q", "Creates trust that the runtime is not a fragile demo"),
    ReadinessDomain("ci", "CI/CD", "started", 40, "Multi-version CI, packaging checks, CLI smoke tests, security scans", "CI exists but needs release, coverage, and artifact gates", [".github/workflows/ci.yml", ".github/workflows/release.yml", "coverage.xml"], "gh workflow run CI", "Enterprise buyers expect automated verification"),
    ReadinessDomain("audit", "Audit Vault", "planned", 10, "Every run stores intent, context, plan, diffs, commands, outputs, report", "No complete run artifact vault yet", [".spr_runs/<run_id>/plan.json", "command_outputs.json", "final_report.md"], "spr run examples/hot_users.spr --audit-dir .spr_runs", "Transforms agent outputs into audit evidence"),
    ReadinessDomain("proof", "Proof Manifest", "planned", 10, "SHA-256 manifest for source, plan, patch, outputs, report", "No signed/tamper-evident artifact chain yet", ["proof_manifest.json", "hashes.json", "repo_before_after.json"], "python tools/proof_manifest.py .spr_runs/<run_id>", "Supports reproducibility, provenance, and investor/customer trust"),
    ReadinessDomain("policy", "Policy Gatekeeper", "partial", 30, "Machine-readable allow/deny controls for files, commands, network, models", "Runtime has semantic policy, terminal agent policy needs a formal external policy file", ["completefication_policy.yaml", "policy_gatekeeper.py", "policy tests"], "python policy_gatekeeper.py --check completefication_policy.yaml", "The core enterprise safety layer"),
    ReadinessDomain("security", "Security Controls", "partial", 25, "Secrets scan, forbidden commands, path confinement, network controls, local-only mode", "Basic command/path controls exist; secrets scanning and formal local-only mode missing", ["secrets_scanner.py", "local-only profile", "security tests"], "python secrets_scanner.py .", "Required for private repos and regulated environments"),
    ReadinessDomain("rollback", "Rollback Manager", "planned", 5, "Snapshot changed files before edits and restore failed runs", "No rollback artifact manager yet", ["rollback_manifest.json", "before/after snapshots", "rollback CLI"], "python completefication_rollback.py .spr_runs/<run_id>", "Makes AI code mutation operationally safe"),
    ReadinessDomain("replay", "Replay Engine", "planned", 5, "Replay a run from saved plan and artifacts", "No replay command yet", ["completefication_replay.py", "replay report", "verify-only mode"], "python completefication_replay.py .spr_runs/<run_id> --verify-only", "Proves the agent did not hallucinate completion"),
    ReadinessDomain("cost", "Cost Ledger", "planned", 10, "Track model cost, terminal time, repair tax, value-to-cost ratio", "No quantitative run economics yet", ["cost_ledger.json", "roi_report.md", "model_usage.json"], "python cost_ledger.py .spr_runs/<run_id>", "Turns developer productivity into CFO-readable metrics"),
    ReadinessDomain("models", "Model Governance", "partial", 20, "Planner/coder/critic/security/reporter roles with model registry", "Current provider selection is simple; no multi-model arbitration registry", ["models.yaml", "model_registry.py", "critic model flow"], "python model_registry.py --list", "Reduces single-model failure risk"),
    ReadinessDomain("ux", "Operator UX", "started", 35, "Neomorphic approval cockpit with plan, diff, logs, risks, proof, cost", "UI prototypes exist, but not wired to full mutation lifecycle", ["completefication_neomorphic_ui.py", "production_readiness_command_center.py"], "python production_readiness_command_center.py", "Makes the system demonstrable and sellable"),
    ReadinessDomain("release", "Release Engineering", "planned", 10, "GitHub releases, PyPI publish, Docker image, changelog, semantic versioning", "No release workflow or published package", ["CHANGELOG.md", "Dockerfile", "release.yml", "PyPI token workflow"], "python -m build", "Required for distribution"),
    ReadinessDomain("support", "Support Surface", "planned", 5, "Issue templates, discussion docs, troubleshooting, SLA-ready process", "No formal support infrastructure", [".github/ISSUE_TEMPLATE", "docs/troubleshooting.md", "SUPPORT.md"], "n/a", "Needed for commercial customers"),
    ReadinessDomain("legal", "Commercial Legal", "planned", 5, "Commercial license option, EULA, disclaimers, support terms", "MIT exists but no commercial/legal framework", ["COMMERCIAL_LICENSE.md", "EULA.md", "DISCLAIMER.md"], "n/a", "Required before serious resale"),
]


READ_ONLY_COMMANDS: Dict[str, List[str]] = {
    "pwd": ["pwd"],
    "git_status": ["git", "status", "--short"],
    "git_branch": ["git", "branch", "--show-current"],
    "python_version": ["python", "--version"],
    "pytest": ["python", "-m", "pytest", "-q"],
    "spr_help": ["python", "semantic_protocol_runtime.py", "--help"],
    "complete_help": ["python", "completefication.py", "--help"],
}


HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Production Readiness Command Center</title>
<style>
:root{
  --bg:#e7ebf2;--panel:#e9edf4;--text:#1f2433;--muted:#6d7485;--orange:#ff8b2f;--gold:#f3c86a;--blue:#5868ff;--green:#20b875;--red:#e84d5b;--purple:#8d5cff;
  --shadow-dark:rgba(139,148,166,.55);--shadow-light:rgba(255,255,255,.95);--inner-dark:rgba(139,148,166,.34);--inner-light:rgba(255,255,255,.98);
  --mono:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono",monospace;--sans:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
}
*{box-sizing:border-box}body{margin:0;font-family:var(--sans);color:var(--text);background:radial-gradient(circle at 10% 0%,#fff7e7 0,#edf0f6 31%,#d7dde8 100%)}.wrap{max-width:1440px;margin:0 auto;padding:28px}.top{display:flex;justify-content:space-between;gap:20px;align-items:center;margin-bottom:24px}.brand{display:flex;gap:16px;align-items:center}.mark{width:62px;height:62px;border-radius:24px;background:linear-gradient(145deg,#fafcff,#cfd5df);box-shadow:14px 14px 28px var(--shadow-dark),-14px -14px 28px var(--shadow-light);position:relative}.mark:after{content:"";position:absolute;inset:14px;border-radius:16px;background:linear-gradient(145deg,var(--orange),var(--gold));box-shadow:inset 4px 4px 8px rgba(70,42,0,.28), inset -4px -4px 8px rgba(255,255,255,.4)}h1{font-size:clamp(40px,6vw,84px);line-height:.9;letter-spacing:-.075em;margin:0}h2{font-size:24px;margin:0 0 16px}h3{margin:0 0 9px}.muted{color:var(--muted)}.grid{display:grid;gap:22px}.hero{grid-template-columns:1.05fr .95fr}.two{grid-template-columns:1fr 1fr}.three{grid-template-columns:repeat(3,1fr)}.four{grid-template-columns:repeat(4,1fr)}.six{grid-template-columns:repeat(6,1fr)}.card{background:var(--panel);border-radius:30px;padding:26px;box-shadow:18px 18px 40px var(--shadow-dark),-18px -18px 40px var(--shadow-light)}.inset{background:var(--panel);border-radius:24px;padding:18px;box-shadow:inset 8px 8px 16px var(--inner-dark),inset -8px -8px 16px var(--inner-light)}.pill,.tag{display:inline-flex;align-items:center;border-radius:999px;padding:8px 11px;margin:4px 5px 4px 0;background:var(--panel);box-shadow:inset 4px 4px 8px var(--inner-dark),inset -4px -4px 8px var(--inner-light);font-size:12px;font-weight:900;color:#3a4050}.btn{border:0;border-radius:18px;background:linear-gradient(145deg,#f9fbff,#d5dbe6);box-shadow:8px 8px 16px var(--shadow-dark),-8px -8px 16px var(--shadow-light);padding:13px 16px;font-weight:900;color:#2d3141;cursor:pointer}.btn.primary{background:linear-gradient(145deg,#ffa451,#f07b16);color:#fff}.btn.blue{background:linear-gradient(145deg,#7381ff,#4658f0);color:#fff}.btn:active{box-shadow:inset 6px 6px 10px var(--inner-dark),inset -6px -6px 10px var(--inner-light)}textarea,input,select{width:100%;border:0;outline:0;border-radius:20px;background:var(--panel);box-shadow:inset 8px 8px 16px var(--inner-dark),inset -8px -8px 16px var(--inner-light);padding:15px;color:var(--text);font:14px var(--sans)}textarea{min-height:140px;font-family:var(--mono);resize:vertical}.kpi b{font-size:34px}.kpi{min-height:112px}.progress{height:14px;border-radius:999px;background:var(--panel);box-shadow:inset 5px 5px 10px var(--inner-dark),inset -5px -5px 10px var(--inner-light);overflow:hidden}.bar{height:100%;border-radius:999px;background:linear-gradient(90deg,var(--red),var(--orange),var(--green));width:0%}.domain{display:grid;grid-template-columns:78px 1fr 160px;gap:16px;align-items:center;margin:14px 0}.score{height:58px;width:58px;border-radius:20px;display:grid;place-items:center;font-weight:1000;background:linear-gradient(145deg,#fff,#cfd5df);box-shadow:7px 7px 14px var(--shadow-dark),-7px -7px 14px var(--shadow-light);color:var(--orange)}pre{margin:0;white-space:pre-wrap;word-break:break-word;font-family:var(--mono);font-size:13px}.output{min-height:220px;max-height:520px;overflow:auto}.ok{color:var(--green)}.bad{color:var(--red)}.warn{color:var(--orange)}.accent{color:var(--orange)}.nav{display:flex;gap:10px;flex-wrap:wrap}.matrix{overflow:auto}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:12px;border-bottom:1px solid rgba(80,90,110,.12);font-size:13px}th{color:#3a4050}.footer{padding:36px 0;color:var(--muted)}@media(max-width:1050px){.hero,.two,.three,.four,.six{grid-template-columns:1fr}.domain{grid-template-columns:1fr}.top{align-items:flex-start;flex-direction:column}h1{font-size:52px}}
</style>
</head>
<body>
<main class="wrap">
<section class="top"><div class="brand"><div class="mark"></div><div><h1>Production Command Center</h1><div class="muted">Semantic Protocol Runtime · Completefication · resale-readiness operating cockpit</div></div></div><div class="pill">research prototype → productized developer platform</div></section>
<section class="grid hero">
<div class="card"><h2>Maximum-complexity production readiness surface</h2><p class="muted" style="font-size:18px;line-height:1.55">This cockpit does not pretend the product is finished. It operationalizes the path to a sellable system: packaging, docs, tests, CI, audit vault, proof manifests, policy gatekeeper, rollback, replay, cost ledger, model governance, security, release, support, and commercial legal readiness.</p><div class="nav"><button class="btn primary" onclick="loadReadiness()">Recalculate readiness</button><button class="btn" onclick="runOp('git_status')">Git status</button><button class="btn" onclick="runOp('pytest')">Run tests</button><button class="btn blue" onclick="generatePlan()">Generate max build plan</button></div></div>
<div class="card"><h2>Resale readiness index</h2><div class="grid four"><div class="inset kpi"><b id="overall">—</b><div class="muted">overall score</div></div><div class="inset kpi"><b id="files">—</b><div class="muted">files detected</div></div><div class="inset kpi"><b id="domains">16</b><div class="muted">domains</div></div><div class="inset kpi"><b class="warn">ALPHA</b><div class="muted">truth state</div></div></div><div style="height:16px"></div><div class="progress"><div id="overallBar" class="bar"></div></div><p class="muted">Target for early-access resale: 60+. Target for enterprise resale: 80+.</p></div>
</section>
<section class="grid two" style="margin-top:24px"><div class="card"><h2>Operator command</h2><textarea id="intent">Maximize production readiness: add audit vault, proof manifest, policy gatekeeper, rollback manager, replay engine, cost ledger, model governance, secrets scanner, release workflow, docs, tests, and neomorphic approval UI.</textarea><div style="height:14px"></div><div class="grid two"><button class="btn primary" onclick="generatePlan()">Generate CLI build sequence</button><button class="btn" onclick="copyPlan()">Copy current output</button></div></div><div class="card"><h2>Grounded output</h2><div class="inset output"><pre id="out">Ready. Recalculate readiness or generate a build plan.</pre></div><div class="nav" style="margin-top:14px"><button class="btn" onclick="runOp('pwd')">pwd</button><button class="btn" onclick="runOp('git_branch')">branch</button><button class="btn" onclick="runOp('spr_help')">spr help</button><button class="btn" onclick="runOp('complete_help')">complete help</button></div></div></section>
<section class="card" style="margin-top:24px"><h2>Readiness domain board</h2><div id="domainBoard"></div></section>
<section class="grid three" style="margin-top:24px"><div class="card"><h2>Enterprise modules</h2><div id="enterpriseModules"></div></div><div class="card"><h2>Evidence artifacts</h2><div class="inset"><pre id="evidenceTree"></pre></div></div><div class="card"><h2>Risk gates</h2><div id="riskGates"></div></div></section>
<section class="card matrix" style="margin-top:24px"><h2>Production acceptance matrix</h2><table><thead><tr><th>Layer</th><th>Acceptance criterion</th><th>Command / artifact</th><th>Commercial impact</th></tr></thead><tbody id="matrix"></tbody></table></section>
<section class="grid three" style="margin-top:24px"><div class="card"><h2>CLI commands</h2><div class="inset"><pre id="cliCommands"></pre></div></div><div class="card"><h2>Pricing posture</h2><div class="inset"><pre>Free: local dry-run + examples
Pro: completefication + repair loop
Founder: audit vault + proof manifests
Team: policy gatekeeper + CI/CD PR mode
Enterprise: local-only, compliance export, approvals
Regulated: signed evidence bundles + custom policy</pre></div></div><div class="card"><h2>Truth label</h2><p class="muted">Current state should be sold only as early-access / pilot / research-grade unless the readiness score crosses the target threshold and the acceptance matrix is satisfied.</p><span class="tag bad">not resale-ready today</span><span class="tag warn">commercial potential</span><span class="tag ok">productization path active</span></div></section>
<div class="footer">Production Readiness Command Center · read-only diagnostics · generated build plans · serious productization cockpit</div>
</main>
<script>
async function post(path, body){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});return await r.json()}
function out(x){document.getElementById('out').textContent=typeof x==='string'?x:JSON.stringify(x,null,2)}
function tag(x){return `<span class="tag">${x}</span>`}
async function loadReadiness(){const d=await post('/api/readiness',{});document.getElementById('overall').textContent=d.overall_score+'/100';document.getElementById('files').textContent=d.file_count;document.getElementById('domains').textContent=d.domains.length;document.getElementById('overallBar').style.width=d.overall_score+'%';renderDomains(d.domains);renderModules(d);renderMatrix(d.matrix);out(d.summary)}
function renderDomains(domains){document.getElementById('domainBoard').innerHTML=domains.map(x=>`<div class="domain"><div class="score">${x.score}</div><div><h3>${x.name} <span class="tag">${x.status}</span></h3><p class="muted">${x.current_gap}</p><div>${x.required_artifacts.map(tag).join('')}</div></div><div><button class="btn" onclick="out(${JSON.stringify(JSON.stringify(x,null,2))})">Details</button></div></div>`).join('')}
function renderModules(d){document.getElementById('enterpriseModules').innerHTML=d.enterprise_modules.map(m=>`<div class="inset" style="margin:12px 0"><h3>${m.name}</h3><p class="muted">${m.description}</p>${m.tags.map(tag).join('')}</div>`).join('');document.getElementById('evidenceTree').textContent=d.evidence_tree;document.getElementById('riskGates').innerHTML=d.risk_gates.map(g=>`<div class="inset" style="margin:12px 0"><h3>${g.name}</h3><p class="muted">${g.rule}</p><span class="tag ${g.level==='critical'?'bad':'warn'}">${g.level}</span></div>`).join('');document.getElementById('cliCommands').textContent=d.cli_commands.join('\n')}
function renderMatrix(rows){document.getElementById('matrix').innerHTML=rows.map(r=>`<tr><td>${r.layer}</td><td>${r.criterion}</td><td><code>${r.command}</code></td><td>${r.impact}</td></tr>`).join('')}
async function runOp(name){out('Running '+name+'...');out(await post('/api/read_only',{name}))}
async function generatePlan(){const intent=document.getElementById('intent').value;const d=await post('/api/plan',{intent});out(d);document.getElementById('cliCommands').textContent=d.commands.join('\n')}
function copyPlan(){navigator.clipboard&&navigator.clipboard.writeText(document.getElementById('out').textContent)}
loadReadiness();
</script>
</body>
</html>'''


def json_response(handler: BaseHTTPRequestHandler, payload: Dict[str, Any], status: int = 200) -> None:
    data = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(data)


def html_response(handler: BaseHTTPRequestHandler) -> None:
    data = HTML.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(data)


def read_body(handler: BaseHTTPRequestHandler) -> Dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length <= 0:
        return {}
    try:
        return json.loads(handler.rfile.read(length).decode("utf-8"))
    except json.JSONDecodeError:
        return {}


def text_files() -> List[pathlib.Path]:
    files: List[pathlib.Path] = []
    for root, dirs, names in os.walk(WORKSPACE):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for name in names:
            p = pathlib.Path(root) / name
            if p.suffix.lower() in TEXT_SUFFIXES or p.name in {"README", "LICENSE", "Makefile", "Dockerfile"}:
                files.append(p)
    return files


def artifact_exists(path: str) -> bool:
    return (WORKSPACE / path).exists()


def computed_domains() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for d in DOMAINS:
        row = asdict(d)
        hits = sum(1 for a in d.required_artifacts if artifact_exists(a.split("/")[0]) or artifact_exists(a))
        if hits:
            row["detected_artifact_hits"] = hits
            row["computed_score"] = min(100, max(d.score, d.score + hits * 5))
        else:
            row["detected_artifact_hits"] = 0
            row["computed_score"] = d.score
        row["score"] = row["computed_score"]
        out.append(row)
    return out


def run_read_only(name: str) -> Dict[str, Any]:
    if name not in READ_ONLY_COMMANDS:
        return {"ok": False, "error": f"Unknown read-only operation: {name}"}
    cmd = READ_ONLY_COMMANDS[name]
    if shutil.which(cmd[0]) is None and not pathlib.Path(cmd[0]).exists():
        return {"ok": False, "cmd": cmd, "error": f"Command unavailable: {cmd[0]}"}
    start = time.time()
    try:
        proc = subprocess.run(cmd, cwd=str(WORKSPACE), text=True, capture_output=True, timeout=COMMAND_TIMEOUT)
        output = ""
        if proc.stdout:
            output += proc.stdout
        if proc.stderr:
            output += "\n[stderr]\n" + proc.stderr
        output = output.strip() or "(no output)"
        if len(output) > MAX_OUTPUT:
            output = output[:MAX_OUTPUT] + "\n...[truncated]"
        return {"ok": proc.returncode == 0, "operation": name, "cmd": cmd, "returncode": proc.returncode, "elapsed_s": round(time.time() - start, 3), "output": output}
    except Exception as exc:
        return {"ok": False, "operation": name, "cmd": cmd, "error": str(exc), "elapsed_s": round(time.time() - start, 3)}


def readiness_payload() -> Dict[str, Any]:
    domains = computed_domains()
    overall = round(sum(d["score"] for d in domains) / len(domains)) if domains else 0
    return {
        "ok": True,
        "workspace": str(WORKSPACE),
        "file_count": len(text_files()),
        "overall_score": overall,
        "truth_state": "research prototype / productization in progress",
        "summary": {
            "current_state": "Not resale-ready yet, but productization scaffolding is being added.",
            "overall_score": overall,
            "early_access_target": 60,
            "enterprise_target": 80,
            "next_priority": ["audit vault", "proof manifest", "policy gatekeeper", "secrets scanner", "rollback/replay", "docs/tests"],
        },
        "domains": domains,
        "enterprise_modules": enterprise_modules(),
        "evidence_tree": evidence_tree(),
        "risk_gates": risk_gates(),
        "matrix": acceptance_matrix(),
        "cli_commands": cli_commands(),
    }


def enterprise_modules() -> List[Dict[str, Any]]:
    return [
        {"name": "Audit Vault", "description": "Immutable run folders containing intent, context, plan, patch, commands, outputs, repairs, and report.", "tags": ["evidence", "audit", "enterprise"]},
        {"name": "Proof Manifest", "description": "SHA-256 artifact chain over source, plan, patches, outputs, and report.", "tags": ["provenance", "hashes", "anti-tamper"]},
        {"name": "Policy Gatekeeper", "description": "External policy file for commands, files, network, secrets, models, and approval requirements.", "tags": ["safety", "controls", "governance"]},
        {"name": "Replay Engine", "description": "Re-run or verify a saved run folder to prove results are reproducible.", "tags": ["replay", "verification", "trust"]},
        {"name": "Cost Ledger", "description": "Track model usage, terminal seconds, repair tax, files changed, and estimated human value.", "tags": ["ROI", "CFO", "metrics"]},
        {"name": "Rollback Manager", "description": "Snapshot files before mutation and restore failed or rejected runs.", "tags": ["safety", "restore", "ops"]},
    ]


def evidence_tree() -> str:
    return ".spr_runs/<run_id>/\n  intent.txt\n  repo_context.json\n  model_request.json\n  model_response.json\n  plan.json\n  patch_manifest.json\n  before/\n  after/\n  command_outputs.json\n  repair_attempts.json\n  cost_ledger.json\n  proof_manifest.json\n  final_report.md\n  evidence_bundle.zip"


def risk_gates() -> List[Dict[str, str]]:
    return [
        {"name": "No shell strings", "rule": "Commands must be argv arrays, never shell=True.", "level": "critical"},
        {"name": "Workspace confinement", "rule": "Reads/writes cannot escape the repository root.", "level": "critical"},
        {"name": "Secrets redaction", "rule": "Secrets must not be sent to LLMs, saved in logs, or spoken by TTS.", "level": "critical"},
        {"name": "Human approval", "rule": "Writes, network, process, and system operations require explicit approval.", "level": "critical"},
        {"name": "Replayable proof", "rule": "Every successful run must have a proof manifest and command output record.", "level": "high"},
        {"name": "Rollback available", "rule": "Before mutation, changed files must be recoverable.", "level": "high"},
    ]


def acceptance_matrix() -> List[Dict[str, str]]:
    rows = []
    for d in DOMAINS:
        rows.append({"layer": d.name, "criterion": d.target, "command": d.command, "impact": d.enterprise_value})
    return rows


def cli_commands() -> List[str]:
    return [
        "python -m pip install -e .[dev]",
        "spr --help",
        "spr explain examples/hot_users.spr",
        "pytest -q",
        "python completefication.py 'add audit vault and proof manifest' --provider ollama --model llama3.2 --dry-run",
        "python completefication_neomorphic_ui.py",
        "python production_readiness_command_center.py",
    ]


def generate_plan(intent: str) -> Dict[str, Any]:
    intent = (intent or "").strip() or "Maximize production readiness."
    commands = [
        f"python completefication.py {json.dumps('add audit vault with run artifact folders and proof manifest')} --dry-run",
        f"python completefication.py {json.dumps('add policy gatekeeper with yaml allow deny controls and tests')} --dry-run",
        f"python completefication.py {json.dumps('add rollback and replay engine for completefication runs')} --dry-run",
        f"python completefication.py {json.dumps('add cost ledger and ROI dashboard artifacts')} --dry-run",
        f"python completefication.py {json.dumps('add docs quickstart language reference and production guide')} --dry-run",
        "pytest -q",
        "spr explain examples/hot_users.spr",
    ]
    return {
        "ok": True,
        "intent": intent,
        "build_sequence": [
            "freeze current prototype baseline",
            "add audit/proof primitives",
            "formalize policy gatekeeper",
            "add rollback/replay safety",
            "expand tests and examples",
            "wire UI to run artifacts",
            "publish docs and release pipeline",
        ],
        "commands": commands,
        "definition_of_done": [
            "fresh clone installs with pip -e .[dev]",
            "spr explain/run examples work",
            "pytest passes in CI",
            "audit folder generated for every run",
            "proof manifest hashes artifacts",
            "rollback can restore changed files",
            "replay can verify saved runs",
            "docs explain install, grammar, policies, risks, and examples",
        ],
    }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if urlparse(self.path).path in {"/", "/index.html"}:
            html_response(self)
            return
        json_response(self, {"ok": False, "error": "not found"}, 404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        body = self.read_json()
        if path == "/api/readiness":
            json_response(self, readiness_payload())
        elif path == "/api/read_only":
            json_response(self, run_read_only(str(body.get("name", ""))))
        elif path == "/api/plan":
            json_response(self, generate_plan(str(body.get("intent", ""))))
        else:
            json_response(self, {"ok": False, "error": "unknown endpoint"}, 404)

    def read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    def log_message(self, fmt: str, *args: Any) -> None:
        return


def main() -> int:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"{APP_NAME} v{APP_VERSION}")
    print(f"Workspace: {WORKSPACE}")
    print(f"Open: http://localhost:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
