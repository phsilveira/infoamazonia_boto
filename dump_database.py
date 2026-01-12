"""Utility script to create a PostgreSQL dump using the configured DATABASE_URL.

Example:
    python dump_database.py --output backups/boto.sql

Requires `pg_dump` to be available on PATH. The script reads connection
information from `config.settings` so it always matches the application
configuration.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from collections.abc import Mapping
from urllib.parse import parse_qs

from sqlalchemy.engine.url import make_url

try:
    from config import settings
except ImportError as exc:  # pragma: no cover - misconfiguration guard
    raise SystemExit(f"Unable to import application settings: {exc}") from exc


def ensure_pg_dump_available(pg_dump_path: str) -> None:
    """Verify that the pg_dump executable exists before attempting a backup."""
    if shutil.which(pg_dump_path) is None:
        raise SystemExit(
            "pg_dump was not found on PATH. Install PostgreSQL client tools or "
            "provide the full path via --pg-dump-path."
        )


def build_pg_dump_command(args: argparse.Namespace, url) -> List[str]:
    """Compose the pg_dump command line based on settings and CLI options."""

    if not url.username or not url.database:
        raise SystemExit("DATABASE_URL must include both username and database name.")

    cmd = [
        args.pg_dump_path,
        "--host",
        url.host or "localhost",
        "--port",
        str(url.port or 5432),
        "--username",
        url.username,
        "--dbname",
        url.database,
        "--format",
        args.format,
        "--file",
        str(args.output.resolve()),
    ]

    if args.schema_only:
        cmd.append("--schema-only")
    if args.data_only:
        cmd.append("--data-only")

    if args.extra:
        cmd.extend(args.extra)

    return cmd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a PostgreSQL dump file.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("backups") / f"boto_dump_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.sql",
        help="Output path for the dump file (directories will be created if needed).",
    )
    parser.add_argument(
        "--format",
        choices=["plain", "custom", "directory", "tar"],
        default="plain",
        help="pg_dump output format.",
    )
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Dump only the schema (no data).",
    )
    parser.add_argument(
        "--data-only",
        action="store_true",
        help="Dump only the data (no schema).",
    )
    parser.add_argument(
        "--pg-dump-path",
        default="pg_dump",
        help="Name or path of the pg_dump executable.",
    )
    parser.add_argument(
        "database_url",
        nargs="?",
        help="Optional DATABASE_URL override. Defaults to the value in config.py settings.",
    )
    parser.add_argument(
        "extra",
        nargs=argparse.REMAINDER,
        default=[],
        help="Additional arguments passed directly to pg_dump (use after --).",
    )
    return parser.parse_args()


def _extract_sslmode(url) -> str | None:
    query = url.query
    if isinstance(query, Mapping):
        value = query.get("sslmode")
        if isinstance(value, (list, tuple)):
            return value[0]
        return value
    if isinstance(query, str):
        parsed = parse_qs(query)
        values = parsed.get("sslmode")
        if values:
            return values[0]
    return None


def main() -> int:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    ensure_pg_dump_available(args.pg_dump_path)

    database_url = args.database_url or settings.DATABASE_URL
    url = make_url(database_url)
    pgpassword = url.password or ""

    env = os.environ.copy()
    if pgpassword:
        env["PGPASSWORD"] = pgpassword

    sslmode = _extract_sslmode(url)
    if sslmode:
        env["PGSSLMODE"] = sslmode

    cmd = build_pg_dump_command(args, url)
    print("Running:", " ".join(cmd))

    result = subprocess.run(cmd, env=env, check=False)
    if result.returncode != 0:
        print(f"pg_dump exited with status {result.returncode}", file=sys.stderr)
        return result.returncode

    print(f"Database dump created at {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
