from __future__ import annotations

from pathlib import Path

from knowledgehub.indexer import Indexer
from knowledgehub.service import KnowledgeService

from conftest import write_config


def test_reconcile_indexes_updates_searches_and_deletes(tmp_path: Path) -> None:
    daily = tmp_path / "daily"
    business = tmp_path / "business"
    daily.mkdir()
    business.mkdir()
    note = daily / "note.md"
    note.write_text("# 每日记录\n\n半双工消息流需要严格控制。\n", encoding="utf-8")
    (business / "README.md").write_text("# 行情项目\n\n业务开发架构说明。\n", encoding="utf-8")
    config = write_config(tmp_path, {"daily-work": daily, "business-dev": business})

    indexer = Indexer.from_path(config)
    first = indexer.run(reconcile=True)
    assert first.status == "success"
    assert first.added_count == 2

    service = KnowledgeService.from_path(config)
    long_results = service.search("半双工消息流", scopes=["daily-work"])
    assert len(long_results) == 1
    assert long_results[0]["kb_id"] == "daily-work"
    assert long_results[0]["chunk_id"]

    short_results = service.search("行情", scopes=["business-dev"])
    assert len(short_results) == 1
    assert short_results[0]["project_id"] == "business-dev-project"
    assert service.search("行情", scopes=["daily-work"]) == []

    note.write_text("# 每日记录\n\n半双工消息流已经更新为第二版。\n", encoding="utf-8")
    second = indexer.run(reconcile=False, scopes=["daily-work"])
    assert second.updated_count == 1
    assert "第二版" in service.search("半双工消息流")[0]["snippet"]

    note.unlink()
    third = indexer.run(reconcile=True, scopes=["daily-work"])
    assert third.deleted_count == 1
    assert service.search("半双工消息流") == []


def test_parse_failure_preserves_last_good_index_and_retries(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    note = root / "safe.md"
    note.write_text("# 安全文档\n\n旧版本可检索内容。\n", encoding="utf-8")
    config = write_config(tmp_path, {"daily-work": root})
    indexer = Indexer.from_path(config)
    assert indexer.run(reconcile=True).added_count == 1

    note.write_text("# 错误版本\npassword = 'this-is-a-secret-password'\n", encoding="utf-8")
    failed = indexer.run(reconcile=False)
    assert failed.error_count == 0
    assert failed.skipped_count == 1
    service = KnowledgeService.from_path(config)
    assert len(service.search("旧版本可检索内容")) == 1
    assert service.status()["parse_errors"] == 0

    note.write_text("# 恢复版本\n\n恢复后的知识内容。\n", encoding="utf-8")
    recovered = indexer.run(reconcile=False)
    assert recovered.updated_count == 1
    assert service.search("旧版本可检索内容") == []
    assert len(service.search("恢复后的知识内容")) == 1


def test_project_context_resolves_registered_root(tmp_path: Path) -> None:
    project = tmp_path / "project"
    docs = project / "docs"
    docs.mkdir(parents=True)
    (docs / "architecture.md").write_text("# 架构\n\n项目背景与架构。", encoding="utf-8")
    config = write_config(tmp_path, {"business-dev": project})
    Indexer.from_path(config).run(reconcile=True)

    context = KnowledgeService.from_path(config).project_context(project / "src")
    assert context["matched"] is True
    assert context["project_id"] == "business-dev-project"
    assert context["documents"][0]["title"] == "架构"
