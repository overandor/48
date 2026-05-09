from pathlib import Path

from spr.audit import AuditRun, read_audit_summary
from spr.cli import run_protocol


def test_audit_run_writes_and_seals_manifest(tmp_path):
    audit = AuditRun(root=tmp_path, run_id="test_run")
    audit.start()
    audit.write_text("source.spr", "demo")
    audit.write_json("plan.json", {"ok": True})
    audit.seal({"mode": "test"})

    summary = read_audit_summary(tmp_path / "test_run")

    assert "source.spr" in summary["files"]
    assert "plan.json" in summary["files"]
    assert "proof_manifest.json" in summary["files"]
    assert summary["proof_manifest"]["extra"]["mode"] == "test"
    assert "source.spr" in summary["proof_manifest"]["artifacts"]


def test_run_protocol_dry_run_creates_expected_audit_artifacts(tmp_path):
    spr_file = tmp_path / "hot_users.spr"
    spr_file.write_text(
        '''policy {
  optimize: latency > cost
  deterministic: true
  allow database[db.main]
  allow filesystem[*]
  deny network[*]
  deny shell[*]
}

users := source @db.main "select id, email, score from users"
hot := users -> filter score > 0.8 -> project [id, email, score]
write! hot @file:"hot_users.jsonl"
''',
        encoding="utf-8",
    )

    run_dir = run_protocol(spr_file, dry_run=True, audit_dir=tmp_path / ".spr_runs")

    expected = {
        "source.spr",
        "parsed_ir.json",
        "graph.json",
        "policy_result.json",
        "plan.json",
        "lowered_sql.sql",
        "lowered_python.py",
        "outputs.json",
        "final_report.md",
        "proof_manifest.json",
    }
    actual = {p.name for p in Path(run_dir).iterdir() if p.is_file()}
    assert expected.issubset(actual)
