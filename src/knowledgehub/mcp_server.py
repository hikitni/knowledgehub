from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .config import DEFAULT_CONFIG
from .service import KnowledgeService

mcp = FastMCP("KnowledgeHub", instructions="Read-only local project and document knowledge search")
_config_path = str(DEFAULT_CONFIG)


def _service() -> KnowledgeService:
    return KnowledgeService.from_path(_config_path)


@mcp.tool()
def kb_search(
    query: str,
    scopes: list[str] | None = None,
    project_id: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Search indexed knowledge and return traceable document/chunk references."""
    results = _service().search(query, scopes=scopes, project_id=project_id, limit=limit)
    return {"query": query, "count": len(results), "results": results}


@mcp.tool()
def kb_read(document_id: str, chunk_id: str | None = None) -> dict[str, Any]:
    """Read one indexed document or a specific indexed chunk."""
    return _service().read(document_id=document_id, chunk_id=chunk_id)


@mcp.tool()
def kb_project_context(project_path: str, limit: int = 20) -> dict[str, Any]:
    """Resolve an absolute project path to its indexed project documentation."""
    return _service().project_context(project_path, limit=limit)


@mcp.tool()
def kb_status() -> dict[str, Any]:
    """Return KnowledgeHub index health and last scan information."""
    return _service().status()


def run(config_path: str | Path | None = None) -> None:
    global _config_path
    _config_path = str(Path(config_path or os.environ.get("KNOWLEDGEHUB_CONFIG", DEFAULT_CONFIG)).expanduser().resolve())
    mcp.run(transport="stdio")


def main() -> None:
    run()


if __name__ == "__main__":
    main()
