#!/usr/bin/env python3
"""
voice_terminal_agent.py

Normal-English terminal agent backed by real terminal operations.

What this is
------------
You speak or type normal English. The agent:

1. Transcribes speech or accepts typed input.
2. Sends your request plus system context to an LLM planner.
3. The LLM returns a JSON tool plan.
4. The agent shows the plan and asks for confirmation before risky actions.
5. The agent executes approved terminal operations.
6. The LLM writes a final response grounded in actual command output.
7. The terminal speaks the answer back when TTS is available.

Default mode is safe and local-first:
- local typed input fallback always works;
- Ollama is preferred if available;
- no shell=True;
- allowlisted terminal tools;
- confirmation before write/network/process/system actions;
- command timeout;
- working-directory boundary.

Run
---
    python voice_terminal_agent.py

Typed mode, no voice dependencies:
    python voice_terminal_agent.py --stt text --tts none

Use Ollama model:
    python voice_terminal_agent.py --provider ollama --model llama3.2

Allow execution without repeated confirmations for read-only commands:
    python voice_terminal_agent.py --auto-readonly

Install optional voice packages:
    pip install SpeechRecognition pyttsx3
    # Linux TTS: sudo apt install espeak-ng

Optional offline STT can be added through Vosk or Whisper later; this file keeps
those integrations pluggable without making them hard dependencies.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


APP_NAME = "VoiceTerminalAgent"
DEFAULT_MODEL = os.environ.get("VTA_MODEL", "llama3.2")
DEFAULT_PROVIDER = os.environ.get("VTA_PROVIDER", "auto")
DEFAULT_TIMEOUT = int(os.environ.get("VTA_TIMEOUT", "30"))
MAX_OUTPUT_CHARS = int(os.environ.get("VTA_MAX_OUTPUT_CHARS", "12000"))

READ_ONLY_COMMANDS = {
    "pwd", "ls", "find", "grep", "rg", "cat", "head", "tail", "wc", "du", "df",
    "git", "python", "python3", "pip", "pip3", "node", "npm", "sed", "awk",
    "date", "whoami", "uname", "env", "printenv", "which", "whereis",
}

WRITE_OR_RISKY_COMMANDS = {
    "rm", "mv", "cp", "mkdir", "touch", "chmod", "chown", "curl", "wget", "ssh", "scp",
    "git", "pip", "pip3", "npm", "node", "python", "python3", "bash", "sh", "zsh", "fish",
    "kill", "pkill", "systemctl", "sudo", "docker", "kubectl",
}

FORBIDDEN_COMMANDS = {
    "sudo", "su", "dd", "mkfs", "shutdown", "reboot", "halt", "poweroff", "passwd",
}


@dataclass
class AgentConfig:
    provider: str
    model: str
    stt: str
    tts: str
    workspace: pathlib.Path
    timeout: int
    auto_readonly: bool
    dry_run: bool
    verbose: bool


@dataclass
class ToolCall:
    tool: str
    args: Dict[str, Any]
    reason: str = ""
    risk: str = "read"


@dataclass
class ToolResult:
    tool: str
    args: Dict[str, Any]
    ok: bool
    output: str
    returncode: Optional[int] = None
    elapsed_s: float = 0.0


class LLMError(RuntimeError):
    pass


# -----------------------------------------------------------------------------
# Voice I/O
# -----------------------------------------------------------------------------


def speak(text: str, cfg: AgentConfig) -> None:
    """Speak if possible, always print."""
    print(f"\n{APP_NAME}: {text}\n")
    engine = cfg.tts.lower()
    if engine == "none":
        return

    if engine in {"auto", "espeak"}:
        try:
            subprocess.run(["espeak-ng", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            return
        except FileNotFoundError:
            if engine == "espeak":
                return

    if engine in {"auto", "say"} and platform.system() == "Darwin":
        try:
            subprocess.run(["say", text], check=False)
            return
        except FileNotFoundError:
            if engine == "say":
                return

    if engine in {"auto", "pyttsx3"}:
        try:
            import pyttsx3  # type: ignore
            tts = pyttsx3.init()
            tts.say(text)
            tts.runAndWait()
        except Exception:
            return


def listen(cfg: AgentConfig) -> str:
    """Speech-to-text with typed fallback."""
    if cfg.stt == "text":
        return input("You: ").strip()

    if cfg.stt in {"auto", "speechrecognition", "sr"}:
        try:
            import speech_recognition as sr  # type: ignore
            recognizer = sr.Recognizer()
            with sr.Microphone() as source:
                print("Listening...")
                recognizer.adjust_for_ambient_noise(source, duration=0.35)
                audio = recognizer.listen(source, timeout=8, phrase_time_limit=25)
            try:
                text = recognizer.recognize_google(audio)
                print(f"You: {text}")
                return text.strip()
            except Exception:
                try:
                    text = recognizer.recognize_sphinx(audio)
                    print(f"You: {text}")
                    return text.strip()
                except Exception:
                    print("[stt] Could not transcribe. Type instead.")
        except Exception as exc:
            if cfg.verbose:
                print(f"[stt] voice input unavailable: {exc}")

    return input("You/type: ").strip()


# -----------------------------------------------------------------------------
# LLM providers
# -----------------------------------------------------------------------------


def ollama_generate(model: str, prompt: str, *, format_json: bool = False, timeout: int = 120) -> str:
    payload: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1},
    }
    if format_json:
        payload["format"] = "json"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            obj = json.loads(resp.read().decode("utf-8"))
            return str(obj.get("response", ""))
    except urllib.error.URLError as exc:
        raise LLMError(f"Ollama unavailable: {exc}") from exc


def openai_generate(model: str, prompt: str, *, format_json: bool = False, timeout: int = 120) -> str:
    """Minimal OpenAI-compatible HTTP call. Requires OPENAI_API_KEY."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise LLMError("OPENAI_API_KEY is not set")
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
    }
    if format_json:
        payload["response_format"] = {"type": "json_object"}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            obj = json.loads(resp.read().decode("utf-8"))
            return obj["choices"][0]["message"]["content"]
    except urllib.error.URLError as exc:
        raise LLMError(f"OpenAI request failed: {exc}") from exc


def llm_generate(cfg: AgentConfig, prompt: str, *, json_mode: bool = False) -> str:
    provider = cfg.provider.lower()
    errors: List[str] = []
    if provider in {"auto", "ollama"}:
        try:
            return ollama_generate(cfg.model, prompt, format_json=json_mode)
        except Exception as exc:
            errors.append(str(exc))
            if provider == "ollama":
                raise LLMError(str(exc))
    if provider in {"auto", "openai"}:
        model = cfg.model if provider == "openai" else os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        try:
            return openai_generate(model, prompt, format_json=json_mode)
        except Exception as exc:
            errors.append(str(exc))
            if provider == "openai":
                raise LLMError(str(exc))
    raise LLMError("No LLM provider available. " + " | ".join(errors))


# -----------------------------------------------------------------------------
# Planner
# -----------------------------------------------------------------------------


PLANNER_PROMPT = """
You are a terminal operations planner. The user speaks normal English. Convert the request into a small JSON tool plan.

You may use only these tools:

1. run_command
   args: {"cmd": ["program", "arg1", "arg2"], "cwd": "optional relative path"}
   Use for terminal commands. Never use shell=True. Never output pipes, semicolons, &&, ||, backticks, or command strings.

2. read_file
   args: {"path": "relative/path"}

3. write_file
   args: {"path": "relative/path", "content": "text"}

4. list_dir
   args: {"path": "relative/path"}

5. answer_only
   args: {"text": "response when no terminal operation is needed"}

Risk labels:
- read: read-only inspection
- write: creates/updates/deletes files or changes repo state
- network: external network/API operation
- process: starts long-running service or installs packages
- system: OS-level or privileged operation

Rules:
- Prefer read-only investigation first.
- Ask for confirmation before write/network/process/system actions.
- If the user asks to edit code, first inspect relevant files unless the exact change is trivial.
- Keep plans short, usually 1-5 tool calls.
- Do not invent command outputs.
- Do not ask the user to type exact commands if you can run safe read-only commands yourself.
- Never plan sudo, su, dd, mkfs, shutdown, reboot, halt, poweroff, passwd.

Return JSON only, with this schema:
{
  "summary": "plain English plan summary",
  "needs_confirmation": true,
  "tool_calls": [
    {"tool": "list_dir", "args": {"path": "."}, "reason": "inspect project", "risk": "read"}
  ]
}

User request:
{request}

Workspace:
{workspace}
""".strip()


def extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, flags=re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def fallback_plan(request: str) -> Dict[str, Any]:
    lower = request.lower().strip()
    if lower in {"where am i", "what folder am i in", "pwd"}:
        return {"summary": "Show the current working directory.", "needs_confirmation": False, "tool_calls": [{"tool": "run_command", "args": {"cmd": ["pwd"]}, "reason": "show cwd", "risk": "read"}]}
    if "list" in lower and ("files" in lower or "directory" in lower or "folder" in lower):
        return {"summary": "List files in the workspace.", "needs_confirmation": False, "tool_calls": [{"tool": "list_dir", "args": {"path": "."}, "reason": "show files", "risk": "read"}]}
    if "git status" in lower or "status" == lower:
        return {"summary": "Check git status.", "needs_confirmation": False, "tool_calls": [{"tool": "run_command", "args": {"cmd": ["git", "status", "--short"]}, "reason": "inspect repo state", "risk": "read"}]}
    return {"summary": "Answer directly because no safe terminal plan could be inferred.", "needs_confirmation": False, "tool_calls": [{"tool": "answer_only", "args": {"text": "I need a more specific terminal task, such as listing files, checking git status, reading a file, or running tests."}, "reason": "fallback", "risk": "read"}]}


def plan_with_llm(request: str, cfg: AgentConfig) -> Dict[str, Any]:
    prompt = PLANNER_PROMPT.format(request=request, workspace=str(cfg.workspace))
    try:
        raw = llm_generate(cfg, prompt, json_mode=True)
        plan = extract_json(raw)
    except Exception as exc:
        if cfg.verbose:
            print(f"[planner] LLM planning failed: {exc}")
        plan = fallback_plan(request)

    if "tool_calls" not in plan or not isinstance(plan["tool_calls"], list):
        plan = fallback_plan(request)
    plan.setdefault("summary", "Run a terminal-backed operation.")
    plan.setdefault("needs_confirmation", True)
    return plan


# -----------------------------------------------------------------------------
# Tool execution and safety
# -----------------------------------------------------------------------------


def within_workspace(path: pathlib.Path, workspace: pathlib.Path) -> bool:
    try:
        path.resolve().relative_to(workspace.resolve())
        return True
    except ValueError:
        return False


def safe_path(raw: str, workspace: pathlib.Path) -> pathlib.Path:
    p = (workspace / raw).resolve() if not pathlib.Path(raw).is_absolute() else pathlib.Path(raw).resolve()
    if not within_workspace(p, workspace):
        raise PermissionError(f"Path escapes workspace: {raw}")
    return p


def validate_command(cmd: List[str]) -> Tuple[bool, str]:
    if not cmd or not isinstance(cmd, list):
        return False, "Command must be a non-empty list."
    program = str(cmd[0])
    base = pathlib.Path(program).name
    if base in FORBIDDEN_COMMANDS:
        return False, f"Forbidden command: {base}"
    joined = " ".join(str(x) for x in cmd)
    if any(token in joined for token in [";", "&&", "||", "`", "$(", ">", "<"]):
        return False, "Shell metacharacters are not allowed. Use structured argv only."
    if shutil.which(program) is None and not pathlib.Path(program).exists():
        return False, f"Command not found: {program}"
    return True, "ok"


def infer_command_risk(cmd: List[str]) -> str:
    if not cmd:
        return "system"
    base = pathlib.Path(str(cmd[0])).name
    if base in FORBIDDEN_COMMANDS:
        return "system"
    if base in {"curl", "wget", "ssh", "scp"}:
        return "network"
    if base in {"pip", "pip3", "npm", "docker", "kubectl", "systemctl"}:
        return "process"
    if base in {"rm", "mv", "cp", "mkdir", "touch", "chmod", "chown"}:
        return "write"
    if base == "git" and any(x in cmd for x in ["commit", "push", "pull", "merge", "rebase", "checkout", "switch", "reset", "clean", "add"]):
        return "write"
    if base in {"python", "python3", "node", "bash", "sh", "zsh"}:
        return "process"
    return "read"


def run_command(args: Dict[str, Any], cfg: AgentConfig) -> ToolResult:
    cmd = args.get("cmd")
    if not isinstance(cmd, list):
        return ToolResult("run_command", args, False, "cmd must be a JSON list", returncode=None)
    cmd = [str(x) for x in cmd]
    ok, msg = validate_command(cmd)
    if not ok:
        return ToolResult("run_command", args, False, msg, returncode=None)
    cwd_raw = str(args.get("cwd", "."))
    cwd = safe_path(cwd_raw, cfg.workspace)
    start = time.time()
    if cfg.dry_run:
        return ToolResult("run_command", args, True, f"DRY RUN: would run {shlex.join(cmd)} in {cwd}", 0, time.time() - start)
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True, timeout=cfg.timeout)
        out = ""
        if proc.stdout:
            out += proc.stdout
        if proc.stderr:
            out += "\n[stderr]\n" + proc.stderr
        out = out.strip()
        if len(out) > MAX_OUTPUT_CHARS:
            out = out[:MAX_OUTPUT_CHARS] + "\n...[truncated]"
        return ToolResult("run_command", args, proc.returncode == 0, out or "(no output)", proc.returncode, time.time() - start)
    except subprocess.TimeoutExpired as exc:
        return ToolResult("run_command", args, False, f"Command timed out after {cfg.timeout}s: {exc}", None, time.time() - start)
    except Exception as exc:
        return ToolResult("run_command", args, False, f"Command failed: {exc}", None, time.time() - start)


def read_file(args: Dict[str, Any], cfg: AgentConfig) -> ToolResult:
    path_raw = str(args.get("path", ""))
    try:
        path = safe_path(path_raw, cfg.workspace)
        if not path.is_file():
            return ToolResult("read_file", args, False, f"Not a file: {path_raw}")
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text) > MAX_OUTPUT_CHARS:
            text = text[:MAX_OUTPUT_CHARS] + "\n...[truncated]"
        return ToolResult("read_file", args, True, text)
    except Exception as exc:
        return ToolResult("read_file", args, False, str(exc))


def write_file(args: Dict[str, Any], cfg: AgentConfig) -> ToolResult:
    path_raw = str(args.get("path", ""))
    content = str(args.get("content", ""))
    try:
        path = safe_path(path_raw, cfg.workspace)
        if cfg.dry_run:
            return ToolResult("write_file", args, True, f"DRY RUN: would write {len(content)} chars to {path_raw}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return ToolResult("write_file", args, True, f"Wrote {len(content)} chars to {path_raw}")
    except Exception as exc:
        return ToolResult("write_file", args, False, str(exc))


def list_dir(args: Dict[str, Any], cfg: AgentConfig) -> ToolResult:
    path_raw = str(args.get("path", "."))
    try:
        path = safe_path(path_raw, cfg.workspace)
        if not path.is_dir():
            return ToolResult("list_dir", args, False, f"Not a directory: {path_raw}")
        rows = []
        for p in sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))[:300]:
            marker = "/" if p.is_dir() else ""
            rows.append(f"{p.name}{marker}")
        return ToolResult("list_dir", args, True, "\n".join(rows) if rows else "(empty directory)")
    except Exception as exc:
        return ToolResult("list_dir", args, False, str(exc))


def answer_only(args: Dict[str, Any], cfg: AgentConfig) -> ToolResult:
    return ToolResult("answer_only", args, True, str(args.get("text", "")))


def execute_tool(call: ToolCall, cfg: AgentConfig) -> ToolResult:
    if call.tool == "run_command":
        return run_command(call.args, cfg)
    if call.tool == "read_file":
        return read_file(call.args, cfg)
    if call.tool == "write_file":
        return write_file(call.args, cfg)
    if call.tool == "list_dir":
        return list_dir(call.args, cfg)
    if call.tool == "answer_only":
        return answer_only(call.args, cfg)
    return ToolResult(call.tool, call.args, False, f"Unknown tool: {call.tool}")


def normalize_tool_calls(plan: Dict[str, Any]) -> List[ToolCall]:
    out: List[ToolCall] = []
    for raw in plan.get("tool_calls", []):
        if not isinstance(raw, dict):
            continue
        tool = str(raw.get("tool", ""))
        args = raw.get("args", {}) if isinstance(raw.get("args", {}), dict) else {}
        reason = str(raw.get("reason", ""))
        risk = str(raw.get("risk", "read"))
        if tool == "run_command":
            inferred = infer_command_risk([str(x) for x in args.get("cmd", [])] if isinstance(args.get("cmd"), list) else [])
            if inferred != "read":
                risk = inferred
        out.append(ToolCall(tool=tool, args=args, reason=reason, risk=risk))
    return out


def needs_confirmation(calls: List[ToolCall], plan: Dict[str, Any], cfg: AgentConfig) -> bool:
    if plan.get("needs_confirmation") is True:
        if cfg.auto_readonly and all(c.risk == "read" for c in calls):
            return False
        return True
    if any(c.risk != "read" for c in calls):
        return True
    return not cfg.auto_readonly


def confirm_plan(plan: Dict[str, Any], calls: List[ToolCall], cfg: AgentConfig) -> bool:
    print("\n--- Proposed terminal-backed plan ---")
    print(plan.get("summary", ""))
    for i, call in enumerate(calls, 1):
        print(f"{i}. {call.tool} risk={call.risk} reason={call.reason}")
        print(f"   args={json.dumps(call.args, ensure_ascii=False)}")
    print("--- End plan ---\n")
    speak("I have a terminal-backed plan. Say yes to run it, or no to cancel.", cfg)
    answer = listen(cfg).lower().strip()
    return answer in {"y", "yes", "yeah", "yep", "run", "execute", "do it", "confirm", "proceed"}


# -----------------------------------------------------------------------------
# Final answer synthesis
# -----------------------------------------------------------------------------


FINAL_PROMPT = """
You are a terminal assistant. Answer the user in normal English, grounded only in the terminal results below.

User request:
{request}

Plan summary:
{summary}

Tool results JSON:
{results}

Rules:
- Be concise but useful.
- Mention what operations actually ran.
- If a command failed, explain the failure plainly.
- Do not claim anything not supported by the tool output.
- If more action is needed, state the exact next step.
""".strip()


def synthesize_final(request: str, plan: Dict[str, Any], results: List[ToolResult], cfg: AgentConfig) -> str:
    result_payload = [r.__dict__ for r in results]
    prompt = FINAL_PROMPT.format(
        request=request,
        summary=plan.get("summary", ""),
        results=json.dumps(result_payload, indent=2, ensure_ascii=False),
    )
    try:
        return llm_generate(cfg, prompt, json_mode=False).strip()
    except Exception:
        # Grounded non-LLM fallback.
        ok_count = sum(1 for r in results if r.ok)
        fail_count = len(results) - ok_count
        lines = [f"Ran {len(results)} operation(s): {ok_count} succeeded, {fail_count} failed."]
        for r in results:
            status = "OK" if r.ok else "FAILED"
            lines.append(f"- {r.tool}: {status}. {r.output[:500]}")
        return "\n".join(lines)


# -----------------------------------------------------------------------------
# Main loop
# -----------------------------------------------------------------------------


def handle_request(request: str, cfg: AgentConfig) -> None:
    plan = plan_with_llm(request, cfg)
    calls = normalize_tool_calls(plan)
    if not calls:
        speak("I could not create a valid terminal plan from that request.", cfg)
        return

    if needs_confirmation(calls, plan, cfg):
        if not confirm_plan(plan, calls, cfg):
            speak("Cancelled. No terminal operations were executed.", cfg)
            return

    results: List[ToolResult] = []
    for call in calls:
        result = execute_tool(call, cfg)
        results.append(result)
        if cfg.verbose:
            print(f"\n[{call.tool}] ok={result.ok} rc={result.returncode} elapsed={result.elapsed_s:.2f}s")
            print(result.output)

    final = synthesize_final(request, plan, results, cfg)
    speak(final, cfg)


def loop(cfg: AgentConfig) -> None:
    cfg.workspace.mkdir(parents=True, exist_ok=True)
    speak(
        "Normal-English terminal agent is ready. Speak naturally. I will plan terminal operations, ask for confirmation when needed, run them, and answer from the results.",
        cfg,
    )
    while True:
        try:
            request = listen(cfg)
        except (KeyboardInterrupt, EOFError):
            speak("Stopping terminal agent.", cfg)
            return
        if not request:
            continue
        lower = request.lower().strip()
        if lower in {"quit", "exit", "stop", "goodbye"}:
            speak("Stopping terminal agent.", cfg)
            return
        if lower in {"help", "what can you do"}:
            speak(
                "Try: list the files, check git status, read the README, run the tests, explain this repository, or create a file with a summary.",
                cfg,
            )
            continue
        handle_request(request, cfg)


def parse_args(argv: Optional[List[str]] = None) -> AgentConfig:
    parser = argparse.ArgumentParser(description="Normal-English voice terminal agent backed by terminal operations")
    parser.add_argument("--provider", default=DEFAULT_PROVIDER, choices=["auto", "ollama", "openai", "none"], help="LLM provider")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="LLM model name")
    parser.add_argument("--stt", default="auto", choices=["auto", "speechrecognition", "sr", "text"], help="speech-to-text backend")
    parser.add_argument("--tts", default="auto", choices=["auto", "none", "espeak", "say", "pyttsx3"], help="text-to-speech backend")
    parser.add_argument("--workspace", default=".", help="workspace root; file operations cannot escape this directory")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="command timeout seconds")
    parser.add_argument("--auto-readonly", action="store_true", help="do not ask confirmation for read-only plans")
    parser.add_argument("--dry-run", action="store_true", help="show what would run without changing anything")
    parser.add_argument("--verbose", action="store_true", help="print full operation outputs")
    args = parser.parse_args(argv)
    return AgentConfig(
        provider=args.provider,
        model=args.model,
        stt=args.stt,
        tts=args.tts,
        workspace=pathlib.Path(args.workspace).resolve(),
        timeout=args.timeout,
        auto_readonly=args.auto_readonly,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    config = parse_args()
    if config.provider == "none":
        print("[warning] provider=none uses simple fallback planning and non-LLM final summaries.")
    loop(config)
