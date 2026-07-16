from __future__ import annotations

import json
from pathlib import Path

from knowledgehub.cli import main
from knowledgehub.config import load_config

from conftest import write_config


def test_config_and_cli_roundtrip(tmp_path: Path, capsys) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    (root / "note.md").write_text("# CLI\n\n命令行检索内容。", encoding="utf-8")
    config = write_config(tmp_path, {"daily-work": root})

    loaded = load_config(config)
    assert loaded.enabled_bases()[0].id == "daily-work"
    assert main(["config", "validate", "--config", str(config)]) == 0
    assert main(["init", "--config", str(config)]) == 0
    assert main(["reconcile", "--all", "--config", str(config)]) == 0
    assert main(["search", "命令行检索", "--config", str(config)]) == 0
    output = capsys.readouterr().out
    assert '"count": 1' in output


def test_dry_run_writes_report_without_mutating_index(tmp_path: Path, capsys) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    (root / "note.md").write_text("# Dry Run\n\n预览扫描。", encoding="utf-8")
    config = write_config(tmp_path, {"daily-work": root})
    report = tmp_path / "report.json"

    assert main([
        "reconcile", "--all", "--dry-run", "--config", str(config),
        "--report-json", str(report),
    ]) == 0
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["dry_run"] is True
    assert data["added_count"] == 1
    assert main(["search", "预览扫描", "--config", str(config)]) == 0
    search = capsys.readouterr().out
    assert '"count": 0' in search
