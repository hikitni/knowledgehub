from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import load_config
from .database import Database
from .models import AppConfig


def _scope_clause(scopes: list[str] | None, parameters: list[Any]) -> str:
    if not scopes:
        return ""
    placeholders = ",".join("?" for _ in scopes)
    parameters.extend(scopes)
    return f" AND d.kb_id IN ({placeholders})"


class KnowledgeService:
    def __init__(self, config: AppConfig):
        self.config = config
        self.db = Database(config.hub.database)
        self.db.initialize()

    @classmethod
    def from_path(cls, config_path: str | Path | None = None) -> "KnowledgeService":
        return cls(load_config(config_path))

    def search(
        self,
        query: str,
        *,
        scopes: list[str] | None = None,
        project_id: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        query = query.strip()
        if not query:
            raise ValueError("query must not be empty")
        limit = max(1, min(int(limit), 100))
        parameters: list[Any] = []
        scope_sql = _scope_clause(scopes, parameters)
        project_sql = ""
        if project_id:
            project_sql = " AND d.project_id=?"
            parameters.append(project_id)

        # FTS5 trigram cannot reliably answer one- and two-character queries.
        # Use a bounded LIKE fallback for those cases so Chinese short terms work.
        if len(query) < 3:
            like = f"%{query}%"
            sql = f"""
                SELECT d.kb_id, d.project_id, d.id AS document_id, c.id AS chunk_id,
                       d.absolute_path, d.title, c.heading_path, c.start_line, c.end_line,
                       c.content, 0.0 AS rank
                FROM chunks c
                JOIN documents d ON d.id=c.document_id
                WHERE (c.content LIKE ? OR d.title LIKE ? OR COALESCE(c.heading, '') LIKE ?)
                  {scope_sql} {project_sql}
                ORDER BY d.updated_at DESC, c.ordinal ASC
                LIMIT ?
            """
            rows = self.db.query_all(sql, (like, like, like, *parameters, limit))
        else:
            # Treat the user's text as a phrase instead of exposing raw FTS syntax.
            fts_query = '"' + query.replace('"', '""') + '"'
            sql = f"""
                SELECT d.kb_id, d.project_id, d.id AS document_id,
                       c.id AS chunk_id, d.absolute_path, d.title,
                       c.heading_path, c.start_line, c.end_line,
                       snippet(chunks_fts, 6, '[', ']', '…', 32) AS snippet,
                       c.content, bm25(chunks_fts) AS rank
                FROM chunks_fts
                JOIN chunks c ON c.id=chunks_fts.chunk_id
                JOIN documents d ON d.id=c.document_id
                WHERE chunks_fts MATCH ? {scope_sql} {project_sql}
                ORDER BY rank
                LIMIT ?
            """
            rows = self.db.query_all(sql, (fts_query, *parameters, limit))

        results: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            content = item.pop("content", "")
            if not item.get("snippet"):
                position = content.lower().find(query.lower())
                start = max(0, position - 120) if position >= 0 else 0
                item["snippet"] = content[start : start + 360]
            results.append(item)
        return results

    def read(
        self,
        *,
        document_id: str,
        chunk_id: str | None = None,
    ) -> dict[str, Any]:
        params: list[Any] = [document_id]
        chunk_sql = ""
        if chunk_id:
            chunk_sql = " AND c.id=?"
            params.append(chunk_id)
        rows = self.db.query_all(
            f"""
            SELECT d.kb_id, d.project_id, d.id AS document_id, d.absolute_path,
                   d.title, d.file_type, d.content_hash, d.indexed_at,
                   c.id AS chunk_id, c.ordinal, c.heading, c.heading_path,
                   c.start_line, c.end_line, c.content
            FROM documents d
            LEFT JOIN chunks c ON c.document_id=d.id
            WHERE d.id=? {chunk_sql}
            ORDER BY c.ordinal
            """,
            tuple(params),
        )
        if not rows:
            raise KeyError(f"Document or chunk not found: {document_id}/{chunk_id or '*'}")
        first = rows[0]
        return {
            "kb_id": first["kb_id"],
            "project_id": first["project_id"],
            "document_id": first["document_id"],
            "absolute_path": first["absolute_path"],
            "title": first["title"],
            "file_type": first["file_type"],
            "content_hash": first["content_hash"],
            "indexed_at": first["indexed_at"],
            "chunks": [
                {
                    "chunk_id": row["chunk_id"],
                    "ordinal": row["ordinal"],
                    "heading": row["heading"],
                    "heading_path": row["heading_path"],
                    "start_line": row["start_line"],
                    "end_line": row["end_line"],
                    "content": row["content"],
                }
                for row in rows
                if row["chunk_id"] is not None
            ],
        }

    def project_context(self, project_path: str | Path, limit: int = 20) -> dict[str, Any]:
        target = Path(project_path).expanduser().resolve()
        matches: list[tuple[int, str, str]] = []
        for kb in self.config.enabled_bases():
            for root in kb.roots:
                try:
                    target.relative_to(root.path.resolve())
                except ValueError:
                    continue
                matches.append((len(root.path.parts), kb.id, root.project_id))
        if not matches:
            return {"project_path": str(target), "matched": False, "documents": []}
        _, kb_id, project_id = sorted(matches, reverse=True)[0]
        rows = self.db.query_all(
            """
            SELECT d.id AS document_id, d.title, d.absolute_path, d.updated_at,
                   c.id AS chunk_id, c.heading_path, c.start_line, c.end_line, c.content
            FROM documents d
            LEFT JOIN chunks c ON c.document_id=d.id AND c.ordinal=0
            WHERE d.kb_id=? AND d.project_id=? AND d.status='indexed'
            ORDER BY d.updated_at DESC
            LIMIT ?
            """,
            (kb_id, project_id, max(1, min(int(limit), 100))),
        )
        return {
            "project_path": str(target),
            "matched": True,
            "kb_id": kb_id,
            "project_id": project_id,
            "documents": [
                {
                    "document_id": row["document_id"],
                    "chunk_id": row["chunk_id"],
                    "title": row["title"],
                    "absolute_path": row["absolute_path"],
                    "heading_path": row["heading_path"],
                    "start_line": row["start_line"],
                    "end_line": row["end_line"],
                    "excerpt": (row["content"] or "")[:800],
                    "updated_at": row["updated_at"],
                }
                for row in rows
            ],
        }

    def status(self) -> dict[str, Any]:
        counts = self.db.query_one(
            """SELECT
                 (SELECT COUNT(*) FROM documents WHERE status='indexed') AS documents,
                 (SELECT COUNT(*) FROM chunks) AS chunks,
                 (SELECT COUNT(*) FROM knowledge_bases WHERE enabled=1) AS knowledge_bases,
                 (SELECT COUNT(*) FROM documents WHERE parse_error IS NOT NULL) AS parse_errors
            """
        )
        last = self.db.query_one(
            """SELECT completed_at, status, error_count FROM scan_runs
               ORDER BY started_at DESC LIMIT 1"""
        )
        last_success = self.db.query_one(
            """SELECT completed_at FROM scan_runs WHERE status='success'
               ORDER BY started_at DESC LIMIT 1"""
        )
        health = "healthy"
        if last and last["status"] != "success":
            health = "degraded"
        return {
            "status": health,
            "last_scan": dict(last) if last else None,
            "last_successful_scan": last_success["completed_at"] if last_success else None,
            "documents": counts["documents"] if counts else 0,
            "chunks": counts["chunks"] if counts else 0,
            "knowledge_bases": counts["knowledge_bases"] if counts else 0,
            "parse_errors": counts["parse_errors"] if counts else 0,
            "database": str(self.config.hub.database),
            "config": str(self.config.path),
        }
