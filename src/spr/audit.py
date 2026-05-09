"""Audit artifact support for the production SPR wedge.

Every meaningful run should produce inspectable evidence:
source.spr, parsed_ir.json, graph.json, policy_result.json, plan.json,
outputs.json, final_report.md, and proof_manifest.json.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import pathlib
import time
from typing import Any, Mapping

from .errors import SPRAuditError


def utc_run_id(prefix: str = "spr") -> str:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return f"{prefix}_{stamp}"


def json_default(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return str(value)


def write_json(path: pathlib.Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=json_default), encoding="utf-8")


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


class AuditRun:
    """A single run's evidence folder."""

    def __init__(self, root: str | pathlib.Path = ".spr_runs", run_id: str | None = None):
        self.root = pathlib.Path(root)
        self.run_id = run_id or utc_run_id()
        self.path = self.root / self.run_id

    def start(self) -> pathlib.Path:
        try:
            self.path.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise SPRAuditError(f"audit run already exists: {self.path}") from exc
        latest = self.root / "latest"
        try:
            if latest.exists() or latest.is_symlink():
                latest.unlink()
            latest.symlink_to(self.path.name, target_is_directory=True)
        except OSError:
            # Windows or restricted filesystems may not allow symlinks; write a pointer instead.
            (self.root / "LATEST.txt").write_text(self.run_id, encoding="utf-8")
        return self.path

    def write_text(self, name: str, content: str) -> pathlib.Path:
        target = self.path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def write_json(self, name: str, payload: Any) -> pathlib.Path:
        target = self.path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        write_json(target, payload)
        return target

    def seal(self, extra: Mapping[str, Any] | None = None) -> pathlib.Path:
        artifacts = {}
        for file in sorted(self.path.rglob("*")):
            if file.is_file() and file.name != "proof_manifest.json":
                artifacts[str(file.relative_to(self.path))] = sha256_file(file)
        manifest = {
            "run_id": self.run_id,
            "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "hash_algorithm": "sha256",
            "artifacts": artifacts,
            "extra": dict(extra or {}),
        }
        return self.write_json("proof_manifest.json", manifest)


def read_audit_summary(path: str | pathlib.Path) -> dict[str, Any]:
    folder = pathlib.Path(path)
    if not folder.exists():
        raise SPRAuditError(f"audit path does not exist: {folder}")
    if folder.is_symlink():
        folder = folder.resolve()
    if folder.is_file():
        raise SPRAuditError(f"audit path must be a directory: {folder}")
    summary: dict[str, Any] = {"path": str(folder), "files": []}
    for file in sorted(folder.rglob("*")):
        if file.is_file():
            summary["files"].append(str(file.relative_to(folder)))
    manifest = folder / "proof_manifest.json"
    if manifest.exists():
        summary["proof_manifest"] = json.loads(manifest.read_text(encoding="utf-8"))
    report = folder / "final_report.md"
    if report.exists():
        summary["final_report"] = report.read_text(encoding="utf-8")
    return summary
