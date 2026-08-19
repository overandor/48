"""Proof manifest utilities for Semantic Protocol Runtime.

This module creates tamper-evident SHA-256 manifests for audit folders.
It is intentionally boring and dependency-free: a production customer can inspect
exactly what was hashed and when.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import time
from dataclasses import asdict, dataclass
from typing import Any

from .errors import SPRAuditError


@dataclass
class ArtifactHash:
    path: str
    sha256: str
    bytes: int


@dataclass
class ProofManifest:
    manifest_version: str
    created_at_utc: str
    root: str
    artifacts: list[ArtifactHash]
    artifact_count: int

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["artifacts"] = [asdict(a) for a in self.artifacts]
        return data


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(root: str | pathlib.Path, *, exclude_manifest: bool = True) -> ProofManifest:
    folder = pathlib.Path(root).resolve()
    if not folder.exists() or not folder.is_dir():
        raise SPRAuditError(f"proof root must be an existing directory: {folder}")

    artifacts: list[ArtifactHash] = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(folder).as_posix()
        if exclude_manifest and rel == "proof_manifest.json":
            continue
        artifacts.append(
            ArtifactHash(path=rel, sha256="sha256:" + sha256_file(path), bytes=path.stat().st_size)
        )

    return ProofManifest(
        manifest_version="1.0",
        created_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        root=str(folder),
        artifacts=artifacts,
        artifact_count=len(artifacts),
    )


def write_manifest(root: str | pathlib.Path, output: str = "proof_manifest.json") -> pathlib.Path:
    folder = pathlib.Path(root).resolve()
    manifest = build_manifest(folder)
    target = folder / output
    target.write_text(json.dumps(manifest.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return target


def verify_manifest(root: str | pathlib.Path, manifest_name: str = "proof_manifest.json") -> dict[str, Any]:
    folder = pathlib.Path(root).resolve()
    manifest_path = folder / manifest_name
    if not manifest_path.exists():
        raise SPRAuditError(f"proof manifest not found: {manifest_path}")
    saved = json.loads(manifest_path.read_text(encoding="utf-8"))
    current = build_manifest(folder).to_dict()

    saved_map = {a["path"]: a for a in saved.get("artifacts", [])}
    current_map = {a["path"]: a for a in current.get("artifacts", [])}
    changed: list[str] = []
    missing: list[str] = []
    added: list[str] = []

    for path, saved_artifact in saved_map.items():
        if path not in current_map:
            missing.append(path)
        elif current_map[path]["sha256"] != saved_artifact["sha256"]:
            changed.append(path)
    for path in current_map:
        if path not in saved_map:
            added.append(path)

    return {
        "ok": not changed and not missing and not added,
        "changed": changed,
        "missing": missing,
        "added": added,
        "saved_artifact_count": len(saved_map),
        "current_artifact_count": len(current_map),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create or verify SPR proof manifests")
    parser.add_argument("root", help="audit/run folder")
    parser.add_argument("--verify", action="store_true", help="verify an existing proof_manifest.json")
    args = parser.parse_args(argv)
    try:
        if args.verify:
            print(json.dumps(verify_manifest(args.root), indent=2, sort_keys=True))
        else:
            target = write_manifest(args.root)
            print(f"Wrote proof manifest: {target}")
        return 0
    except Exception as exc:
        print(f"SPR_PROOF_ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
