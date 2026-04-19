from __future__ import annotations

from pathlib import Path
import tomllib


def test_sniffer_scripts_exist() -> None:
    for name in ("sniff-start", "sniff-stop"):
        path = Path("scripts") / name
        assert path.is_file(), f"missing script: {path}"


def test_mise_exposes_sniffer_scripts() -> None:
    config = tomllib.loads(Path("mise.toml").read_text())
    tasks = config["tasks"]

    assert tasks["sniff-start"]["run"] == "./scripts/sniff-start"
    assert tasks["sniff-stop"]["run"] == "./scripts/sniff-stop"
