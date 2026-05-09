#!/usr/bin/env python3
"""
completefication_neomorphic_ui.py

Neomorphic UI for the Completefication Protocol.

Completefication Protocol
-------------------------
A one-command, LLM-backed terminal programming system where normal English becomes:

    intent -> repo inspection -> structured plan -> bounded file edits
    -> terminal checks -> repair loop -> grounded completion report

This file is intentionally self-contained and dependency-free. It serves a polished
neomorphic browser UI from a Python HTTP server and exposes local endpoints that
can preview protocol plans, run safe read-only terminal operations, and describe
how to connect the UI to completefication.py / voice_terminal_agent.py.

Run:
    python completefication_neomorphic_ui.py

Open:
    http://localhost:8787

Optional:
    PORT=8787 python completefication_neomorphic_ui.py

Security posture
----------------
- No shell=True.
- Browser API only exposes a small allowlisted set of read-only operations.
- File writes and true completefication execution should remain behind the CLI
  confirmation loop in completefication.py.
- This UI is the protocol cockpit, not an unsafe remote shell.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import time
from dataclasses import dataclass, asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


APP_NAME = "Completefication Protocol UI"
APP_VERSION = "0.3.0"
PORT = int(os.environ.get("PORT", "8787"))
WORKSPACE = pathlib.Path(os.environ.get("COMPLETE_WORKSPACE", ".")).resolve()
COMMAND_TIMEOUT = int(os.environ.get("COMPLETE_UI_TIMEOUT", "20"))
MAX_OUTPUT = int(os.environ.get("COMPLETE_UI_MAX_OUTPUT", "10000"))

READ_ONLY_COMMANDS: Dict[str, List[str]] = {
    "pwd": ["pwd"],
    "git_status": ["git", "status", "--short"],
    "git_branch": ["git", "branch", "--show-current"],
    "python_version": ["python", "--version"],
    "list_files": ["python", "-c", "import os; print('\\n'.join(sorted([p for p in os.listdir('.') if p not in {'.git','__pycache__'}])))"],
}


@dataclass
class ProtocolStage:
    index: int
    name: str
    purpose: str
    input: str
    output: str
    guardrail: str


PROTOCOL_STAGES: List[ProtocolStage] = [
    ProtocolStage(1, "Intent Capture", "Accept normal English from voice, text, or CLI.", "Human command", "Canonical task string", "Do not execute yet."),
    ProtocolStage(2, "Context Scan", "Inspect repo files, git state, manifests, tests, and runtime entry points.", "Workspace", "Context JSON", "Read-only by default."),
    ProtocolStage(3, "LLM Planning", "Convert the task and repo context into structured edits and commands.", "Task + context", "JSON plan", "No shell strings; argv only."),
    ProtocolStage(4, "Human Gate", "Show files, reasons, commands, and risks before mutation.", "Plan", "Approval / cancellation", "Writes require confirmation."),
    ProtocolStage(5, "Apply Edits", "Write complete replacement files inside the workspace.", "Approved edits", "Updated repo tree", "Path confinement."),
    ProtocolStage(6, "Terminal Verification", "Run tests, --help checks, lint, or project-specific verification.", "Commands", "Command outputs", "Timeout and forbidden command list."),
    ProtocolStage(7, "Repair Loop", "If checks fail, ask the LLM for targeted repairs and retest.", "Failures", "Repair patch", "Limited iterations."),
    ProtocolStage(8, "Grounded Report", "Summarize what actually changed and which checks passed or failed.", "Edits + outputs", "Completion report", "No unsupported success claims."),
]


HTML = r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Completefication Protocol UI</title>
  <style>
    :root{
      --bg:#e7ebf1; --bg2:#d9dee7; --panel:#e9edf4; --text:#202331; --muted:#6d7485;
      --accent:#ff8a2a; --accent2:#f1c75b; --blue:#5568ff; --green:#20b875; --red:#e84d5b;
      --shadow-dark:rgba(143,151,169,.55); --shadow-light:rgba(255,255,255,.92);
      --inner-dark:rgba(143,151,169,.38); --inner-light:rgba(255,255,255,.95);
      --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
      --sans: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    *{box-sizing:border-box} body{margin:0;background:radial-gradient(circle at 20% 0%,#fff7e7 0,#e7ebf1 35%,#d9dee7 100%);font-family:var(--sans);color:var(--text)}
    .wrap{max-width:1240px;margin:0 auto;padding:28px} .top{display:flex;justify-content:space-between;align-items:center;gap:18px;margin-bottom:28px}
    .brand{display:flex;gap:16px;align-items:center}.orb{width:58px;height:58px;border-radius:22px;background:linear-gradient(145deg,#f9fbff,#cfd5df);box-shadow:13px 13px 26px var(--shadow-dark),-13px -13px 26px var(--shadow-light);position:relative}.orb:after{content:"";position:absolute;inset:13px;border-radius:15px;background:linear-gradient(145deg,var(--accent),var(--accent2));box-shadow:inset 4px 4px 8px rgba(70,42,0,.25), inset -4px -4px 8px rgba(255,255,255,.35)}
    h1{font-size:clamp(42px,7vw,86px);letter-spacing:-.075em;line-height:.9;margin:0;color:#252837} h2{font-size:24px;margin:0 0 16px} h3{font-size:18px;margin:0 0 10px}.muted{color:var(--muted)}
    .pill{display:inline-flex;align-items:center;gap:8px;border-radius:999px;padding:10px 14px;background:var(--panel);box-shadow:inset 5px 5px 10px var(--inner-dark), inset -5px -5px 10px var(--inner-light);font-weight:700;color:#3a4050;font-size:13px}
    .grid{display:grid;gap:22px}.hero{grid-template-columns:1.05fr .95fr}.three{grid-template-columns:repeat(3,1fr)}.two{grid-template-columns:1fr 1fr}.four{grid-template-columns:repeat(4,1fr)}
    .card{border-radius:30px;background:var(--panel);box-shadow:18px 18px 38px var(--shadow-dark),-18px -18px 38px var(--shadow-light);padding:28px}.inset{border-radius:24px;background:var(--panel);box-shadow:inset 8px 8px 16px var(--inner-dark), inset -8px -8px 16px var(--inner-light);padding:18px}
    .soft-btn{border:0;border-radius:18px;padding:14px 18px;background:linear-gradient(145deg,#f9fbff,#d7dce6);box-shadow:8px 8px 16px var(--shadow-dark),-8px -8px 16px var(--shadow-light);font-weight:900;color:#2d3141;cursor:pointer}.soft-btn.primary{background:linear-gradient(145deg,#ffa451,#f07c16);color:#fff}.soft-btn:active{box-shadow:inset 6px 6px 10px rgba(110,116,130,.35), inset -6px -6px 10px rgba(255,255,255,.7)}
    textarea,input,select{width:100%;border:0;outline:0;border-radius:20px;background:var(--panel);box-shadow:inset 8px 8px 16px var(--inner-dark), inset -8px -8px 16px var(--inner-light);padding:16px;color:var(--text);font:15px var(--sans)}textarea{min-height:150px;resize:vertical;font-family:var(--mono)}
    .kpi b{font-size:30px}.kpi{min-height:112px}.stage{display:grid;grid-template-columns:54px 1fr;gap:14px;align-items:start;margin:14px 0}.num{height:44px;width:44px;border-radius:16px;background:linear-gradient(145deg,#fff,#cfd5df);box-shadow:7px 7px 14px var(--shadow-dark),-7px -7px 14px var(--shadow-light);display:grid;place-items:center;font-weight:900;color:var(--accent)}
    code,pre{font-family:var(--mono)} pre{white-space:pre-wrap;word-break:break-word;margin:0}.output{min-height:180px;max-height:420px;overflow:auto}.tag{display:inline-flex;margin:4px 6px 4px 0;padding:7px 10px;border-radius:999px;background:var(--panel);box-shadow:inset 4px 4px 8px var(--inner-dark), inset -4px -4px 8px var(--inner-light);font-size:12px;font-weight:800}.ok{color:var(--green)}.bad{color:var(--red)}.accent{color:var(--accent)}
    .flow{display:flex;gap:10px;flex-wrap:wrap}.flow span{padding:12px 14px;border-radius:16px;background:var(--panel);box-shadow:8px 8px 16px var(--shadow-dark),-8px -8px 16px var(--shadow-light);font-size:13px;font-weight:800}.footer{padding:38px 0;color:var(--muted)}
    @media(max-width:900px){.hero,.two,.three,.four{grid-template-columns:1fr}.top{align-items:flex-start;flex-direction:column}h1{font-size:54px}}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="top">
      <div class="brand"><div class="orb"></div><div><h1>Completefication</h1><div class="muted">LLM terminal programming protocol · neomorphic cockpit</div></div></div>
      <div class="pill">normal English → terminal operations → verified code</div>
    </section>

    <section class="grid hero">
      <div class="card">
        <h2>One-command programming protocol</h2>
        <p class="muted" style="font-size:18px;line-height:1.55">Speak or type one normal-English command. The system inspects the repository, asks an LLM for a structured implementation plan, writes bounded file changes, runs terminal checks, repairs failures, and returns a grounded completion report.</p>
        <div class="flow" style="margin:24px 0"><span>Intent</span><span>Inspect</span><span>Plan</span><span>Gate</span><span>Edit</span><span>Verify</span><span>Repair</span><span>Report</span></div>
        <div class="grid two"><button class="soft-btn primary" onclick="previewProtocol()">Preview protocol plan</button><button class="soft-btn" onclick="runReadOnly('git_status')">Check git status</button></div>
      </div>
      <div class="card">
        <h2>Runtime posture</h2>
        <div class="grid four">
          <div class="inset kpi"><b id="kFiles">—</b><div class="muted">workspace files</div></div>
          <div class="inset kpi"><b>0</b><div class="muted">shell=True calls</div></div>
          <div class="inset kpi"><b>8</b><div class="muted">protocol stages</div></div>
          <div class="inset kpi"><b class="ok">SAFE</b><div class="muted">UI mode</div></div>
        </div>
        <p class="muted">This browser cockpit exposes read-only diagnostics. Real code mutation remains in the CLI confirmation loop.</p>
      </div>
    </section>

    <section class="grid two" style="margin-top:24px">
      <div class="card">
        <h2>Command intent</h2>
        <textarea id="intent">Finish the semantic protocol runtime into a voice-first LLM terminal programming system with a neomorphic UI and grounded terminal operations.</textarea>
        <div style="height:14px"></div>
        <div class="grid two"><button class="soft-btn primary" onclick="previewProtocol()">Generate protocol preview</button><button class="soft-btn" onclick="copyCli()">Copy CLI command</button></div>
        <div id="cliBox" class="inset" style="margin-top:16px"><code>python completefication.py "..." --provider ollama --model llama3.2</code></div>
      </div>
      <div class="card">
        <h2>Grounded terminal output</h2>
        <div class="inset output"><pre id="output">Ready. Choose a read-only operation or preview the completefication protocol.</pre></div>
        <div class="flow" style="margin-top:14px"><button class="soft-btn" onclick="runReadOnly('pwd')">pwd</button><button class="soft-btn" onclick="runReadOnly('git_branch')">branch</button><button class="soft-btn" onclick="runReadOnly('python_version')">python</button><button class="soft-btn" onclick="runReadOnly('list_files')">files</button></div>
      </div>
    </section>

    <section class="card" style="margin-top:24px">
      <h2>Full protocol stages</h2>
      <div id="stages"></div>
    </section>

    <section class="grid three" style="margin-top:24px">
      <div class="card"><h3>Voice terminal agent</h3><p class="muted">Normal English is converted into a JSON tool plan; approved terminal operations run; final answers are grounded in command output.</p><span class="tag">voice_terminal_agent.py</span></div>
      <div class="card"><h3>Completefication loop</h3><p class="muted">One command drives inspect, plan, edit, check, repair, and report across the repository.</p><span class="tag">completefication.py</span></div>
      <div class="card"><h3>Semantic runtime</h3><p class="muted">Typed intent, explicit effects, policy verification, planner/lowering, dry-run, and REPL remain the execution substrate.</p><span class="tag">semantic_protocol_runtime.py</span></div>
    </section>

    <section class="card" style="margin-top:24px">
      <h2>Production hardening checklist</h2>
      <div class="grid three">
        <div class="inset"><h3>LLM contract</h3><p class="muted">JSON schema validation, model fallback, deterministic temperature, output size caps, no invented command results.</p></div>
        <div class="inset"><h3>Tool boundary</h3><p class="muted">No shell strings, workspace path confinement, forbidden command list, timeout, dry-run, human gate.</p></div>
        <div class="inset"><h3>Audit layer</h3><p class="muted">Save task, plan, patch, command output, repair attempts, model identity, timestamps, and final report.</p></div>
      </div>
    </section>

    <div class="footer">Completefication Protocol UI · self-contained Python HTTP server · neomorphic design · serious operator cockpit</div>
  </main>
<script>
async function api(path, body){
  const res = await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});
  return await res.json();
}
function setOut(x){document.getElementById('output').textContent=typeof x==='string'?x:JSON.stringify(x,null,2)}
async function runReadOnly(name){setOut('Running '+name+'...'); const data=await api('/api/read_only',{name}); setOut(data)}
async function previewProtocol(){const intent=document.getElementById('intent').value; const data=await api('/api/preview',{intent}); setOut(data); document.getElementById('cliBox').innerHTML='<code>'+data.cli.replaceAll('<','&lt;')+'</code>'}
function copyCli(){const t=document.getElementById('cliBox').innerText;navigator.clipboard&&navigator.clipboard.writeText(t);setOut('Copied CLI command:\n'+t)}
async function load(){const meta=await api('/api/meta',{});document.getElementById('kFiles').textContent=meta.file_count;const stageBox=document.getElementById('stages');stageBox.innerHTML=meta.stages.map(s=>`<div class="stage"><div class="num">${s.index}</div><div><h3>${s.name}</h3><p class="muted">${s.purpose}</p><span class="tag">input: ${s.input}</span><span class="tag">output: ${s.output}</span><span class="tag">guardrail: ${s.guardrail}</span></div></div>`).join('')}
load();
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
    raw = handler.rfile.read(length).decode("utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def run_read_only(name: str) -> Dict[str, Any]:
    if name not in READ_ONLY_COMMANDS:
        return {"ok": False, "error": f"Unknown read-only operation: {name}"}
    cmd = READ_ONLY_COMMANDS[name]
    if shutil.which(cmd[0]) is None and not pathlib.Path(cmd[0]).exists():
        return {"ok": False, "cmd": cmd, "error": f"Command not available: {cmd[0]}"}
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
        return {
            "ok": proc.returncode == 0,
            "operation": name,
            "cmd": cmd,
            "returncode": proc.returncode,
            "elapsed_s": round(time.time() - start, 3),
            "output": output,
        }
    except Exception as exc:
        return {"ok": False, "operation": name, "cmd": cmd, "error": str(exc), "elapsed_s": round(time.time() - start, 3)}


def count_workspace_files() -> int:
    ignored = {".git", "__pycache__", ".pytest_cache", "node_modules", "venv", ".venv", "dist", "build"}
    count = 0
    for root, dirs, files in os.walk(WORKSPACE):
        dirs[:] = [d for d in dirs if d not in ignored]
        count += len(files)
    return count


def shell_quote(text: str) -> str:
    return "'" + text.replace("'", "'\"'\"'") + "'"


def preview_protocol(intent: str) -> Dict[str, Any]:
    intent = (intent or "").strip()
    if not intent:
        intent = "Finish the Completefication protocol."
    cli = f"python completefication.py {shell_quote(intent)} --provider ollama --model llama3.2"
    dry = f"python completefication.py {shell_quote(intent)} --provider ollama --model llama3.2 --dry-run"
    voice = "python voice_terminal_agent.py --provider ollama --model llama3.2 --auto-readonly"
    return {
        "ok": True,
        "intent": intent,
        "protocol": "Completefication",
        "contract": {
            "input": "normal English task",
            "planner": "LLM JSON plan",
            "mutation": "complete replacement file edits inside workspace",
            "verification": "terminal commands with bounded timeout",
            "repair": "limited LLM repair iterations",
            "report": "grounded completion report from actual outputs",
        },
        "cli": cli,
        "dry_run_cli": dry,
        "voice_agent_cli": voice,
        "stage_count": len(PROTOCOL_STAGES),
        "guardrails": [
            "no shell=True",
            "workspace path confinement",
            "forbidden command list",
            "human confirmation for mutation",
            "dry-run available",
            "grounded final report",
        ],
    }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            html_response(self)
            return
        json_response(self, {"ok": False, "error": "Not found"}, 404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        body = read_body(self)
        if parsed.path == "/api/meta":
            json_response(self, {
                "ok": True,
                "app": APP_NAME,
                "version": APP_VERSION,
                "workspace": str(WORKSPACE),
                "file_count": count_workspace_files(),
                "stages": [asdict(s) for s in PROTOCOL_STAGES],
            })
            return
        if parsed.path == "/api/read_only":
            json_response(self, run_read_only(str(body.get("name", ""))))
            return
        if parsed.path == "/api/preview":
            json_response(self, preview_protocol(str(body.get("intent", ""))))
            return
        json_response(self, {"ok": False, "error": "Unknown endpoint"}, 404)

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
