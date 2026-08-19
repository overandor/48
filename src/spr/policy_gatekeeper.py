"""Production policy gatekeeper for Semantic Protocol Runtime.

The gatekeeper is a boring, inspectable execution firewall. It validates paths,
commands, prompt text, and effect targets before any runtime or agent executes.
It deliberately supports a small JSON policy format to avoid new dependencies.

Example policy file:

{
  "allow": {
    "read_paths": ["**/*.py", "examples/**", "docs/**"],
    "write_paths": ["out/**", ".spr_runs/**"],
    "commands": [["python", "-m", "pytest", "-q"], ["spr", "--help"]],
    "network": []
  },
  "deny": {
    "paths": [".env", "secrets/**"],
    "commands": ["sudo", "rm", "dd", "mkfs", "shutdown", "reboot"],
    "prompt_terms": ["private key", "password", "secret"]
  },
  "approval_required": ["write", "network", "process", "system"]
}
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import pathlib
from dataclasses import dataclass, field, asdict
from typing import Any

from .errors import SPRPolicyError


DEFAULT_DENIED_COMMANDS = [
    "sudo",
    "su",
    "dd",
    "mkfs",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    "passwd",
]

DEFAULT_DENIED_PATHS = [".env", ".env.*", "secrets/**", "**/id_rsa", "**/id_ed25519"]
DEFAULT_DENIED_PROMPT_TERMS = ["private key", "password", "secret key", "api key"]


@dataclass
class GateDecision:
    ok: bool
    operation: str
    subject: str
    reason: str
    approval_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GatePolicy:
    allow_read_paths: list[str] = field(default_factory=lambda: ["**/*"])
    allow_write_paths: list[str] = field(default_factory=lambda: ["out/**", ".spr_runs/**"])
    allow_commands: list[list[str]] = field(default_factory=list)
    allow_network: list[str] = field(default_factory=list)
    deny_paths: list[str] = field(default_factory=lambda: DEFAULT_DENIED_PATHS.copy())
    deny_commands: list[str] = field(default_factory=lambda: DEFAULT_DENIED_COMMANDS.copy())
    deny_prompt_terms: list[str] = field(default_factory=lambda: DEFAULT_DENIED_PROMPT_TERMS.copy())
    approval_required: list[str] = field(default_factory=lambda: ["write", "network", "process", "system"])

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GatePolicy":
        allow = data.get("allow", {}) if isinstance(data.get("allow", {}), dict) else {}
        deny = data.get("deny", {}) if isinstance(data.get("deny", {}), dict) else {}
        return cls(
            allow_read_paths=list(allow.get("read_paths", ["**/*"])),
            allow_write_paths=list(allow.get("write_paths", ["out/**", ".spr_runs/**"])),
            allow_commands=[list(cmd) for cmd in allow.get("commands", [])],
            allow_network=list(allow.get("network", [])),
            deny_paths=list(deny.get("paths", DEFAULT_DENIED_PATHS)),
            deny_commands=list(deny.get("commands", DEFAULT_DENIED_COMMANDS)),
            deny_prompt_terms=list(deny.get("prompt_terms", DEFAULT_DENIED_PROMPT_TERMS)),
            approval_required=list(data.get("approval_required", ["write", "network", "process", "system"])),
        )

    @classmethod
    def load(cls, path: str | pathlib.Path) -> "GatePolicy":
        p = pathlib.Path(path)
        return cls.from_dict(json.loads(p.read_text(encoding="utf-8")))


def match_any(path: str, patterns: list[str]) -> bool:
    normalized = path.replace("\\", "/")
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in patterns)


def command_matches(command: list[str], allowed: list[list[str]]) -> bool:
    if not allowed:
        return False
    for candidate in allowed:
        if command[: len(candidate)] == candidate:
            return True
    return False


class PolicyGatekeeper:
    def __init__(self, policy: GatePolicy | None = None):
        self.policy = policy or GatePolicy()

    def check_read_path(self, path: str) -> GateDecision:
        if match_any(path, self.policy.deny_paths):
            return GateDecision(False, "read", path, "path is denied")
        if not match_any(path, self.policy.allow_read_paths):
            return GateDecision(False, "read", path, "path is not in allowed read scope")
        return GateDecision(True, "read", path, "read allowed")

    def check_write_path(self, path: str) -> GateDecision:
        if match_any(path, self.policy.deny_paths):
            return GateDecision(False, "write", path, "path is denied")
        if not match_any(path, self.policy.allow_write_paths):
            return GateDecision(False, "write", path, "path is not in allowed write scope")
        return GateDecision(True, "write", path, "write allowed", "write" in self.policy.approval_required)

    def check_command(self, command: list[str]) -> GateDecision:
        if not command:
            return GateDecision(False, "command", "", "empty command")
        program = pathlib.Path(str(command[0])).name
        if program in self.policy.deny_commands:
            return GateDecision(False, "command", " ".join(command), f"command is denied: {program}")
        if command_matches([str(x) for x in command], self.policy.allow_commands):
            return GateDecision(True, "command", " ".join(command), "command allowed")
        return GateDecision(False, "command", " ".join(command), "command is not allowlisted")

    def check_network(self, target: str) -> GateDecision:
        if target in self.policy.allow_network or "*" in self.policy.allow_network:
            return GateDecision(True, "network", target, "network target allowed", "network" in self.policy.approval_required)
        return GateDecision(False, "network", target, "network target is not allowlisted")

    def check_prompt(self, text: str) -> GateDecision:
        lower = text.lower()
        for term in self.policy.deny_prompt_terms:
            if term.lower() in lower:
                return GateDecision(False, "prompt", term, "prompt contains denied sensitive term")
        return GateDecision(True, "prompt", "prompt", "prompt allowed")

    def require(self, decision: GateDecision) -> None:
        if not decision.ok:
            raise SPRPolicyError(decision.reason, hint=f"Operation={decision.operation}, subject={decision.subject}")


def default_policy_json() -> str:
    return json.dumps(
        {
            "allow": {
                "read_paths": ["**/*.py", "**/*.md", "examples/**", "docs/**", "tests/**", "pyproject.toml"],
                "write_paths": ["out/**", ".spr_runs/**", "build/**"],
                "commands": [["python", "-m", "pytest", "-q"], ["python", "semantic_protocol_runtime.py", "--help"], ["spr", "--help"]],
                "network": [],
            },
            "deny": {
                "paths": DEFAULT_DENIED_PATHS,
                "commands": DEFAULT_DENIED_COMMANDS,
                "prompt_terms": DEFAULT_DENIED_PROMPT_TERMS,
            },
            "approval_required": ["write", "network", "process", "system"],
        },
        indent=2,
        sort_keys=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SPR production policy gatekeeper")
    parser.add_argument("--policy", help="JSON policy file")
    parser.add_argument("--write-default", help="write a default JSON policy to this path")
    parser.add_argument("--check-read")
    parser.add_argument("--check-write")
    parser.add_argument("--check-command", nargs="+")
    parser.add_argument("--check-prompt")
    args = parser.parse_args(argv)

    if args.write_default:
        pathlib.Path(args.write_default).write_text(default_policy_json() + "\n", encoding="utf-8")
        print(f"Wrote default policy: {args.write_default}")
        return 0

    policy = GatePolicy.load(args.policy) if args.policy else GatePolicy()
    gate = PolicyGatekeeper(policy)
    decisions: list[GateDecision] = []
    if args.check_read:
        decisions.append(gate.check_read_path(args.check_read))
    if args.check_write:
        decisions.append(gate.check_write_path(args.check_write))
    if args.check_command:
        decisions.append(gate.check_command(args.check_command))
    if args.check_prompt:
        decisions.append(gate.check_prompt(args.check_prompt))

    if not decisions:
        print(default_policy_json())
        return 0

    print(json.dumps([d.to_dict() for d in decisions], indent=2, sort_keys=True))
    return 0 if all(d.ok for d in decisions) else 2


if __name__ == "__main__":
    raise SystemExit(main())
