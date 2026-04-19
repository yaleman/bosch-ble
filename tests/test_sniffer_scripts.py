from __future__ import annotations

from pathlib import Path
import tomllib


def test_sniffer_scripts_exist() -> None:
    for name in ("sniff-start", "sniff-stop", "sniff-copy"):
        path = Path("scripts") / name
        assert path.is_file(), f"missing script: {path}"


def test_mise_exposes_sniffer_scripts() -> None:
    config = tomllib.loads(Path("mise.toml").read_text())
    tasks = config["tasks"]

    assert tasks["sniff-start"]["run"] == "./scripts/sniff-start"
    assert tasks["sniff-stop"]["run"] == "./scripts/sniff-stop"
    assert tasks["sniff-copy"]["run"] == "./scripts/sniff-copy"


def test_sniffer_scripts_use_remote_host_environment_variable() -> None:
    for name in ("sniff-start", "sniff-stop", "sniff-copy"):
        content = (Path("scripts") / name).read_text()
        assert "REMOTE_HOST" in content
        assert "m710qa.local" not in content
