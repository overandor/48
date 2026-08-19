from spr.proof import build_manifest, verify_manifest, write_manifest


def test_build_manifest_hashes_files(tmp_path):
    (tmp_path / "a.txt").write_text("alpha", encoding="utf-8")
    (tmp_path / "b.txt").write_text("beta", encoding="utf-8")

    manifest = build_manifest(tmp_path)

    assert manifest.artifact_count == 2
    assert {a.path for a in manifest.artifacts} == {"a.txt", "b.txt"}
    assert all(a.sha256.startswith("sha256:") for a in manifest.artifacts)


def test_verify_manifest_detects_change(tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("alpha", encoding="utf-8")
    write_manifest(tmp_path)

    assert verify_manifest(tmp_path)["ok"] is True

    target.write_text("changed", encoding="utf-8")
    result = verify_manifest(tmp_path)

    assert result["ok"] is False
    assert result["changed"] == ["a.txt"]
