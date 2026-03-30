#!/usr/bin/env python3
"""
Small wrapper to generate only the marketing graphs.

It picks the latest reports/files_generation_<n> folder by default and writes
the three PNG charts to the Desktop via src.visualizer.generate_visualizations().
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


def find_latest_reports_dir(base_dir: Path) -> Path:
    """Return the newest reports/files_generation_<n> directory."""
    candidates = []
    if not base_dir.exists():
        raise FileNotFoundError(f"Reports folder not found: {base_dir}")

    for path in base_dir.iterdir():
        if not path.is_dir():
            continue
        match = re.fullmatch(r"files_generation_(\d+)", path.name)
        if match:
            candidates.append((int(match.group(1)), path))

    if not candidates:
        raise FileNotFoundError(f"No files_generation_* folders found in {base_dir}")

    candidates.sort(key=lambda item: item[0])
    return candidates[-1][1]


def main() -> None:
    from src.visualizer import generate_visualizations

    parser = argparse.ArgumentParser(description="Generate only the three marketing charts.")
    parser.add_argument(
        "source_directory",
        nargs="?",
        help="Optional reports directory. Defaults to the latest reports/files_generation_<n> folder.",
    )
    args = parser.parse_args()

    if args.source_directory:
        source_dir = Path(args.source_directory).expanduser().resolve()
    else:
        source_dir = find_latest_reports_dir(Path("reports"))

    generate_visualizations(str(source_dir))


if __name__ == "__main__":
    main()
