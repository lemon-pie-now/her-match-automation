"""Export private sources, update the GitHub secret, and refresh events."""
from __future__ import annotations

import argparse
import base64
import shutil
import subprocess

from export_sources import (
    DEFAULT_OUTPUT,
    DEFAULT_WORKBOOK,
    read_source_rows,
    write_sources_csv,
)


SECRET_NAME = "SOURCES_CSV_BASE64"
WORKFLOW_FILE = "update-events.yml"


def require_github_cli() -> str:
    github_cli = shutil.which("gh")

    if github_cli is None:
        raise RuntimeError(
            "GitHub CLI is not installed. Install it from "
            "https://cli.github.com/ and run `gh auth login`."
        )

    return github_cli


def run_command(
    command: list[str],
    *,
    input_bytes: bytes | None = None,
) -> None:
    subprocess.run(
        command,
        input=input_bytes,
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Export private calendar sources and synchronize them with "
            "GitHub Actions."
        )
    )
    parser.add_argument(
        "--no-run",
        action="store_true",
        help="Update the secret without starting the workflow.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and export locally without changing GitHub.",
    )
    arguments = parser.parse_args()

    rows = read_source_rows(DEFAULT_WORKBOOK)
    write_sources_csv(rows, DEFAULT_OUTPUT)
    print(f"Exported {len(rows)} source(s) to {DEFAULT_OUTPUT}.")

    if arguments.dry_run:
        print("Dry run complete; GitHub was not changed.")
        return

    github_cli = require_github_cli()
    encoded_sources = base64.b64encode(DEFAULT_OUTPUT.read_bytes())
    run_command(
        [github_cli, "secret", "set", SECRET_NAME],
        input_bytes=encoded_sources,
    )
    print(f"Updated encrypted GitHub secret {SECRET_NAME}.")

    if not arguments.no_run:
        run_command(
            [github_cli, "workflow", "run", WORKFLOW_FILE]
        )
        print(f"Started GitHub Actions workflow {WORKFLOW_FILE}.")


if __name__ == "__main__":
    main()
