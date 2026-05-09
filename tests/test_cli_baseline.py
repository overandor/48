import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args):
    return subprocess.run(
        [sys.executable, str(ROOT / "semantic_protocol_runtime.py"), *args],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        timeout=20,
    )


def test_cli_help_runs():
    proc = run_cli("--help")
    assert proc.returncode == 0
    assert "usage" in proc.stdout.lower()


def test_cli_explain_hot_users_example_runs():
    proc = run_cli("explain", "examples/hot_users.spr")
    assert proc.returncode == 0
    combined = proc.stdout + proc.stderr
    assert "hot" in combined
    assert "policy" in combined.lower() or "plan" in combined.lower()


def test_cli_denied_network_example_fails():
    proc = run_cli("explain", "examples/denied_network.spr")
    assert proc.returncode != 0
    combined = proc.stdout + proc.stderr
    assert "denied" in combined.lower() or "policy" in combined.lower()
