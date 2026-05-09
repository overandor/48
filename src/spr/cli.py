"""Production-wedge CLI for Semantic Protocol Runtime.

This CLI intentionally focuses on the narrow core:
- init a demo
- explain a .spr file
- compile plan artifacts
- run with dry-run by default
- audit a saved run

Voice and autonomous coding remain separate experimental layers.
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import sys
from typing import Any

from .audit import AuditRun, read_audit_summary
from .compat import GraphBuilder, Planner, ProgramParser, ProgramVerifier, SQLLowerer
from .errors import SPRError, SPRLoweringError

HOT_USERS_EXAMPLE = '''policy {
  optimize: latency > cost
  deterministic: true
  allow database[db.main]
  allow filesystem[*]
  deny network[*]
  deny shell[*]
}

users := source @db.main "select id, email, score from users"
hot   := users -> filter score > 0.8 -> project [id, email, score]
write! hot @file:"hot_users.jsonl"
'''


def load_program(path: str | pathlib.Path):
    source_path = pathlib.Path(path)
    source = source_path.read_text(encoding="utf-8")
    program = ProgramParser().parse(source)
    graph = GraphBuilder().build(program)
    ProgramVerifier().verify_static(program, graph)
    plan = Planner().build_plan(program)
    return source, program, graph, plan


def explain(path: str | pathlib.Path) -> dict[str, Any]:
    _source, program, graph, plan = load_program(path)
    return {
        "program": program.to_dict(),
        "graph": {"nodes": [node.to_dict() for node in graph.nodes]},
        "plan": plan.to_dict(),
    }


def compile_artifacts(path: str | pathlib.Path, out_dir: str | pathlib.Path) -> pathlib.Path:
    source, program, graph, plan = load_program(path)
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    audit = AuditRun(root=out, run_id="compile")
    # compile output may already exist; replace for deterministic local use
    if audit.path.exists():
        shutil.rmtree(audit.path)
    audit.start()
    audit.write_text("source.spr", source)
    audit.write_json("parsed_ir.json", program.to_dict())
    audit.write_json("graph.json", {"nodes": [node.to_dict() for node in graph.nodes]})
    audit.write_json("policy_result.json", {"ok": True, "policy": program.policy.to_dict()})
    audit.write_json("plan.json", plan.to_dict())

    lowered_sql: list[str] = []
    binding_map = program.binding_map()
    sql_lowerer = SQLLowerer()
    for binding in program.bindings:
        try:
            if binding.source or any(op.name in {"filter", "project", "limit", "sort", "group", "sum"} for op in binding.ops):
                lowered_sql.append(f"-- binding: {binding.name}\n" + sql_lowerer.lower_binding_to_sql(binding, binding_map))
        except Exception as exc:
            lowered_sql.append(f"-- binding: {binding.name}\n-- not SQL-lowerable: {exc}")
    audit.write_text("lowered_sql.sql", "\n\n".join(lowered_sql).strip() + "\n")
    audit.write_text("lowered_python.py", "# Python lowering artifact placeholder for production wedge.\n")
    audit.write_json("outputs.json", {"compiled": True, "executed": False})
    audit.write_text("final_report.md", "# SPR Compile Report\n\nCompilation completed. No workflow execution occurred.\n")
    audit.seal({"mode": "compile"})
    return audit.path


def run_protocol(path: str | pathlib.Path, *, dry_run: bool, audit_dir: str | pathlib.Path) -> pathlib.Path:
    source, program, graph, plan = load_program(path)
    audit = AuditRun(root=audit_dir)
    audit.start()
    audit.write_text("source.spr", source)
    audit.write_json("parsed_ir.json", program.to_dict())
    audit.write_json("graph.json", {"nodes": [node.to_dict() for node in graph.nodes]})
    audit.write_json("policy_result.json", {"ok": True, "policy": program.policy.to_dict()})
    audit.write_json("plan.json", plan.to_dict())

    lowered_sql: list[str] = []
    binding_map = program.binding_map()
    sql_lowerer = SQLLowerer()
    for binding in program.bindings:
        try:
            lowered_sql.append(f"-- binding: {binding.name}\n" + sql_lowerer.lower_binding_to_sql(binding, binding_map))
        except Exception:
            continue
    audit.write_text("lowered_sql.sql", "\n\n".join(lowered_sql).strip() + "\n")
    audit.write_text("lowered_python.py", "# Python lowering artifact placeholder for production wedge.\n")

    if dry_run:
        outputs = {
            "dry_run": True,
            "executed": False,
            "message": "Dry run only. Plan, policy, graph, and lowering artifacts were generated.",
        }
        report = "# SPR Dry Run Report\n\nNo effects were executed. Audit artifacts were generated.\n"
    else:
        # Production wedge: do not silently execute side effects yet.
        # This preserves the product promise: plan and audit before action.
        outputs = {
            "dry_run": False,
            "executed": False,
            "message": "Real execution is intentionally gated in this production wedge. Use --dry-run until effect executors are hardened.",
        }
        report = "# SPR Run Report\n\nExecution was gated. No side effects were executed.\n"
    audit.write_json("outputs.json", outputs)
    audit.write_text("final_report.md", report)
    audit.seal({"mode": "run", "dry_run": dry_run})
    return audit.path


def init_demo(target: str | pathlib.Path) -> pathlib.Path:
    root = pathlib.Path(target)
    (root / "examples").mkdir(parents=True, exist_ok=True)
    demo = root / "examples" / "hot_users.spr"
    demo.write_text(HOT_USERS_EXAMPLE, encoding="utf-8")
    return demo


def print_json(payload: Any) -> None:
    import json

    print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=str))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="spr", description="Semantic Protocol Runtime production-wedge CLI")
    parser.add_argument("--version", action="version", version="spr 0.1.0")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="create a demo project or example")
    p_init.add_argument("name", nargs="?", default="demo")
    p_init.add_argument("--dir", default=".")

    p_explain = sub.add_parser("explain", help="parse, verify, graph, and plan a .spr file")
    p_explain.add_argument("file")

    p_compile = sub.add_parser("compile", help="write compile artifacts without executing effects")
    p_compile.add_argument("file")
    p_compile.add_argument("--out", default="build")

    p_run = sub.add_parser("run", help="run or dry-run a .spr file with audit artifacts")
    p_run.add_argument("file")
    p_run.add_argument("--dry-run", action="store_true", default=True)
    p_run.add_argument("--audit-dir", default=".spr_runs")

    p_audit = sub.add_parser("audit", help="inspect an audit run directory")
    p_audit.add_argument("path")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            demo = init_demo(pathlib.Path(args.dir) / args.name)
            print(f"Created demo: {demo}")
            return 0
        if args.command == "explain":
            print_json(explain(args.file))
            return 0
        if args.command == "compile":
            path = compile_artifacts(args.file, args.out)
            print(f"Wrote compile artifacts: {path}")
            return 0
        if args.command == "run":
            path = run_protocol(args.file, dry_run=args.dry_run, audit_dir=args.audit_dir)
            print(f"Wrote audit artifacts: {path}")
            return 0
        if args.command == "audit":
            print_json(read_audit_summary(args.path))
            return 0
    except SPRError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"SPR_ERROR: {exc}", file=sys.stderr)
        return 1
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
