from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .chunker import chunk_document
from .config import load_config
from .database import Database
from .models import (
    AppConfig,
    KnowledgeBaseConfig,
    KnowledgeBaseStats,
    RootConfig,
    RunReport,
)
from .parsers import ParseError, parse_document
from .security import detect_sensitive_content, reject_path

UTC_OFFSET_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


def now_iso() -> str:
    return datetime.now().astimezone().strftime(UTC_OFFSET_FORMAT)


def _safe_error(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {str(exc)[:300]}"


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _document_id(kb_id: str, real_path: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"knowledgehub:{kb_id}:{real_path}"))


def _chunk_id(document_id: str, ordinal: int, content_hash: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{document_id}:{ordinal}:{content_hash}"))


def _matches(relative: str, patterns: tuple[str, ...]) -> bool:
    normalized = relative.lstrip("./")
    for pattern in patterns:
        if fnmatch.fnmatch(normalized, pattern):
            return True
        # Glob users expect **/*.md to include root-level Markdown files too.
        if pattern.startswith("**/") and fnmatch.fnmatch(normalized, pattern[3:]):
            return True
    return False


def _under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


class SkipFile(RuntimeError):
    """A file is intentionally excluded without failing the scan."""


class Indexer:
    def __init__(self, config: AppConfig):
        self.config = config
        self.db = Database(config.hub.database)
        self.db.initialize()
        self._sync_knowledge_bases()

    @classmethod
    def from_path(cls, config_path: str | Path | None = None) -> "Indexer":
        return cls(load_config(config_path))

    def _sync_knowledge_bases(self) -> None:
        timestamp = now_iso()
        raw_hash = hashlib.sha256(
            json.dumps(self.config.raw, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        with self.db.transaction() as connection:
            for kb in self.config.knowledge_bases:
                connection.execute(
                    """
                    INSERT INTO knowledge_bases(id, name, type, enabled, config_hash, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                      name=excluded.name, type=excluded.type, enabled=excluded.enabled,
                      config_hash=excluded.config_hash, updated_at=excluded.updated_at
                    """,
                    (kb.id, kb.name, kb.type, int(kb.enabled), raw_hash, timestamp, timestamp),
                )

    def _selected_bases(self, scopes: list[str] | None) -> tuple[KnowledgeBaseConfig, ...]:
        enabled = self.config.enabled_bases()
        if not scopes:
            return enabled
        wanted = set(scopes)
        selected = tuple(kb for kb in enabled if kb.id in wanted)
        missing = wanted - {kb.id for kb in selected}
        if missing:
            raise ValueError(f"Unknown or disabled scope(s): {', '.join(sorted(missing))}")
        return selected

    def _enumerate(self, kb: KnowledgeBaseConfig, root: RootConfig) -> list[Path]:
        if not root.path.exists():
            return []
        files: list[Path] = []
        for current, dirs, names in os.walk(root.path, followlinks=False):
            current_path = Path(current)
            kept_dirs: list[str] = []
            for name in dirs:
                candidate = current_path / name
                rel = candidate.relative_to(root.path).as_posix() + "/"
                if candidate.is_symlink() or reject_path(candidate) or _matches(rel, kb.exclude):
                    continue
                kept_dirs.append(name)
            dirs[:] = kept_dirs
            for name in names:
                candidate = current_path / name
                if candidate.is_symlink() or not candidate.is_file():
                    continue
                relative = candidate.relative_to(root.path).as_posix()
                if reject_path(candidate):
                    continue
                if kb.include and not _matches(relative, kb.include):
                    continue
                if kb.exclude and _matches(relative, kb.exclude):
                    continue
                files.append(candidate)
        return sorted(files)

    def run(
        self,
        *,
        reconcile: bool,
        scopes: list[str] | None = None,
        dry_run: bool = False,
        report_path: str | Path | None = None,
    ) -> RunReport:
        started_monotonic = time.monotonic()
        report = RunReport(
            id=str(uuid.uuid4()),
            scan_type="reconcile" if reconcile else "scan",
            started_at=now_iso(),
            dry_run=dry_run,
        )
        selected = self._selected_bases(scopes)
        seen_paths: set[tuple[str, str]] = set()
        selected_roots: dict[str, list[Path]] = {}

        for kb in selected:
            stats = KnowledgeBaseStats(id=kb.id)
            report.knowledge_bases.append(stats)
            selected_roots[kb.id] = [root.path.resolve() for root in kb.roots]
            for root in kb.roots:
                if not root.path.exists():
                    self._error(report, stats, root.path, "root-not-found")
                    continue
                for path in self._enumerate(kb, root):
                    real_path = str(path.resolve())
                    seen_paths.add((kb.id, real_path))
                    stats.discovered_count += 1
                    report.discovered_count += 1
                    try:
                        outcome = self._index_one(kb, root, path, dry_run=dry_run)
                    except SkipFile as exc:
                        self._increment(report, stats, "skipped")
                        report.skipped.append({"path": str(path), "safe_message": str(exc)[:300]})
                        continue
                    except Exception as exc:
                        self._error(report, stats, path, _safe_error(exc))
                        continue
                    self._increment(report, stats, outcome)

        if reconcile:
            self._reconcile_deletions(
                selected_roots=selected_roots,
                seen_paths=seen_paths,
                report=report,
                dry_run=dry_run,
            )

        report.completed_at = now_iso()
        report.duration_seconds = round(time.monotonic() - started_monotonic, 3)
        report.status = "success" if report.error_count == 0 else "partial_failure"
        if report_path:
            destination = Path(report_path).expanduser().resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            report.report_path = str(destination)
            destination.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        if not dry_run:
            self.db.record_run(report.to_dict())
        return report

    def _increment(self, report: RunReport, stats: KnowledgeBaseStats, outcome: str) -> None:
        field = f"{outcome}_count"
        if not hasattr(report, field):
            raise ValueError(f"Unknown index outcome: {outcome}")
        setattr(report, field, getattr(report, field) + 1)
        setattr(stats, field, getattr(stats, field) + 1)

    def _error(
        self,
        report: RunReport,
        stats: KnowledgeBaseStats,
        path: Path,
        safe_message: str,
    ) -> None:
        report.error_count += 1
        stats.error_count += 1
        report.errors.append({"path": str(path), "safe_message": safe_message})

    def _existing(self, kb_id: str, real_path: str) -> Any:
        return self.db.query_one(
            "SELECT * FROM documents WHERE kb_id=? AND real_path=?", (kb_id, real_path)
        )

    def _index_one(
        self,
        kb: KnowledgeBaseConfig,
        root: RootConfig,
        path: Path,
        *,
        dry_run: bool,
    ) -> str:
        stat = path.stat()
        max_size = self.config.indexing.max_file_size_mb * 1024 * 1024
        if stat.st_size > max_size:
            raise SkipFile(f"file-too-large:{stat.st_size}")
        real_path = str(path.resolve())
        existing = self._existing(kb.id, real_path)
        if (
            existing
            and existing["size"] == stat.st_size
            and existing["mtime_ns"] == stat.st_mtime_ns
            and not existing["parse_error"]
        ):
            return "unchanged"

        content_hash = _hash_file(path)
        if (
            existing
            and existing["content_hash"] == content_hash
            and existing["status"] == "indexed"
            and not existing["parse_error"]
        ):
            if not dry_run:
                with self.db.transaction() as connection:
                    connection.execute(
                        """UPDATE documents SET size=?, mtime_ns=?, inode=?, missing_since=NULL,
                           parse_error=NULL, updated_at=? WHERE id=?""",
                        (stat.st_size, stat.st_mtime_ns, stat.st_ino, now_iso(), existing["id"]),
                    )
            return "unchanged"

        try:
            parsed = parse_document(path)
            sensitive_rule = detect_sensitive_content(
                parsed.content, self.config.indexing.sensitive_scan_max_bytes
            )
            if sensitive_rule:
                raise SkipFile(f"sensitive-content:{sensitive_rule}")
            chunks = chunk_document(parsed.content, parsed.file_type)
            if not chunks and parsed.content.strip():
                raise ParseError("Parser returned content but chunker produced no chunks")
        except SkipFile:
            raise
        except Exception as exc:
            if not dry_run:
                self._record_parse_error(
                    kb=kb,
                    root=root,
                    path=path,
                    stat=stat,
                    content_hash=content_hash,
                    existing=existing,
                    safe_message=_safe_error(exc),
                )
            raise

        outcome = "updated" if existing else "added"
        if dry_run:
            return outcome

        timestamp = now_iso()
        document_id = existing["id"] if existing else _document_id(kb.id, real_path)
        relative_path = path.resolve().relative_to(root.path.resolve()).as_posix()
        with self.db.transaction() as connection:
            connection.execute(
                "DELETE FROM chunks_fts WHERE document_id=?", (document_id,)
            )
            connection.execute("DELETE FROM chunks WHERE document_id=?", (document_id,))
            connection.execute(
                """
                INSERT INTO documents(
                    id, kb_id, project_id, absolute_path, real_path, relative_path,
                    file_type, title, size, mtime_ns, inode, content_hash, status,
                    parse_error, missing_since, indexed_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'indexed', NULL, NULL, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    project_id=excluded.project_id, absolute_path=excluded.absolute_path,
                    real_path=excluded.real_path, relative_path=excluded.relative_path,
                    file_type=excluded.file_type, title=excluded.title, size=excluded.size,
                    mtime_ns=excluded.mtime_ns, inode=excluded.inode,
                    content_hash=excluded.content_hash, status='indexed', parse_error=NULL,
                    missing_since=NULL, indexed_at=excluded.indexed_at,
                    updated_at=excluded.updated_at
                """,
                (
                    document_id, kb.id, root.project_id, str(path.resolve()), real_path,
                    relative_path, parsed.file_type, parsed.title, stat.st_size,
                    stat.st_mtime_ns, stat.st_ino, content_hash, timestamp, timestamp, timestamp,
                ),
            )
            for chunk in chunks:
                chunk_hash = _hash_text(chunk.content)
                chunk_id = _chunk_id(document_id, chunk.ordinal, chunk_hash)
                connection.execute(
                    """
                    INSERT INTO chunks(
                        id, document_id, ordinal, heading, heading_path, content,
                        start_line, end_line, content_hash, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk_id, document_id, chunk.ordinal, chunk.heading,
                        chunk.heading_path, chunk.content, chunk.start_line, chunk.end_line,
                        chunk_hash, timestamp, timestamp,
                    ),
                )
                connection.execute(
                    """INSERT INTO chunks_fts(
                        chunk_id, document_id, kb_id, project_id, title, heading, content
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        chunk_id, document_id, kb.id, root.project_id, parsed.title,
                        chunk.heading or "", chunk.content,
                    ),
                )
        return outcome

    def _record_parse_error(
        self,
        *,
        kb: KnowledgeBaseConfig,
        root: RootConfig,
        path: Path,
        stat: os.stat_result,
        content_hash: str,
        existing: Any,
        safe_message: str,
    ) -> None:
        timestamp = now_iso()
        real_path = str(path.resolve())
        document_id = existing["id"] if existing else _document_id(kb.id, real_path)
        relative_path = path.resolve().relative_to(root.path.resolve()).as_posix()
        with self.db.transaction() as connection:
            connection.execute(
                """
                INSERT INTO documents(
                    id, kb_id, project_id, absolute_path, real_path, relative_path,
                    file_type, title, size, mtime_ns, inode, content_hash, status,
                    parse_error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'error', ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    size=excluded.size, mtime_ns=excluded.mtime_ns, inode=excluded.inode,
                    parse_error=excluded.parse_error,
                    status=CASE WHEN documents.indexed_at IS NULL THEN 'error' ELSE documents.status END,
                    updated_at=excluded.updated_at
                """,
                (
                    document_id, kb.id, root.project_id, real_path, real_path, relative_path,
                    path.suffix.lower().lstrip("."), path.stem, stat.st_size, stat.st_mtime_ns,
                    stat.st_ino, content_hash, safe_message, timestamp, timestamp,
                ),
            )

    def _reconcile_deletions(
        self,
        *,
        selected_roots: dict[str, list[Path]],
        seen_paths: set[tuple[str, str]],
        report: RunReport,
        dry_run: bool,
    ) -> None:
        stats_by_kb = {item.id: item for item in report.knowledge_bases}
        candidates: list[Any] = []
        for kb_id, roots in selected_roots.items():
            for row in self.db.query_all("SELECT * FROM documents WHERE kb_id=?", (kb_id,)):
                path = Path(row["real_path"])
                if not any(_under(path, root) for root in roots):
                    continue
                if (kb_id, row["real_path"]) not in seen_paths:
                    candidates.append(row)
        if not candidates:
            return
        grace = self.config.indexing.delete_grace_seconds
        if grace and not dry_run:
            time.sleep(grace)
        for row in candidates:
            path = Path(row["real_path"])
            if path.exists():
                continue
            stats = stats_by_kb[row["kb_id"]]
            if not dry_run:
                with self.db.transaction() as connection:
                    connection.execute("DELETE FROM chunks_fts WHERE document_id=?", (row["id"],))
                    connection.execute("DELETE FROM documents WHERE id=?", (row["id"],))
            self._increment(report, stats, "deleted")

    def notify(self, path: str | Path, dry_run: bool = False) -> str:
        target = Path(path).expanduser().resolve()
        if not target.is_file():
            raise FileNotFoundError(target)
        path_rule = reject_path(target)
        if path_rule:
            raise PermissionError(f"Path rejected: {path_rule}")
        for kb in self.config.enabled_bases():
            for root in kb.roots:
                if _under(target, root.path.resolve()):
                    relative = target.relative_to(root.path.resolve()).as_posix()
                    if kb.include and not _matches(relative, kb.include):
                        raise ValueError(f"Path is not included by scope {kb.id}: {target}")
                    if kb.exclude and _matches(relative, kb.exclude):
                        raise ValueError(f"Path is excluded by scope {kb.id}: {target}")
                    return self._index_one(kb, root, target, dry_run=dry_run)
        raise ValueError(f"Path does not belong to an enabled knowledge root: {target}")
