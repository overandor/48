#!/usr/bin/env python3
"""
completefication.py

One-command LLM-based programming in the terminal.

Concept
-------
Completefication means: from one normal-English command, the terminal becomes a
bounded programming operator that can inspect a repository, plan a change, edit
files, run checks, repair failures, and produce a completion report backed by
actual terminal operations.

Example
-------
    python completefication.py "add voice mode to semantic_protocol_runtime.py"

Safer dry run:
    python completefication.py "add a README section explaining voice mode" --dry-run

Use Ollama:
    python completefication.py "write tests for the parser" --provider ollama --model llama3.2

Use OpenAI-compatible API:
    OPENAI_API_KEY=... python completefication.py "fix the failing tests" --provider openai --model gpt-4o-mini

What it does
------------
1. Inspects the repo with real terminal operations.
2. Asks an LLM for an implementation plan and file patches.
3. Applies only structured file writes inside the workspace.
4. Runs checks/tests.
5. If checks fail, asks the LLM for a repair patch and tries again.
6. Prints a completion report grounded in command output.

Safety model
------------
- No shell=True.
- File writes are confined to the workspace.
- Dangerous commands are blocked.
- Default checks are read/test oriented.
- Use --dry-run to preview writes and commands.

This is intentionally a single-file prototype. It is designed to complement
voice_terminal_agent.py and semantic_protocol_runtime.py.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_PROVIDER = os.environ.get("COMPLETE_PROVIDER", "auto")
DEFAULT_MODEL = os.environ.get("COMPLETE_MODEL", "llama3.2")
DEFAULT_TIMEOUT = int(os.environ.get("COMPLETE_TIMEOUT", "60"))
MAX_FILE_CHARS = int(os.environ.get("COMPLETE_MAX_FILE_CHARS", "18000"))
MAX_TOTAL_CONTEXT_CHARS = int(os.environ.get("COMPLETE_MAX_CONTEXT_CHARS", "70000"))
MAX_OUTPUT_CHARS = int(os.environ.get("COMPLETE_MAX_OUTPUT_CHARS", "16000"))

FORBIDDEN_COMMANDS = {
    "sudo", "su", "dd", "mkfs", "shutdown", "reboot", "halt", "poweroff", "passwd",
}

DEFAULT_IGNORE_DIRS = {
    ".git", "__pycache__", ".pytest_cache", ".mypy_cache", "node_modules", "dist", "build",
    ".venv", "venv", "env", ".next", ".turbo", ".cache",
}

TEXT_SUFFIXES = {
    ".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".sh",
    ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".sql", ".spr", ".gitignore",
}


@dataclass
class Config:
    task: str
    workspace: pathlib.Path
    provider: str
    model: str
    timeout: int
    max_iterations: int
    dry_run: bool
    verbose: bool
    auto_confirm: bool


@dataclass
class CommandResult:
    cmd: List[str]
    ok: bool
    output: str
    returncode: Optional[int]
    elapsed_s: float


@dataclass
class FileEdit:
    path: str
    content: str
    reason: str = ""


class LLMError(RuntimeError):
    pass


# -----------------------------------------------------------------------------
# LLM providers
# -----------------------------------------------------------------------------


def ollama_generate(model: str, prompt: str, *, json_mode: bool, timeout: int = 180) -> str:
    payload: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1},
    }
    if json_mode:
        payload["format"] = "json"
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return str(json.loads(resp.read().decode("utf-8")).get("response", ""))
    except urllib.error.URLError as exc:
        raise LLMError(f"Ollama unavailable: {exc}") from exc


def openai_generate(model: str, prompt: str, *, json_mode: bool, timeout: int = 180) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise LLMError("OPENAI_API_KEY is not set")
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
    except urllib.error.URLError as exc:
        raise LLMError(f"OpenAI request failed: {exc}") from exc


def llm_generate(cfg: Config, prompt: str, *, json_mode: bool = False) -> str:
    errors: List[str] = []
    if cfg.provider in {"auto", "ollama"}:
        try:
            return ollama_generate(cfg.model, prompt, json_mode=json_mode)
        except Exception as exc:
            errors.append(str(exc))
            if cfg.provider == "ollama":
                raise
    if cfg.provider in {"auto", "openai"}:
        model = cfg.model if cfg.provider == "openai" else os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        try:
            return openai_generate(model, prompt, json_mode=json_mode)
        except Exception as exc:
            errors.append(str(exc))
            if cfg.provider == "openai":
                raise
    raise LLMError("No LLM provider available. " + " | ".join(errors))


def extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise
        return json.loads(match.group(0))


# -----------------------------------------------------------------------------
# Workspace / terminal operations
# -----------------------------------------------------------------------------


def within_workspace(path: pathlib.Path, workspace: pathlib.Path) -> bool:
    try:
        path.resolve().relative_to(workspace.resolve())
        return True
    except ValueError:
        return False


def safe_path(raw: str, workspace: pathlib.Path) -> pathlib.Path:
    path = pathlib.Path(raw)
    resolved = (workspace / path).resolve() if not path.is_absolute() else path.resolve()
    if not within_workspace(resolved, workspace):
        raise PermissionError(f"Path escapes workspace: {raw}")
    return resolved


def is_text_file(path: pathlib.Path) -> bool:
    if path.name in {"README", "LICENSE", "Makefile", "Dockerfile"}:
        return True
    return path.suffix.lower() in TEXT_SUFFIXES


def list_files(workspace: pathlib.Path, limit: int = 300) -> List[str]:
    files: List[str] = []
    for root, dirs, names in os.walk(workspace):
        root_path = pathlib.Path(root)
        dirs[:] = [d for d in dirs if d not in DEFAULT_IGNORE_DIRS]
        for name in names:
            p = root_path / name
            if not is_text_file(p):
                continue
            rel = str(p.relative_to(workspace))
            files.append(rel)
            if len(files) >= limit:
                return sorted(files)
    return sorted(files)


def read_file_for_context(workspace: pathlib.Path, rel: str) -> str:
    path = safe_path(rel, workspace)
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    if len(text) > MAX_FILE_CHARS:
        text = text[:MAX_FILE_CHARS] + "\n...[truncated]"
    return text


def validate_command(cmd: List[str]) -> Tuple[bool, str]:
    if not cmd or not isinstance(cmd, list):
        return False, "command must be a non-empty list"
    base = pathlib.Path(str(cmd[0])).name
    if base in FORBIDDEN_COMMANDS:
        return False, f"forbidden command: {base}"
    joined = " ".join(str(x) for x in cmd)
    if any(token in joined for token in [";", "&&", "||", "`", "$(", ">", "<"]):
        return False, "shell metacharacters are blocked; use argv only"
    if shutil.which(str(cmd[0])) is None and not pathlib.Path(str(cmd[0])).exists():
        return False, f"command not found: {cmd[0]}"
    return True, "ok"


def run_command(cmd: List[str], cfg: Config) -> CommandResult:
    ok, msg = validate_command(cmd)
    start = time.time()
    if not ok:
        return CommandResult(cmd, False, msg, None, time.time() - start)
    if cfg.dry_run:
        return CommandResult(cmd, True, "DRY RUN: would run " + " ".join(cmd), 0, time.time() - start)
    try:
        proc = subprocess.run(cmd, cwd=str(cfg.workspace), text=True, capture_output=True, timeout=cfg.timeout)
        output = ""
        if proc.stdout:
            output += proc.stdout
        if proc.stderr:
            output += "\n[stderr]\n" + proc.stderr
        output = output.strip() or "(no output)"
        if len(output) > MAX_OUTPUT_CHARS:
            output = output[:MAX_OUTPUT_CHARS] + "\n...[truncated]"
        return CommandResult(cmd, proc.returncode == 0, output, proc.returncode, time.time() - start)
    except subprocess.TimeoutExpired as exc:
        return CommandResult(cmd, False, f"timeout after {cfg.timeout}s: {exc}", None, time.time() - start)
    except Exception as exc:
        return CommandResult(cmd, False, f"command failed: {exc}", None, time.time() - start)


def detect_check_commands(workspace: pathlib.Path) -> List[List[str]]:
    commands: List[List[str]] = []
    if (workspace / "pyproject.toml").exists() or (workspace / "pytest.ini").exists() or (workspace / "tests").exists():
        if shutil.which("python"):
            commands.append(["python", "-m", "pytest", "-q"])
    if (workspace / "package.json").exists() and shutil.which("npm"):
        commands.append(["npm", "test", "--", "--runInBand"])
    if (workspace / "semantic_protocol_runtime.py").exists() and shutil.which("python"):
        commands.append(["python", "semantic_protocol_runtime.py", "--help"])
    if (workspace / "completefication.py").exists() and shutil.which("python"):
        commands.append(["python", "completefication.py", "--help"])
    return commands or [["python", "--version"]]


def inspect_repo(cfg: Config) -> Dict[str, Any]:
    file_list = list_files(cfg.workspace)
    command_results = []
    for cmd in [["git", "status", "--short"], ["git", "branch", "--show-current"]]:
        if shutil.which(cmd[0]):
            r = run_command(cmd, cfg)
            command_results.append(r.__dict__)
    priority_files = []
    for candidate in ["README.md", "pyproject.toml", "requirements.txt", "package.json", "semantic_protocol_runtime.py", "voice_terminal_agent.py"]:
        if candidate in file_list:
            priority_files.append({"path": candidate, "content": read_file_for_context(cfg.workspace, candidate)})
    context = {
        "workspace": str(cfg.workspace),
        "files": file_list,
        "priority_files": priority_files,
        "commands": command_results,
    }
    raw = json.dumps(context, ensure_ascii=False)
    if len(raw) > MAX_TOTAL_CONTEXT_CHARS:
        context["priority_files"] = priority_files[:3]
        context["truncated"] = True
    return context


# -----------------------------------------------------------------------------
# LLM patch planning
# -----------------------------------------------------------------------------


IMPLEMENT_PROMPT = """
You are a senior software engineer operating a terminal-native coding agent called Completefication.

User task:
{task}

Repository context JSON:
{context}

Return JSON only with this schema:
{{
  "summary": "what you will implement",
  "edits": [
    {{"path": "relative/file.py", "content": "complete replacement file content", "reason": "why"}}
  ],
  "commands": [
    ["python", "completefication.py", "--help"]
  ],
  "notes": ["short implementation note"]
}}

Rules:
- Write complete replacement contents for every edited file.
- Keep edits inside the repository.
- Do not use shell metacharacters.
- Prefer single-file, runnable, dependency-light implementations.
- Include tests or docs when useful.
- Commands must be argv arrays, not shell strings.
- Never use sudo, su, dd, mkfs, shutdown, reboot, halt, poweroff, passwd.
- If the task is ambiguous, make the smallest useful implementation.
""".strip()


REPAIR_PROMPT = """
You are repairing an implementation produced by Completefication.

User task:
{task}

Repository context JSON:
{context}

Previous implementation JSON:
{plan}

Check results JSON:
{results}

Return JSON only with this schema:
{{
  "summary": "repair summary",
  "edits": [
    {{"path": "relative/file.py", "content": "complete replacement file content", "reason": "why"}}
  ],
  "commands": [
    ["python", "completefication.py", "--help"]
  ],
  "notes": ["short repair note"]
}}

Rules:
- Only change files needed to fix the failure.
- Write complete replacement contents for every edited file.
- Keep edits inside the repository.
- Commands must be argv arrays.
""".strip()


def plan_implementation(cfg: Config, context: Dict[str, Any]) -> Dict[str, Any]:
    prompt = IMPLEMENT_PROMPT.format(task=cfg.task, context=json.dumps(context, ensure_ascii=False, indent=2))
    raw = llm_generate(cfg, prompt, json_mode=True)
    plan = extract_json(raw)
    plan.setdefault("summary", "Implement requested change")
    plan.setdefault("edits", [])
    plan.setdefault("commands", [])
    plan.setdefault("notes", [])
    return plan


def plan_repair(cfg: Config, context: Dict[str, Any], plan: Dict[str, Any], results: List[CommandResult]) -> Dict[str, Any]:
    prompt = REPAIR_PROMPT.format(
        task=cfg.task,
        context=json.dumps(context, ensure_ascii=False, indent=2),
        plan=json.dumps(plan, ensure_ascii=False, indent=2),
        results=json.dumps([r.__dict__ for r in results], ensure_ascii=False, indent=2),
    )
    raw = llm_generate(cfg, prompt, json_mode=True)
    repair = extract_json(raw)
    repair.setdefault("summary", "Repair implementation")
    repair.setdefault("edits", [])
    repair.setdefault("commands", [])
    repair.setdefault("notes", [])
    return repair


# -----------------------------------------------------------------------------
# Apply edits / run checks
# -----------------------------------------------------------------------------


def normalize_edits(plan: Dict[str, Any]) -> List[FileEdit]:
    edits: List[FileEdit] = []
    for raw in plan.get("edits", []):
        if not isinstance(raw, dict):
            continue
        path = str(raw.get("path", "")).strip()
        content = raw.get("content", "")
        reason = str(raw.get("reason", ""))
        if not path:
            continue
        edits.append(FileEdit(path=path, content=str(content), reason=reason))
    return edits


def apply_edits(edits: List[FileEdit], cfg: Config) -> List[str]:
    messages: List[str] = []
    for edit in edits:
        path = safe_path(edit.path, cfg.workspace)
        rel = str(path.relative_to(cfg.workspace))
        if cfg.dry_run:
            messages.append(f"DRY RUN: would write {len(edit.content)} chars to {rel} — {edit.reason}")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(edit.content, encoding="utf-8")
        messages.append(f"wrote {len(edit.content)} chars to {rel} — {edit.reason}")
    return messages


def commands_from_plan(plan: Dict[str, Any], cfg: Config) -> List[List[str]]:
    out: List[List[str]] = []
    for raw in plan.get("commands", []):
        if isinstance(raw, list) and raw and all(isinstance(x, (str, int, float)) for x in raw):
            out.append([str(x) for x in raw])
    if not out:
        out = detect_check_commands(cfg.workspace)
    return out[:8]


def run_checks(commands: List[List[str]], cfg: Config) -> List[CommandResult]:
    results: List[CommandResult] = []
    for cmd in commands:
        results.append(run_command(cmd, cfg))
    return results


def all_ok(results: List[CommandResult]) -> bool:
    return bool(results) and all(r.ok for r in results)


# -----------------------------------------------------------------------------
# Reporting
# -----------------------------------------------------------------------------


REPORT_PROMPT = """
You are writing a grounded completion report for a terminal coding agent.

User task:
{task}

Implementation plan JSON:
{plan}

Applied edit messages:
{edits}

Check results JSON:
{results}

Return a concise Markdown report with:
- what changed;
- files edited;
- checks run and outcomes;
- exact command to use next;
- any limitations.

Do not claim success unless the check results support it.
""".strip()


def final_report(cfg: Config, plan: Dict[str, Any], edit_messages: List[str], results: List[CommandResult]) -> str:
    prompt = REPORT_PROMPT.format(
        task=cfg.task,
        plan=json.dumps(plan, ensure_ascii=False, indent=2),
        edits=json.dumps(edit_messages, ensure_ascii=False, indent=2),
        results=json.dumps([r.__dict__ for r in results], ensure_ascii=False, indent=2),
    )
    try:
        return llm_generate(cfg, prompt, json_mode=False).strip()
    except Exception:
        status = "PASS" if all_ok(results) else "CHECKS FAILED"
        lines = [f"# Completefication Report — {status}", "", f"Task: {cfg.task}", "", "## Edits"]
        lines += [f"- {m}" for m in edit_messages] or ["- No edits applied"]
        lines += ["", "## Checks"]
        for r in results:
            lines.append(f"- {' '.join(r.cmd)}: {'OK' if r.ok else 'FAILED'}")
            lines.append(f"  {r.output[:500]}")
        return "\n".join(lines)


# -----------------------------------------------------------------------------
# Confirmation / main
# -----------------------------------------------------------------------------


def confirm(plan: Dict[str, Any], edits: List[FileEdit], commands: List[List[str]], cfg: Config) -> bool:
    if cfg.auto_confirm:
        return True
    print("\n--- Completefication Plan ---")
    print(plan.get("summary", ""))
    print("\nEdits:")
    for e in edits:
        print(f"- {e.path}: {e.reason} ({len(e.content)} chars)")
    print("\nCommands:")
    for c in commands:
        print("- " + " ".join(c))
    print("--- End Plan ---")
    answer = input("Apply this plan? [y/N] ").strip().lower()
    return answer in {"y", "yes"}


def run_completefication(cfg: Config) -> int:
    cfg.workspace = cfg.workspace.resolve()
    print(f"[completefication] workspace: {cfg.workspace}")
    print(f"[completefication] task: {cfg.task}")

    context = inspect_repo(cfg)
    try:
        plan = plan_implementation(cfg, context)
    except Exception as exc:
        print(f"LLM planning failed: {exc}", file=sys.stderr)
        return 2

    edits = normalize_edits(plan)
    commands = commands_from_plan(plan, cfg)
    if not edits and not commands:
        print("No edits or commands were produced.", file=sys.stderr)
        return 3

    if not confirm(plan, edits, commands, cfg):
        print("Cancelled.")
        return 0

    edit_messages = apply_edits(edits, cfg)
    for m in edit_messages:
        print(f"[edit] {m}")

    results = run_checks(commands, cfg)
    for r in results:
        status = "OK" if r.ok else "FAIL"
        print(f"[check:{status}] {' '.join(r.cmd)}")
        if cfg.verbose or not r.ok:
            print(r.output)

    iteration = 0
    while not all_ok(results) and iteration < cfg.max_iterations:
        iteration += 1
        print(f"[repair] iteration {iteration}/{cfg.max_iterations}")
        context = inspect_repo(cfg)
        try:
            repair = plan_repair(cfg, context, plan, results)
        except Exception as exc:
            print(f"Repair planning failed: {exc}", file=sys.stderr)
            break
        repair_edits = normalize_edits(repair)
        repair_commands = commands_from_plan(repair, cfg)
        if not repair_edits and not repair_commands:
            print("Repair produced no edits or commands.", file=sys.stderr)
            break
        if not confirm(repair, repair_edits, repair_commands, cfg):
            print("Repair cancelled.")
            break
        edit_messages.extend(apply_edits(repair_edits, cfg))
        plan = repair
        results = run_checks(repair_commands, cfg)
        for r in results:
            status = "OK" if r.ok else "FAIL"
            print(f"[check:{status}] {' '.join(r.cmd)}")
            if cfg.verbose or not r.ok:
                print(r.output)

    report = final_report(cfg, plan, edit_messages, results)
    print("\n" + report + "\n")
    return 0 if all_ok(results) else 1


def parse_args(argv: Optional[List[str]] = None) -> Config:
    parser = argparse.ArgumentParser(description="One-command LLM programming completefication loop")
    parser.add_argument("task", nargs="?", help="Normal-English programming task")
    parser.add_argument("--workspace", default=".", help="Repo/workspace root")
    parser.add_argument("--provider", default=DEFAULT_PROVIDER, choices=["auto", "ollama", "openai"], help="LLM provider")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model name")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Command timeout seconds")
    parser.add_argument("--max-iterations", type=int, default=2, help="Repair iterations after failed checks")
    parser.add_argument("--dry-run", action="store_true", help="Preview writes and commands without changing files")
    parser.add_argument("--yes", action="store_true", help="Apply generated plan without interactive confirmation")
    parser.add_argument("--verbose", action="store_true", help="Print detailed check output")
    args = parser.parse_args(argv)
    task = args.task or input("Completefication task: ").strip()
    if not task:
        parser.error("task is required")
    return Config(
        task=task,
        workspace=pathlib.Path(args.workspace),
        provider=args.provider,
        model=args.model,
        timeout=args.timeout,
        max_iterations=max(0, args.max_iterations),
        dry_run=args.dry_run,
        verbose=args.verbose,
        auto_confirm=args.yes,
    )


if __name__ == "__main__":
    raise SystemExit(run_completefication(parse_args()))
