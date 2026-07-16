from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .config import DEFAULT_CONFIG, ConfigError, load_config
from .database import Database
from .indexer import Indexer
from .service import KnowledgeService


def _json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _add_config(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to YAML configuration")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kb", description="KnowledgeHub CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Initialize the SQLite index")
    _add_config(init)

    for name in ("scan", "reconcile"):
        command = sub.add_parser(name, help=f"Run {name}")
        _add_config(command)
        command.add_argument("--all", action="store_true", help="Select all enabled scopes")
        command.add_argument("--scope", action="append", default=[], help="Knowledge base id")
        command.add_argument("--dry-run", action="store_true")
        command.add_argument("--report-json")

    notify = sub.add_parser("notify", help="Index one changed file")
    _add_config(notify)
    notify.add_argument("path")
    notify.add_argument("--dry-run", action="store_true")

    search = sub.add_parser("search", help="Full-text search")
    _add_config(search)
    search.add_argument("query")
    search.add_argument("--scope", action="append", default=[])
    search.add_argument("--project-id")
    search.add_argument("--limit", type=int, default=10)

    read = sub.add_parser("read", help="Read indexed chunks")
    _add_config(read)
    read.add_argument("--document-id", required=True)
    read.add_argument("--chunk-id")

    context = sub.add_parser("project-context", help="Resolve project knowledge")
    _add_config(context)
    context.add_argument("project_path")
    context.add_argument("--limit", type=int, default=20)

    status = sub.add_parser("status", help="Index health")
    _add_config(status)
    status.add_argument("--json", action="store_true")

    config = sub.add_parser("config", help="Configuration operations")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    validate = config_sub.add_parser("validate")
    _add_config(validate)

    mcp = sub.add_parser("mcp", help="Run read-only MCP server over stdio")
    _add_config(mcp)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "config" and args.config_command == "validate":
            config = load_config(args.config)
            _json({"valid": True, "config": str(config.path), "enabled": [kb.id for kb in config.enabled_bases()]})
            return 0
        if args.command == "init":
            config = load_config(args.config)
            Database(config.hub.database).initialize()
            Indexer(config)
            _json({"initialized": True, "database": str(config.hub.database)})
            return 0
        if args.command in {"scan", "reconcile"}:
            scopes = None if args.all or not args.scope else args.scope
            report = Indexer.from_path(args.config).run(
                reconcile=args.command == "reconcile",
                scopes=scopes,
                dry_run=args.dry_run,
                report_path=args.report_json,
            )
            _json(report.to_dict())
            return 0 if report.error_count == 0 else 3
        if args.command == "notify":
            outcome = Indexer.from_path(args.config).notify(args.path, dry_run=args.dry_run)
            _json({"path": str(Path(args.path).resolve()), "outcome": outcome, "dry_run": args.dry_run})
            return 0
        if args.command == "search":
            results = KnowledgeService.from_path(args.config).search(
                args.query,
                scopes=args.scope or None,
                project_id=args.project_id,
                limit=args.limit,
            )
            _json({"query": args.query, "count": len(results), "results": results})
            return 0
        if args.command == "read":
            _json(KnowledgeService.from_path(args.config).read(document_id=args.document_id, chunk_id=args.chunk_id))
            return 0
        if args.command == "project-context":
            _json(KnowledgeService.from_path(args.config).project_context(args.project_path, args.limit))
            return 0
        if args.command == "status":
            data = KnowledgeService.from_path(args.config).status()
            _json(data) if args.json else print(
                f"{data['status']}: {data['documents']} documents, {data['chunks']} chunks, "
                f"last success={data['last_successful_scan'] or '-'}"
            )
            return 0
        if args.command == "mcp":
            from .mcp_server import run

            run(args.config)
            return 0
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except PermissionError as exc:
        print(f"Security rule rejected content: {exc}", file=sys.stderr)
        return 5
    except Exception as exc:
        print(f"KnowledgeHub error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 4
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
