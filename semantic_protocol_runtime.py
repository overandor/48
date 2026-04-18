#!/usr/bin/env python3
"""
semantic_protocol_runtime.py

A single-file prototype for a semantic protocol programming system.

What it does
------------
- Parses a small terminal-native semantic protocol language.
- Builds a typed-ish IR with values, transforms, effects, policies, and runtime hints.
- Plans execution across multiple targets (Python, SQL, HTTP).
- Supports explicit effect markers and capability policies.
- Provides an "autogen-style" bounded planning loop.
- Uses local Hugging Face Transformers by default for LLM assistance.
- Keeps remote providers disabled by default. No API key required to run locally.

This is a prototype, not a production compiler. The design goal is:
    meaning first, lowering second.

Example protocol
----------------
policy {
  optimize: latency > cost
  deterministic: true
  allow network[api.main, slack.ops]
  allow database[db.main]
  deny shell[*]
}

users := source @db.main "select id, email, score from users"
hot   := users -> filter score > 0.8 -> project [id, email, score]
write! hot @file:"hot_users.jsonl"
notify! hot @slack.ops:"#risk"

Usage
-----
python semantic_protocol_runtime.py explain examples/demo.spr
python semantic_protocol_runtime.py compile examples/demo.spr --out build/
python semantic_protocol_runtime.py run examples/demo.spr --dry-run
python semantic_protocol_runtime.py repl

Optional local LLM (Transformers)
---------------------------------
Set a local HF model:
    export SPR_HF_MODEL=Qwen/Qwen2.5-1.5B-Instruct

The LLM is used only for bounded suggestions:
- runtime ranking among already legal targets
- optional explanation text
- optional fill-in for unresolved metadata

The planner remains deterministic-first and policy-constrained.
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import os
import pathlib
import re
import shlex
import sqlite3
import sys
import textwrap
import traceback
from typing import Any, Dict, List, Optional, Tuple, Union


APP_NAME = "spr"
APP_VERSION = "0.1.0"
DEFAULT_BUILD_DIR = "build"


def eprint(*args: Any, **kwargs: Any) -> None:
    print(*args, file=sys.stderr, **kwargs)


def ensure_dir(path: Union[str, pathlib.Path]) -> pathlib.Path:
    p = pathlib.Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def load_text_file(path: Union[str, pathlib.Path]) -> str:
    return pathlib.Path(path).read_text(encoding="utf-8")


def dump_text_file(path: Union[str, pathlib.Path], content: str) -> None:
    pathlib.Path(path).write_text(content, encoding="utf-8")


def split_csv_like(inner: str) -> List[str]:
    if not inner.strip():
        return []
    parts: List[str] = []
    current: List[str] = []
    depth = 0
    quote: Optional[str] = None
    for ch in inner:
        if quote:
            current.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in ("'", '"'):
            quote = ch
            current.append(ch)
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current).strip())
    return parts


def pretty(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False, default=str)


class SPRRuntimeError(Exception):
    pass


class ParseError(SPRRuntimeError):
    pass


class PolicyError(SPRRuntimeError):
    pass


class PlanningError(SPRRuntimeError):
    pass


class VerificationError(SPRRuntimeError):
    pass


class CapabilityKind(str, Enum):
    NETWORK = "network"
    DATABASE = "database"
    FILESYSTEM = "filesystem"
    SHELL = "shell"
    PYTHON = "python"
    HTTP = "http"
    LLM = "llm"


@dataclass
class AllowDenyRule:
    allow: bool
    kind: CapabilityKind
    subjects: List[str]

    def matches(self, subject: str) -> bool:
        for s in self.subjects:
            if s == "*" or s == subject:
                return True
        return False


@dataclass
class Policy:
    optimize_left: str = "latency"
    optimize_right: str = "cost"
    deterministic: bool = True
    retries: int = 0
    rules: List[AllowDenyRule] = field(default_factory=list)
    custom: Dict[str, Any] = field(default_factory=dict)

    def is_allowed(self, kind: CapabilityKind, subject: str) -> bool:
        explicit: Optional[bool] = None
        for rule in self.rules:
            if rule.kind == kind and rule.matches(subject):
                explicit = rule.allow
        if explicit is not None:
            return explicit
        if kind in {CapabilityKind.SHELL, CapabilityKind.NETWORK, CapabilityKind.HTTP, CapabilityKind.LLM}:
            return False
        return True

    def require(self, kind: CapabilityKind, subject: str) -> None:
        if not self.is_allowed(kind, subject):
            raise PolicyError(f"Policy denied {kind.value}[{subject}]")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "optimize_left": self.optimize_left,
            "optimize_right": self.optimize_right,
            "deterministic": self.deterministic,
            "retries": self.retries,
            "rules": [dataclasses.asdict(r) for r in self.rules],
            "custom": self.custom,
        }


@dataclass
class SourceSpec:
    runtime: str
    payload: str


@dataclass
class RuntimeBinding:
    kind: str
    target: str


@dataclass
class TypeRef:
    raw: str
    base: str = "any"
    params: List[TypeRef] = field(default_factory=list)

    @classmethod
    def from_string(cls, text: str) -> TypeRef:
        text = text.strip()
        if "[" in text and text.endswith("]"):
            base = text[:text.find("[")]
            inner = text[text.find("[")+1:-1]
            params = [cls.from_string(p) for p in split_csv_like(inner)]
            return cls(raw=text, base=base, params=params)
        return cls(raw=text, base=text)


@dataclass
class TransformOp:
    name: str
    args: Dict[str, Any] = field(default_factory=dict)
    runtime_hint: Optional[str] = None
    approximate: bool = False
    planner_hints: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "args": self.args,
            "runtime_hint": self.runtime_hint,
            "approximate": self.approximate,
            "planner_hints": self.planner_hints,
        }


@dataclass
class Binding:
    name: str
    source: Optional[SourceSpec] = None
    input_name: Optional[str] = None
    declared_type: Optional[TypeRef] = None
    ops: List[TransformOp] = field(default_factory=list)
    runtime_hint: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "source": dataclasses.asdict(self.source) if self.source else None,
            "input_name": self.input_name,
            "declared_type": dataclasses.asdict(self.declared_type) if self.declared_type else None,
            "ops": [op.to_dict() for op in self.ops],
            "runtime_hint": self.runtime_hint,
        }


@dataclass
class Effect:
    effect_name: str
    input_name: str
    binding: RuntimeBinding
    args: Dict[str, Any] = field(default_factory=dict)
    raw: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "effect_name": self.effect_name,
            "input_name": self.input_name,
            "binding": dataclasses.asdict(self.binding),
            "args": self.args,
            "raw": self.raw,
        }


@dataclass
class Program:
    policy: Policy = field(default_factory=Policy)
    bindings: List[Binding] = field(default_factory=list)
    effects: List[Effect] = field(default_factory=list)
    comments: List[str] = field(default_factory=list)

    def binding_map(self) -> Dict[str, Binding]:
        return {b.name: b for b in self.bindings}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policy": self.policy.to_dict(),
            "bindings": [b.to_dict() for b in self.bindings],
            "effects": [e.to_dict() for e in self.effects],
            "comments": self.comments,
        }


class ProgramParser:
    POLICY_RE = re.compile(r"^\s*policy\s*\{\s*$")
    BIND_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?::\s*([^=@:=]+?))?\s*(?:@([A-Za-z_][A-Za-z0-9_]*))?\s*(?::=|=)\s*(.+)$")
    EFFECT_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)!\s+([A-Za-z_][A-Za-z0-9_]*)\s+(.+)$")
    SOURCE_RE = re.compile(r'^\s*source\s+@([A-Za-z0-9_\.\-:]+)\s+(".*"|[\'.*\'])\s*$')

    def parse(self, text: str) -> Program:
        prog = Program()
        lines = text.splitlines()
        i = 0
        while i < len(lines):
            raw = lines[i]
            stripped = raw.strip()
            if not stripped:
                i += 1
                continue
            if stripped.startswith("#"):
                prog.comments.append(stripped)
                i += 1
                continue
            if self.POLICY_RE.match(raw):
                block, j = self._collect_block(lines, i)
                prog.policy = self._parse_policy_block(block)
                i = j
                continue
            effect_m = self.EFFECT_RE.match(raw)
            if effect_m:
                effect_name, input_name, rest = effect_m.groups()
                prog.effects.append(self._parse_effect(effect_name, input_name, rest, raw))
                i += 1
                continue
            bind_m = self.BIND_RE.match(raw)
            if bind_m:
                name, declared_type, runtime_hint, rhs = bind_m.groups()
                prog.bindings.append(self._parse_binding(name, declared_type, rhs, runtime_hint))
                i += 1
                continue
            raise ParseError(f"Cannot parse line {i + 1}: {raw}")
        self._validate_names(prog)
        return prog

    def _collect_block(self, lines: List[str], start: int) -> Tuple[List[str], int]:
        block: List[str] = []
        depth = 0
        i = start
        while i < len(lines):
            line = lines[i]
            depth += line.count("{")
            depth -= line.count("}")
            block.append(line)
            i += 1
            if depth == 0:
                return block, i
        raise ParseError("Unterminated block")

    def _parse_policy_block(self, lines: List[str]) -> Policy:
        pol = Policy()
        inner = lines[1:-1]
        for line in inner:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if s.startswith("optimize:"):
                val = s.split(":", 1)[1].strip()
                if ">" in val:
                    left, right = [x.strip() for x in val.split(">", 1)]
                    pol.optimize_left = left
                    pol.optimize_right = right
                else:
                    pol.optimize_left = val
                    pol.optimize_right = "cost"
                continue
            if s.startswith("deterministic:"):
                pol.deterministic = s.split(":", 1)[1].strip().lower() == "true"
                continue
            if s.startswith("retries:"):
                pol.retries = int(s.split(":", 1)[1].strip())
                continue
            if s.startswith("allow ") or s.startswith("deny "):
                allow = s.startswith("allow ")
                rest = s.split(" ", 1)[1]
                m = re.match(r"([A-Za-z_]+)\[(.*)\]$", rest)
                if not m:
                    raise ParseError(f"Invalid policy rule: {s}")
                kind_raw, subjects_raw = m.groups()
                kind = CapabilityKind(kind_raw)
                subjects = [x.strip() for x in split_csv_like(subjects_raw)]
                pol.rules.append(AllowDenyRule(allow=allow, kind=kind, subjects=subjects))
                continue
            if ":" in s:
                k, v = s.split(":", 1)
                pol.custom[k.strip()] = self._parse_scalar(v.strip())
                continue
            raise ParseError(f"Unknown policy directive: {s}")
        return pol

    def _parse_effect(self, effect_name: str, input_name: str, rest: str, raw: str) -> Effect:
        parts = shlex.split(rest)
        if not parts:
            raise ParseError(f"Invalid effect: {raw}")
        binding_part = parts[0]
        if not binding_part.startswith("@"):
            raise ParseError(f"Effect must start with runtime binding: {raw}")
        token = binding_part[1:]
        if ":" in token:
            kind, target = token.split(":", 1)
        else:
            kind, target = token, ""
        args: Dict[str, Any] = {}
        for p in parts[1:]:
            if ":" in p:
                k, v = p.split(":", 1)
                args[k] = self._parse_scalar(v)
            else:
                args[p] = True
        return Effect(effect_name=effect_name, input_name=input_name, binding=RuntimeBinding(kind=kind, target=target), args=args, raw=raw)

    def _parse_binding(self, name: str, declared_type: Optional[str], rhs: str, runtime_hint: Optional[str] = None) -> Binding:
        declared = TypeRef.from_string(declared_type) if declared_type else None
        source_m = self.SOURCE_RE.match(rhs)
        if source_m:
            runtime, payload = source_m.groups()
            return Binding(
                name=name,
                declared_type=declared,
                source=SourceSpec(runtime=runtime, payload=ast.literal_eval(payload)),
                ops=[],
                runtime_hint=runtime_hint,
            )

        # Handle & (join) and | (fallback/alternative pipeline)
        # For simplicity in this prototype, we'll treat them as special ops if they appear

        if " & " in rhs:
            parts = [p.strip() for p in rhs.split(" & ")]
            return Binding(
                name=name,
                input_name=parts[0],
                declared_type=declared,
                ops=[TransformOp("join", {"with": parts[1:]})],
                runtime_hint=runtime_hint,
            )

        if " | " in rhs:
            parts = [p.strip() for p in rhs.split(" | ")]
            # If it's a fallback, we can model it as an op
            return Binding(
                name=name,
                input_name=parts[0],
                declared_type=declared,
                ops=[TransformOp("fallback", {"alternatives": parts[1:]})],
                runtime_hint=runtime_hint,
            )

        segments = [seg.strip() for seg in rhs.split("->")]
        if not segments:
            raise ParseError(f"Invalid binding for {name}")
        input_name = segments[0]
        ops: List[TransformOp] = []
        for seg in segments[1:]:
            ops.append(self._parse_transform(seg))
        return Binding(name=name, input_name=input_name, declared_type=declared, ops=ops, runtime_hint=runtime_hint)

    def _parse_transform(self, seg: str) -> TransformOp:
        seg = seg.strip()
        approximate = False
        if seg.startswith("~>"):
            approximate = True
            seg = seg[2:].strip()
        runtime_hint = None
        planner_hints: Dict[str, Any] = {}
        if " #" in seg:
            seg, hint_part = seg.split(" #", 1)
            planner_hints["hint"] = hint_part.strip()
        if " @" in seg:
            left, right = seg.rsplit(" @", 1)
            seg = left.strip()
            runtime_hint = right.strip()
        if seg.startswith("filter "):
            return TransformOp("filter", {"predicate": seg[len("filter "):].strip()}, runtime_hint, approximate, planner_hints)
        if seg.startswith("project "):
            body = seg[len("project "):].strip()
            fields = [x.strip() for x in split_csv_like(body[1:-1])] if body.startswith("[") and body.endswith("]") else [body]
            return TransformOp("project", {"fields": fields}, runtime_hint, approximate, planner_hints)
        if seg.startswith("map "):
            return TransformOp("map", {"expr": seg[len("map "):].strip()}, runtime_hint, approximate, planner_hints)
        if seg.startswith("group "):
            return TransformOp("group", {"field": seg[len("group "):].strip()}, runtime_hint, approximate, planner_hints)
        if seg.startswith("sum "):
            return TransformOp("sum", {"field": seg[len("sum "):].strip()}, runtime_hint, approximate, planner_hints)
        if seg.startswith("limit "):
            return TransformOp("limit", {"n": int(seg[len("limit "):].strip())}, runtime_hint, approximate, planner_hints)
        if seg.startswith("sort "):
            return TransformOp("sort", {"expr": seg[len("sort "):].strip()}, runtime_hint, approximate, planner_hints)
        if seg.startswith("batch "):
            return TransformOp("batch", {"n": int(seg[len("batch "):].strip())}, runtime_hint, approximate, planner_hints)
        if seg.startswith("python "):
            return TransformOp("python", {"expr": seg[len("python "):].strip()}, runtime_hint or "python:local", approximate, planner_hints)
        return TransformOp("custom", {"expr": seg}, runtime_hint, approximate, planner_hints)

    def _parse_scalar(self, text: str) -> Any:
        text = text.strip()
        if text.lower() in ("true", "false"):
            return text.lower() == "true"
        if text.isdigit():
            return int(text)
        try:
            return float(text)
        except Exception:
            pass
        if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
            return ast.literal_eval(text)
        if text.startswith("[") and text.endswith("]"):
            return [self._parse_scalar(x) for x in split_csv_like(text[1:-1])]
        return text

    def _validate_names(self, prog: Program) -> None:
        seen = set()
        for b in prog.bindings:
            if b.name in seen:
                raise ParseError(f"Duplicate binding name: {b.name}")
            seen.add(b.name)
        for e in prog.effects:
            if e.input_name not in seen:
                raise ParseError(f"Effect input does not refer to a known binding: {e.input_name}")


@dataclass
class GraphNode:
    id: str
    kind: str
    ref_name: str
    payload: Dict[str, Any] = field(default_factory=dict)
    deps: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class ProgramGraph:
    nodes: List[GraphNode] = field(default_factory=list)

    def node_map(self) -> Dict[str, GraphNode]:
        return {n.id: n for n in self.nodes}

    def topo(self) -> List[GraphNode]:
        node_map = self.node_map()
        indegree = {nid: 0 for nid in node_map}
        for n in self.nodes:
            for dep in n.deps:
                indegree[n.id] += 1
        queue = [node_map[nid] for nid, deg in indegree.items() if deg == 0]
        out: List[GraphNode] = []
        while queue:
            cur = queue.pop(0)
            out.append(cur)
            for n in self.nodes:
                if cur.id in n.deps:
                    indegree[n.id] -= 1
                    if indegree[n.id] == 0:
                        queue.append(n)
        if len(out) != len(self.nodes):
            raise VerificationError("Cycle detected in program graph")
        return out


class GraphBuilder:
    def build(self, prog: Program) -> ProgramGraph:
        nodes: List[GraphNode] = []
        for b in prog.bindings:
            deps: List[str] = []
            if b.input_name:
                deps.append(f"binding:{b.input_name}")
            for op in b.ops:
                if op.name == "join":
                    for other in op.args.get("with", []):
                        deps.append(f"binding:{other}")
                elif op.name == "fallback":
                    for other in op.args.get("alternatives", []):
                        deps.append(f"binding:{other}")
            nodes.append(GraphNode(id=f"binding:{b.name}", kind="binding", ref_name=b.name, payload=b.to_dict(), deps=deps))
        for idx, e in enumerate(prog.effects):
            nodes.append(GraphNode(
                id=f"effect:{idx}:{e.effect_name}",
                kind="effect",
                ref_name=e.effect_name,
                payload=e.to_dict(),
                deps=[f"binding:{e.input_name}"],
            ))
        return ProgramGraph(nodes=nodes)


class ProgramVerifier:
    def verify_static(self, prog: Program, graph: ProgramGraph) -> None:
        if prog.policy.deterministic:
            for b in prog.bindings:
                for op in b.ops:
                    if op.approximate:
                        raise VerificationError(f"Approximate transform not allowed under deterministic policy: {b.name}:{op.name}")
        for b in prog.bindings:
            if b.source and b.source.runtime.startswith("db"):
                prog.policy.require(CapabilityKind.DATABASE, b.source.runtime)
            for op in b.ops:
                if op.runtime_hint:
                    kind = CapabilityKind.DATABASE if op.runtime_hint.startswith("sql") else CapabilityKind.PYTHON
                    prog.policy.require(kind, op.runtime_hint)
        for e in prog.effects:
            if e.binding.kind.startswith("file"):
                prog.policy.require(CapabilityKind.FILESYSTEM, e.binding.target or "*")
            elif e.binding.kind.startswith("slack"):
                prog.policy.require(CapabilityKind.NETWORK, "slack.ops")
        graph.topo()


class BaseLLMAdapter:
    name = "none"

    def enabled(self) -> bool:
        return False

    def suggest_runtime(self, op: TransformOp, candidates: List[str], context: Dict[str, Any]) -> Optional[str]:
        return None


class HFLocalAdapter(BaseLLMAdapter):
    name = "hf-local"

    def __init__(self, model_name: Optional[str] = None, max_new_tokens: int = 64):
        self.model_name = model_name or os.getenv("SPR_HF_MODEL", "").strip()
        self.max_new_tokens = max_new_tokens
        self._loaded = False
        self._pipeline = None

    def enabled(self) -> bool:
        return bool(self.model_name)

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.model_name:
            return
        try:
            from transformers import pipeline
            self._pipeline = pipeline("text-generation", model=self.model_name, tokenizer=self.model_name, device_map="auto")
        except Exception as exc:
            eprint(f"[llm] failed to load {self.model_name}: {exc}")
            self._pipeline = None

    def suggest_runtime(self, op: TransformOp, candidates: List[str], context: Dict[str, Any]) -> Optional[str]:
        self._load()
        if not self._pipeline:
            return None
        prompt = textwrap.dedent(f"""
        Choose exactly one runtime from:
        {json.dumps(candidates)}

        Operation:
        {json.dumps(op.to_dict(), ensure_ascii=False)}

        Context:
        {json.dumps(context, ensure_ascii=False)}

        Answer with only one candidate.
        """).strip()
        try:
            out = self._pipeline(prompt, max_new_tokens=self.max_new_tokens, do_sample=False)
            txt = out[0].get("generated_text", "")
            txt = txt[len(prompt):].strip() if txt.startswith(prompt) else txt.strip()
            line = txt.splitlines()[0].strip().strip('"').strip("'")
            return line if line in candidates else None
        except Exception:
            return None


class DisabledRemoteAdapter(BaseLLMAdapter):
    name = "remote-disabled"

    def enabled(self) -> bool:
        return False


@dataclass
class LoweredStep:
    step_id: str
    binding_name: str
    op_index: Optional[int]
    runtime: str
    kind: str
    payload: Dict[str, Any]
    input_ref: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class LoweredEffect:
    effect_id: str
    effect_name: str
    input_name: str
    runtime: str
    payload: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class ExecutionPlan:
    policy: Dict[str, Any]
    steps: List[LoweredStep]
    effects: List[LoweredEffect]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policy": self.policy,
            "steps": [s.to_dict() for s in self.steps],
            "effects": [e.to_dict() for e in self.effects],
        }


class CostModel:
    def rank_transform(self, binding: Binding, op: TransformOp, source_runtime: Optional[str]) -> List[str]:
        if op.runtime_hint:
            return [op.runtime_hint]
        if op.name in {"filter", "project", "group", "sum", "limit", "sort"} and source_runtime and source_runtime.startswith("db"):
            return ["sql:pushdown", "python:local"]
        if op.name in {"map", "custom", "python", "batch"}:
            return ["python:local"]
        return ["python:local"]

    def rank_effect(self, effect: Effect) -> List[str]:
        if effect.binding.kind.startswith("file"):
            return ["file:local"]
        if effect.binding.kind.startswith("slack"):
            return ["http:slack"]
        return [effect.binding.kind]

    def choose(self, candidates: List[str]) -> str:
        return candidates[0]


class Planner:
    def __init__(self, llm: Optional[BaseLLMAdapter] = None):
        self.cost_model = CostModel()
        self.llm = llm or BaseLLMAdapter()

    def build_plan(self, prog: Program) -> ExecutionPlan:
        steps: List[LoweredStep] = []
        for binding in prog.bindings:
            source_runtime = binding.source.runtime if binding.source else None
            if binding.source:
                runtime = "sql:source" if binding.source.runtime.startswith("db") else "python:source"
                steps.append(LoweredStep(
                    step_id=f"source:{binding.name}",
                    binding_name=binding.name,
                    op_index=None,
                    runtime=runtime,
                    kind="source",
                    payload={"payload": binding.source.payload, "source_runtime": binding.source.runtime},
                ))
            for idx, op in enumerate(binding.ops):
                candidates = self.cost_model.rank_transform(binding, op, source_runtime)
                chosen = self.llm.suggest_runtime(op, candidates, {"binding": binding.name, "policy": prog.policy.to_dict()}) if self.llm.enabled() else None
                runtime = chosen if chosen in candidates else self.cost_model.choose(candidates)

                # Use binding-level runtime hint if it matches candidates
                if binding.runtime_hint:
                    for c in candidates:
                        if c.startswith(binding.runtime_hint):
                            runtime = c
                            break

                steps.append(LoweredStep(
                    step_id=f"step:{binding.name}:{idx}",
                    binding_name=binding.name,
                    op_index=idx,
                    runtime=runtime,
                    kind="transform",
                    payload=op.to_dict(),
                    input_ref=binding.input_name or binding.name,
                ))
        effects: List[LoweredEffect] = []
        for idx, e in enumerate(prog.effects):
            runtime = self.cost_model.rank_effect(e)[0]
            effects.append(LoweredEffect(
                effect_id=f"effect:{idx}",
                effect_name=e.effect_name,
                input_name=e.input_name,
                runtime=runtime,
                payload=e.to_dict(),
            ))
        return ExecutionPlan(policy=prog.policy.to_dict(), steps=steps, effects=effects)


class SQLLowerer:
    def lower_binding_to_sql(self, binding: Binding, binding_map: Dict[str, Binding] = None) -> str:
        if not binding.source and not binding.input_name:
             raise PlanningError(f"Cannot SQL-lower binding without source or input: {binding.name}")

        if binding.source:
            if not binding.source.runtime.startswith("db"):
                raise PlanningError(f"Cannot SQL-lower non-db source: {binding.source.runtime}")
            sql = binding.source.payload.strip().rstrip(";")
            base_table = f"({sql}) AS _spr_base_{binding.name}"
        else:
            # Try to recursively lower input
            if not binding_map or binding.input_name not in binding_map:
                raise PlanningError(f"Missing binding map or input for {binding.name}")
            input_sql = self.lower_binding_to_sql(binding_map[binding.input_name], binding_map)
            base_table = f"({input_sql.rstrip(';')}) AS _spr_base_{binding.name}"

        select_fields: Optional[List[str]] = None
        where_clauses: List[str] = []
        group_clause: Optional[str] = None
        sum_clause: Optional[str] = None
        order_clause: Optional[str] = None
        limit_clause: Optional[int] = None

        for op in binding.ops:
            if op.name == "filter":
                where_clauses.append(op.args["predicate"])
            elif op.name == "project":
                select_fields = op.args["fields"]
            elif op.name == "group":
                group_clause = op.args["field"]
            elif op.name == "sum":
                sum_clause = op.args["field"]
            elif op.name == "sort":
                order_clause = op.args["expr"]
            elif op.name == "limit":
                limit_clause = int(op.args["n"])
            elif op.name == "join":
                # Basic JOIN support
                with_bindings = op.args["with"]
                for other_name in with_bindings:
                    if not binding_map or other_name not in binding_map:
                         raise PlanningError(f"Join target {other_name} not found")
                    other_sql = self.lower_binding_to_sql(binding_map[other_name], binding_map)
                    base_table += f" JOIN ({other_sql.rstrip(';')}) AS _spr_join_{other_name} ON 1=1" # Dummy ON, should be refined
            else:
                raise PlanningError(f"Binding {binding.name} has op not safely lowerable to SQL: {op.name}")

        outer_select = "*"
        if select_fields:
            outer_select = ", ".join(select_fields)
        if group_clause and sum_clause:
            outer_select = f"{group_clause}, SUM({sum_clause}) AS sum_{sum_clause}"

        out = f"SELECT {outer_select} FROM {base_table}"
        if where_clauses:
            out += " WHERE " + " AND ".join(f"({x})" for x in where_clauses)
        if group_clause:
            out += f" GROUP BY {group_clause}"
        if order_clause:
            out += f" ORDER BY {order_clause}"
        if limit_clause is not None:
            out += f" LIMIT {limit_clause}"
        return out + ";"


class PythonLowerer:
    PRELUDE = """
import json
import sqlite3
import pathlib
from typing import Any, Dict, List

def _spr_join(left: List[Dict[str, Any]], right: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for l in left:
        for r in right:
            out.append({**l, **r})
    return out

def _spr_fetch_db_rows(db_path: str, query: str) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(query).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def _spr_write_jsonl(path: str, rows: List[Dict[str, Any]]) -> None:
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\\n")

def _spr_eval_expr(expr: str, row: Dict[str, Any]) -> Any:
    allowed = {"len": len, "int": int, "float": float, "str": str, "bool": bool}
    return eval(expr, {"__builtins__": {}}, {"row": row, **row, **allowed})

def _spr_filter(rows: List[Dict[str, Any]], predicate: str) -> List[Dict[str, Any]]:
    return [r for r in rows if bool(_spr_eval_expr(predicate, r))]

def _spr_project(rows: List[Dict[str, Any]], fields: List[str]) -> List[Dict[str, Any]]:
    return [{k: r.get(k) for k in fields} for r in rows]

def _spr_map(rows: List[Dict[str, Any]], expr: str) -> List[Dict[str, Any]]:
    out = []
    for r in rows:
        val = _spr_eval_expr(expr, r)
        out.append(val if isinstance(val, dict) else {"value": val})
    return out

def _spr_sort(rows: List[Dict[str, Any]], expr: str) -> List[Dict[str, Any]]:
    return sorted(rows, key=lambda r: _spr_eval_expr(expr, r))

def _spr_limit(rows: List[Dict[str, Any]], n: int) -> List[Dict[str, Any]]:
    return rows[:n]

def _spr_batch(rows: List[Dict[str, Any]], n: int) -> List[Dict[str, Any]]:
    return [{"batch_index": i // n, "item": row} for i, row in enumerate(rows)]

def _spr_group_sum(rows: List[Dict[str, Any]], group_field: str, sum_field: str) -> List[Dict[str, Any]]:
    acc = {}
    for r in rows:
        key = r.get(group_field)
        acc[key] = acc.get(key, 0) + (r.get(sum_field) or 0)
    return [{group_field: k, f"sum_{sum_field}": v} for k, v in acc.items()]

def _spr_notify(kind: str, target: str, rows: List[Dict[str, Any]], args: Dict[str, Any]) -> None:
    print(f"[effect] {kind} target={target} rows={len(rows)} args={args}")

DATA = {}
"""

    def lower_python_script(self, prog: Program) -> str:
        lines = [self.PRELUDE.strip(), ""]
        sql_lowerer = SQLLowerer()
        sql_cache: Dict[str, str] = {}
        binding_map = prog.binding_map()

        def can_push_sql(name):
            b = binding_map.get(name)
            if not b: return False
            if b.source: return b.source.runtime.startswith("db")
            if b.input_name:
                if not can_push_sql(b.input_name): return False
                for op in b.ops:
                    if op.name not in {"filter", "project", "group", "sum", "sort", "limit", "join"}:
                        return False
                    if op.name == "join":
                        for other in op.args.get("with", []):
                            if not can_push_sql(other): return False
                return True
            return False

        for b in prog.bindings:
            if b.ops and can_push_sql(b.name):
                try:
                    sql_cache[b.name] = sql_lowerer.lower_binding_to_sql(b, binding_map)
                except Exception:
                    pass
        for b in prog.bindings:
            if b.name in sql_cache:
                lines.append(f'DATA[{json.dumps(b.name)}] = _spr_fetch_db_rows("spr_demo.db", {json.dumps(sql_cache[b.name])})')
                continue

            if b.source:
                if b.source.runtime.startswith("db"):
                    lines.append(f'DATA[{json.dumps(b.name)}] = _spr_fetch_db_rows("spr_demo.db", {json.dumps(b.source.payload)})')
                else:
                    lines.append(f'DATA[{json.dumps(b.name)}] = []')
            elif b.input_name:
                lines.append(f'DATA[{json.dumps(b.name)}] = list(DATA.get({json.dumps(b.input_name)}, []))')

            if b.name not in sql_cache:
                group_field = None
                pending_sum = None
                for op in b.ops:
                    if op.name == "filter":
                        lines.append(f'DATA[{json.dumps(b.name)}] = _spr_filter(DATA[{json.dumps(b.name)}], {json.dumps(op.args["predicate"])})')
                    elif op.name == "project":
                        lines.append(f'DATA[{json.dumps(b.name)}] = _spr_project(DATA[{json.dumps(b.name)}], {json.dumps(op.args["fields"])})')
                    elif op.name == "map":
                        lines.append(f'DATA[{json.dumps(b.name)}] = _spr_map(DATA[{json.dumps(b.name)}], {json.dumps(op.args["expr"])})')
                    elif op.name == "sort":
                        lines.append(f'DATA[{json.dumps(b.name)}] = _spr_sort(DATA[{json.dumps(b.name)}], {json.dumps(op.args["expr"])})')
                    elif op.name == "limit":
                        lines.append(f'DATA[{json.dumps(b.name)}] = _spr_limit(DATA[{json.dumps(b.name)}], {int(op.args["n"])})')
                    elif op.name == "batch":
                        lines.append(f'DATA[{json.dumps(b.name)}] = _spr_batch(DATA[{json.dumps(b.name)}], {int(op.args["n"])})')
                    elif op.name == "group":
                        group_field = op.args["field"]
                    elif op.name == "sum":
                        pending_sum = op.args["field"]
                    elif op.name == "join":
                        for other in op.args.get("with", []):
                            lines.append(f'DATA[{json.dumps(b.name)}] = _spr_join(DATA[{json.dumps(b.name)}], DATA.get({json.dumps(other)}, []))')
                    elif op.name == "fallback":
                        alt_names = op.args["alternatives"]
                        for alt in alt_names:
                            lines.append(f'if not DATA[{json.dumps(b.name)}]: DATA[{json.dumps(b.name)}] = DATA.get({json.dumps(alt)}, [])')
                    elif op.name in {"custom", "python"}:
                        lines.append(f'DATA[{json.dumps(b.name)}] = _spr_map(DATA[{json.dumps(b.name)}], {json.dumps(op.args["expr"])})')
                if group_field and pending_sum:
                    lines.append(f'DATA[{json.dumps(b.name)}] = _spr_group_sum(DATA[{json.dumps(b.name)}], {json.dumps(group_field)}, {json.dumps(pending_sum)})')
        for e in prog.effects:
            if e.binding.kind.startswith("file"):
                target = e.binding.target or e.args.get("path") or f"{e.input_name}.jsonl"
                lines.append(f'_spr_write_jsonl({json.dumps(target)}, DATA[{json.dumps(e.input_name)}])')
            else:
                lines.append(f'_spr_notify({json.dumps(e.effect_name)}, {json.dumps(e.binding.kind + ":" + e.binding.target)}, DATA[{json.dumps(e.input_name)}], {json.dumps(e.args)})')
        lines.append('print(json.dumps({"bindings": {k: len(v) if isinstance(v, list) else None for k, v in DATA.items()}}, indent=2))')
        return "\n".join(lines) + "\n"


class SemanticProtocolCompiler:
    def __init__(self, llm: Optional[BaseLLMAdapter] = None):
        self.parser = ProgramParser()
        self.graph_builder = GraphBuilder()
        self.verifier = ProgramVerifier()
        self.planner = Planner(llm=llm or BaseLLMAdapter())
        self.py_lowerer = PythonLowerer()
        self.sql_lowerer = SQLLowerer()

    def parse(self, text: str) -> Program:
        return self.parser.parse(text)

    def graph(self, prog: Program) -> ProgramGraph:
        return self.graph_builder.build(prog)

    def verify(self, prog: Program) -> ProgramGraph:
        graph = self.graph(prog)
        self.verifier.verify_static(prog, graph)
        return graph

    def plan(self, prog: Program) -> ExecutionPlan:
        self.verify(prog)
        return self.planner.build_plan(prog)

    def compile(self, prog: Program, out_dir: Union[str, pathlib.Path]) -> Dict[str, Any]:
        out = ensure_dir(out_dir)
        graph = self.verify(prog)
        plan = self.plan(prog)
        dump_text_file(out / "program.json", pretty(prog.to_dict()))
        dump_text_file(out / "graph.json", pretty({"nodes": [n.to_dict() for n in graph.nodes]}))
        dump_text_file(out / "plan.json", pretty(plan.to_dict()))
        sql_artifacts: Dict[str, str] = {}
        sql_dir = ensure_dir(out / "sql")
        for b in prog.bindings:
            if b.source and b.source.runtime.startswith("db"):
                try:
                    sql_artifacts[b.name] = self.sql_lowerer.lower_binding_to_sql(b)
                    dump_text_file(sql_dir / f"{b.name}.sql", sql_artifacts[b.name])
                except Exception:
                    pass
        dump_text_file(out / "runtime_generated.py", self.py_lowerer.lower_python_script(prog))
        return {
            "out_dir": str(out),
            "sql_artifacts": list(sql_artifacts.keys()),
            "files": sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file()),
        }

    def explain(self, prog: Program) -> str:
        graph = self.verify(prog)
        plan = self.plan(prog)
        lines = [f"{APP_NAME} {APP_VERSION}", "", "Policy", "------", pretty(prog.policy.to_dict()), "", "Bindings", "--------"]
        for b in prog.bindings:
            lines.append(f"- {b.name}")
            if b.source:
                lines.append(f"  source: @{b.source.runtime} {b.source.payload!r}")
            if b.input_name:
                lines.append(f"  input: {b.input_name}")
            if b.declared_type:
                lines.append(f"  type: {b.declared_type.raw}")
            for i, op in enumerate(b.ops):
                lines.append(f"  op[{i}]: {op.name} args={json.dumps(op.args, ensure_ascii=False)} hint={op.runtime_hint!r}")
        lines.extend(["", "Effects", "-------"])
        for e in prog.effects:
            lines.append(f"- {e.effect_name}! {e.input_name} @{e.binding.kind}:{e.binding.target} args={json.dumps(e.args, ensure_ascii=False)}")
        lines.extend(["", "Graph", "-----"])
        for n in graph.topo():
            lines.append(f"- {n.id} deps={n.deps}")
        lines.extend(["", "Plan", "----"])
        for s in plan.steps:
            lines.append(f"- {s.step_id}: runtime={s.runtime} kind={s.kind} input={s.input_ref}")
        for e in plan.effects:
            lines.append(f"- {e.effect_id}: runtime={e.runtime} effect={e.effect_name} input={e.input_name}")
        return "\n".join(lines)


class Runner:
    def __init__(self, compiler: SemanticProtocolCompiler):
        self.compiler = compiler

    def run(self, prog: Program, build_dir: Union[str, pathlib.Path], dry_run: bool = False) -> Dict[str, Any]:
        result = self.compiler.compile(prog, build_dir)
        runtime_file = pathlib.Path(result["out_dir"]) / "runtime_generated.py"
        if dry_run:
            return {"dry_run": True, "runtime_file": str(runtime_file), "build": result}
        db_path = pathlib.Path(result["out_dir"]) / "spr_demo.db"
        if not db_path.exists():
            self._seed_demo_db(db_path)
        code = runtime_file.read_text(encoding="utf-8")
        ns: Dict[str, Any] = {}
        cwd = os.getcwd()
        os.chdir(result["out_dir"])
        try:
            exec(compile(code, str(runtime_file), "exec"), ns, ns)
        finally:
            os.chdir(cwd)
        return {"dry_run": False, "runtime_file": str(runtime_file), "build": result, "db_path": str(db_path)}

    def _seed_demo_db(self, db_path: pathlib.Path) -> None:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("create table if not exists users (id integer, email text, score real)")
            conn.execute("delete from users")
            rows = [
                (1, "a@example.com", 0.91),
                (2, "b@example.com", 0.77),
                (3, "c@example.com", 0.99),
                (4, "d@example.com", 0.45),
            ]
            conn.executemany("insert into users values (?, ?, ?)", rows)

            conn.execute("create table if not exists profiles (user_id integer, bio text)")
            conn.execute("delete from profiles")
            profiles = [
                (1, "Engineer"),
                (2, "Designer"),
                (3, "Scientist"),
            ]
            conn.executemany("insert into profiles values (?, ?)", profiles)

            conn.commit()
        finally:
            conn.close()


class REPL:
    def __init__(self, compiler: SemanticProtocolCompiler):
        self.compiler = compiler
        self.current_program: Optional[Program] = None
        self.current_text: Optional[str] = None
        self.cwd = pathlib.Path.cwd()

    def loop(self) -> None:
        print(f"{APP_NAME} {APP_VERSION}\nType 'help' for commands.")
        while True:
            try:
                line = input("spr> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if not line:
                continue
            try:
                if line in {"quit", "exit"}:
                    return
                if line == "help":
                    print("load <file> | show | explain | compile [dir] | run [--dry] | quit")
                elif line.startswith("load "):
                    full = (self.cwd / line[len('load '):].strip()).resolve()
                    self.current_text = load_text_file(full)
                    self.current_program = self.compiler.parse(self.current_text)
                    print(f"Loaded {full}")
                elif line == "show":
                    if self.current_text is None:
                        raise SPRRuntimeError("No program loaded")
                    print(self.current_text)
                elif line == "explain":
                    if self.current_program is None:
                        raise SPRRuntimeError("No program loaded")
                    print(self.compiler.explain(self.current_program))
                elif line.startswith("compile"):
                    if self.current_program is None:
                        raise SPRRuntimeError("No program loaded")
                    parts = shlex.split(line)
                    out = parts[1] if len(parts) > 1 else DEFAULT_BUILD_DIR
                    print(pretty(self.compiler.compile(self.current_program, out)))
                elif line.startswith("run"):
                    if self.current_program is None:
                        raise SPRRuntimeError("No program loaded")
                    dry = "--dry" in shlex.split(line)
                    print(pretty(Runner(self.compiler).run(self.current_program, DEFAULT_BUILD_DIR, dry_run=dry)))
                else:
                    print("Unknown command")
            except Exception as exc:
                print(f"[error] {exc}")
                traceback.print_exc()


DEMO_PROTOCOL = """
policy {
  optimize: latency > cost
  deterministic: true
  allow database[db.main]
  allow filesystem[*]
  allow network[slack.ops]
  deny shell[*]
  retries: 1
}

users := source @db.main "select id, email, score from users"
hot   := users -> filter score > 0.8 -> project [id, email, score] -> sort score -> limit 10
write! hot @file:"hot_users.jsonl"
notify! hot @slack.ops:"#risk"
""".strip() + "\n"


def ensure_demo_examples(root: Union[str, pathlib.Path] = ".") -> pathlib.Path:
    root = ensure_dir(root)
    examples = ensure_dir(pathlib.Path(root) / "examples")
    dump_text_file(examples / "demo.spr", DEMO_PROTOCOL)
    return examples


def build_compiler_from_env() -> SemanticProtocolCompiler:
    llm_mode = os.getenv("SPR_LLM_MODE", "hf-local").strip()
    if llm_mode == "hf-local":
        llm = HFLocalAdapter()
    else:
        llm = BaseLLMAdapter()
    return SemanticProtocolCompiler(llm=llm)


def make_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=APP_NAME, description="Semantic protocol runtime prototype")
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("init", help="create example files")
    s.add_argument("--dir", default=".")
    s.set_defaults(func=lambda a: (print(f"Created {ensure_demo_examples(a.dir)}"), 0)[1])
    s = sub.add_parser("parse", help="parse a protocol file")
    s.add_argument("file")
    s.set_defaults(func=lambda a: (print(pretty(build_compiler_from_env().parse(load_text_file(a.file)).to_dict())), 0)[1])
    s = sub.add_parser("explain", help="verify and explain a protocol file")
    s.add_argument("file")
    s.set_defaults(func=lambda a: (print(build_compiler_from_env().explain(build_compiler_from_env().parse(load_text_file(a.file)))), 0)[1])
    s = sub.add_parser("compile", help="compile a protocol file to artifacts")
    s.add_argument("file")
    s.add_argument("--out", default=DEFAULT_BUILD_DIR)
    def _compile(a):
        c = build_compiler_from_env()
        print(pretty(c.compile(c.parse(load_text_file(a.file)), a.out)))
        return 0
    s.set_defaults(func=_compile)
    s = sub.add_parser("run", help="compile and execute a protocol file")
    s.add_argument("file")
    s.add_argument("--out", default=DEFAULT_BUILD_DIR)
    s.add_argument("--dry-run", action="store_true")
    def _run(a):
        c = build_compiler_from_env()
        print(pretty(Runner(c).run(c.parse(load_text_file(a.file)), a.out, dry_run=a.dry_run)))
        return 0
    s.set_defaults(func=_run)
    s = sub.add_parser("repl", help="interactive mode")
    s.set_defaults(func=lambda a: (ensure_demo_examples("."), REPL(build_compiler_from_env()).loop(), 0)[2])
    return p


def main(argv: Optional[List[str]] = None) -> int:
    argv = argv or sys.argv[1:]
    parser = make_arg_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except SPRRuntimeError as exc:
        eprint(f"[{type(exc).__name__}] {exc}")
        return 2
    except Exception as exc:
        eprint(f"[fatal] {exc}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
