from __future__ import annotations

import json
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from knowledgehub.cli import main


def test_mcp_stdio_lists_read_only_tools_and_queries_real_index(tmp_path: Path, capsys) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    (root / "knowledge.md").write_text("# MCP 验证\n\nKnowledgeHub MCP 协议测试。\n", encoding="utf-8")

    config = tmp_path / "knowledge-bases.yaml"
    database = tmp_path / "knowledge.db"
    config.write_text(
        f"""version: 1
hub:
  root: {tmp_path}
  database: {database}
  lock_dir: {tmp_path / 'run'}
  log_dir: {tmp_path / 'logs'}
knowledge_bases:
  test:
    name: Test
    enabled: true
    type: document-vault
    roots:
      - path: {root}
        project_id: test-project
    include: [\"**/*.md\"]
    exclude: []
""",
        encoding="utf-8",
    )

    assert main(["reconcile", "--all", "--config", str(config)]) == 0
    capsys.readouterr()

    server = StdioServerParameters(
        command=str(Path(__file__).parents[1] / ".venv" / "bin" / "kb"),
        args=["mcp", "--config", str(config)],
        cwd=str(Path(__file__).parents[1]),
    )

    async def exercise() -> None:
        async with stdio_client(server) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert {tool.name for tool in tools.tools} == {
                    "kb_search",
                    "kb_read",
                    "kb_project_context",
                    "kb_status",
                }

                status = await session.call_tool("kb_status", {})
                assert status.isError is False
                status_data = json.loads(status.content[0].text)
                assert status_data["documents"] == 1

                search = await session.call_tool("kb_search", {"query": "KnowledgeHub", "limit": 5})
                assert search.isError is False
                search_data = json.loads(search.content[0].text)
                assert search_data["count"] == 1
                assert search_data["results"][0]["project_id"] == "test-project"

    anyio.run(exercise)
