from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RootConfig:
    path: Path
    project_id: str


@dataclass(frozen=True)
class KnowledgeBaseConfig:
    id: str
    name: str
    type: str
    enabled: bool
    roots: tuple[RootConfig, ...]
    include: tuple[str, ...]
    exclude: tuple[str, ...]


@dataclass(frozen=True)
class HubConfig:
    root: Path
    database: Path
    lock_dir: Path
    log_dir: Path
    timezone: str
    stale_lock_seconds: int = 21600


@dataclass(frozen=True)
class IndexingConfig:
    hash_algorithm: str = "sha256"
    max_file_size_mb: int = 50
    preserve_last_good_index_on_error: bool = True
    delete_grace_seconds: int = 10
    sensitive_scan_max_bytes: int = 2 * 1024 * 1024


@dataclass(frozen=True)
class AppConfig:
    path: Path
    hub: HubConfig
    indexing: IndexingConfig
    knowledge_bases: tuple[KnowledgeBaseConfig, ...]
    raw: dict[str, Any]

    def enabled_bases(self) -> tuple[KnowledgeBaseConfig, ...]:
        return tuple(kb for kb in self.knowledge_bases if kb.enabled)


@dataclass(frozen=True)
class ParsedDocument:
    title: str
    content: str
    file_type: str


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    heading: str | None
    heading_path: str | None
    content: str
    start_line: int
    end_line: int


@dataclass
class KnowledgeBaseStats:
    id: str
    discovered_count: int = 0
    added_count: int = 0
    updated_count: int = 0
    deleted_count: int = 0
    unchanged_count: int = 0
    skipped_count: int = 0
    error_count: int = 0


@dataclass
class RunReport:
    id: str
    scan_type: str
    started_at: str
    completed_at: str | None = None
    duration_seconds: float | None = None
    status: str = "running"
    discovered_count: int = 0
    added_count: int = 0
    updated_count: int = 0
    deleted_count: int = 0
    unchanged_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    dry_run: bool = False
    knowledge_bases: list[KnowledgeBaseStats] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    report_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["knowledge_bases"] = [asdict(item) for item in self.knowledge_bases]
        return data
