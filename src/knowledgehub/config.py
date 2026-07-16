from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from .models import (
    AppConfig,
    HubConfig,
    IndexingConfig,
    KnowledgeBaseConfig,
    RootConfig,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = Path(
    os.environ.get(
        "KNOWLEDGEHUB_CONFIG",
        str(PROJECT_ROOT / "config" / "knowledge-bases.yaml"),
    )
)


class ConfigError(ValueError):
    pass


def _required(mapping: dict[str, Any], key: str, section: str) -> Any:
    if key not in mapping:
        raise ConfigError(f"Missing required key {section}.{key}")
    return mapping[key]


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(path or DEFAULT_CONFIG).expanduser().resolve()
    if not config_path.is_file():
        raise ConfigError(f"Config file not found: {config_path}")
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML: {exc}") from exc
    if raw.get("version") != 1:
        raise ConfigError("Only configuration version 1 is supported")

    hub_raw = _required(raw, "hub", "root")
    indexing_raw = raw.get("indexing", {})
    hub = HubConfig(
        root=Path(_required(hub_raw, "root", "hub")).expanduser().resolve(),
        database=Path(_required(hub_raw, "database", "hub")).expanduser().resolve(),
        lock_dir=Path(_required(hub_raw, "lock_dir", "hub")).expanduser().resolve(),
        log_dir=Path(_required(hub_raw, "log_dir", "hub")).expanduser().resolve(),
        timezone=str(hub_raw.get("timezone", "Asia/Shanghai")),
        stale_lock_seconds=int(hub_raw.get("stale_lock_seconds", 21600)),
    )
    indexing = IndexingConfig(
        hash_algorithm=str(indexing_raw.get("hash_algorithm", "sha256")),
        max_file_size_mb=int(indexing_raw.get("max_file_size_mb", 50)),
        preserve_last_good_index_on_error=bool(
            indexing_raw.get("preserve_last_good_index_on_error", True)
        ),
        delete_grace_seconds=max(0, int(indexing_raw.get("delete_grace_seconds", 10))),
        sensitive_scan_max_bytes=max(
            1024, int(indexing_raw.get("sensitive_scan_max_bytes", 2 * 1024 * 1024))
        ),
    )
    if indexing.hash_algorithm != "sha256":
        raise ConfigError("V1 supports only sha256")

    bases_raw = _required(raw, "knowledge_bases", "root")
    if not isinstance(bases_raw, dict) or not bases_raw:
        raise ConfigError("knowledge_bases must be a non-empty mapping")
    bases: list[KnowledgeBaseConfig] = []
    for kb_id, item in bases_raw.items():
        if not isinstance(item, dict):
            raise ConfigError(f"knowledge_bases.{kb_id} must be a mapping")
        roots: list[RootConfig] = []
        for index, root in enumerate(item.get("roots", [])):
            if not isinstance(root, dict) or "path" not in root:
                raise ConfigError(f"knowledge_bases.{kb_id}.roots[{index}] is invalid")
            root_path = Path(root["path"]).expanduser().resolve()
            project_id = str(root.get("project_id") or root_path.name)
            roots.append(RootConfig(root_path, project_id))
        if bool(item.get("enabled", True)) and not roots:
            raise ConfigError(f"Enabled knowledge base {kb_id} has no roots")
        bases.append(
            KnowledgeBaseConfig(
                id=str(kb_id),
                name=str(item.get("name", kb_id)),
                type=str(item.get("type", "document-vault")),
                enabled=bool(item.get("enabled", True)),
                roots=tuple(roots),
                include=tuple(str(v) for v in item.get("include", ["**/*.md"])),
                exclude=tuple(str(v) for v in item.get("exclude", [])),
            )
        )

    return AppConfig(
        path=config_path,
        hub=hub,
        indexing=indexing,
        knowledge_bases=tuple(bases),
        raw=raw,
    )
