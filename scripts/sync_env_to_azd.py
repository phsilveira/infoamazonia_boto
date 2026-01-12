#!/usr/bin/env python3
"""Sync key/value pairs from a .env file into an azd environment."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable

from dotenv import dotenv_values


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Load secrets from a dotenv file and run `azd env set` for each key. "
            "Use this to keep Azure Developer CLI environments in sync with your local .env."
        )
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help=r"Path to the dotenv file to read (defaults to ./.env).",
    )
    parser.add_argument(
        "--environment",
        dest="environment",
        default=None,
        help=(
            "Name of the azd environment to target. If omitted, the value is read from "
            "AZD_ENV_NAME or the currently selected environment."
        ),
    )
    parser.add_argument(
        "--skip",
        nargs="*",
        default=[],
        metavar="KEY",
        help="Space-separated list of keys to skip (e.g. --skip DATABASE_URL REDIS_PASSWORD).",
    )
    parser.add_argument(
        "--only",
        nargs="*",
        default=None,
        metavar="KEY",
        help="If provided, restrict syncing to these keys only.",
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Set keys even when the value is blank (default: skip empty values).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the azd commands instead of executing them.",
    )
    return parser.parse_args()


def ensure_env_selected(explicit_env: str | None) -> str:
    if explicit_env:
        return explicit_env

    env_from_var = os.environ.get("AZD_ENV_NAME") or os.environ.get("AZURE_ENV_NAME")
    if env_from_var:
        return env_from_var

    # Fall back to `azd env get-values --output json` to detect the currently selected environment.
    try:
        result = subprocess.run(
            ["azd", "env", "list", "--output", "json"],
            capture_output=True,
            check=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise SystemExit("azd CLI is not installed or not on PATH.") from exc
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"Failed to list azd environments: {exc.stderr}") from exc

    import json

    envs = json.loads(result.stdout or "[]")
    selected = next((env for env in envs if env.get("isDefault")), None)
    if not selected:
        raise SystemExit(
            "No azd environment selected. Run `azd env select <name>` or pass --environment."
        )
    return selected["name"]


def iter_key_values(env_file: Path) -> Iterable[tuple[str, str | None]]:
    if not env_file.exists():
        raise SystemExit(f"Env file not found: {env_file}")
    values = dotenv_values(env_file)
    if not values:
        raise SystemExit(f"Env file is empty or unreadable: {env_file}")
    return values.items()


def run_command(cmd: list[str], dry_run: bool) -> None:
    printable = " ".join(cmd)
    if dry_run:
        print(f"DRY RUN: {printable}")
        return

    result = subprocess.run(cmd, text=True)
    if result.returncode != 0:
        raise SystemExit(f"Command failed ({result.returncode}): {printable}")


def main() -> None:
    args = parse_args()
    target_env = ensure_env_selected(args.environment)

    skip = set(args.skip or [])
    allowlist = set(args.only or []) if args.only else None

    for key, value in iter_key_values(args.env_file):
        if key is None:
            continue
        if key in skip:
            continue
        if allowlist is not None and key not in allowlist:
            continue
        if (value is None or value == "") and not args.allow_empty:
            continue

        azd_command = [
            "azd",
            "env",
            "set",
            key,
            value or "",
            "--environment",
            target_env,
        ]
        run_command(azd_command, args.dry_run)
        print(f"Set {key} in azd environment '{target_env}'")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
