from __future__ import annotations

from pathlib import Path

import yaml


def write_config(tmp_path: Path, roots: dict[str, Path], *, delete_grace: int = 0) -> Path:
    config = {
        "version": 1,
        "hub": {
            "root": str(tmp_path / "hub"),
            "database": str(tmp_path / "hub/index/knowledge.db"),
            "lock_dir": str(tmp_path / "hub/run"),
            "log_dir": str(tmp_path / "hub/logs"),
            "timezone": "Asia/Shanghai",
            "stale_lock_seconds": 60,
        },
        "indexing": {
            "hash_algorithm": "sha256",
            "max_file_size_mb": 5,
            "preserve_last_good_index_on_error": True,
            "delete_grace_seconds": delete_grace,
            "sensitive_scan_max_bytes": 1024 * 1024,
        },
        "knowledge_bases": {
            kb_id: {
                "name": kb_id,
                "enabled": True,
                "type": "document-vault",
                "roots": [{"path": str(root), "project_id": f"{kb_id}-project"}],
                "include": ["**/*.md", "**/*.txt", "**/*.json"],
                "exclude": ["**/.git/**", "**/.env*", "**/*secret*"],
            }
            for kb_id, root in roots.items()
        },
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path
