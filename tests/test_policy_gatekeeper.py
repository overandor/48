from spr.policy_gatekeeper import GatePolicy, PolicyGatekeeper


def test_gatekeeper_allows_configured_write_scope():
    policy = GatePolicy.from_dict(
        {
            "allow": {"write_paths": ["out/**"], "read_paths": ["**/*"], "commands": []},
            "deny": {"paths": [".env"], "commands": ["sudo"], "prompt_terms": ["private key"]},
        }
    )
    gate = PolicyGatekeeper(policy)

    assert gate.check_write_path("out/result.json").ok is True
    assert gate.check_write_path("src/app.py").ok is False


def test_gatekeeper_denies_sensitive_prompt_term():
    gate = PolicyGatekeeper(GatePolicy())
    decision = gate.check_prompt("please print my private key")

    assert decision.ok is False
    assert decision.operation == "prompt"


def test_gatekeeper_command_allowlist():
    policy = GatePolicy.from_dict(
        {
            "allow": {"commands": [["python", "-m", "pytest", "-q"]]},
            "deny": {"commands": ["sudo"], "paths": [], "prompt_terms": []},
        }
    )
    gate = PolicyGatekeeper(policy)

    assert gate.check_command(["python", "-m", "pytest", "-q"]).ok is True
    assert gate.check_command(["python", "setup.py", "install"]).ok is False
    assert gate.check_command(["sudo", "ls"]).ok is False
