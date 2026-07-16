from __future__ import annotations

from knowledgehub.chunker import chunk_document
from knowledgehub.security import detect_sensitive_content


def test_markdown_heading_paths_and_explicit_chunks() -> None:
    chunks = chunk_document("# 产品\n背景\n## 功能\n消息流控制", "md")
    assert [chunk.heading_path for chunk in chunks] == ["产品", "产品 / 功能"]
    assert chunks[1].start_line == 3


def test_sensitive_detection_is_bounded_and_detects_credentials() -> None:
    assert detect_sensitive_content("普通项目知识", 1024) is None
    sample = "password = " + "super-" + "secret-value"
    assert detect_sensitive_content(sample, 1024) == "credential-field"
