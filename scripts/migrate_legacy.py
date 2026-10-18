#!/usr/bin/env python3
"""Copy a user-selected retired importer library into a new Manager library."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from manager.migration import audit_legacy, migrate_legacy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path, nargs="?")
    parser.add_argument(
        "--audit", action="store_true", help="Read only; summarize source assets"
    )
    parser.add_argument(
        "--no-runtime", action="store_true", help="Deprecated compatibility flag; libraries are always data-only"
    )
    args = parser.parse_args()
    if args.audit:
        report = audit_legacy(args.source)
        report.pop("files")
    else:
        if args.destination is None:
            parser.error("destination is required unless --audit is used")
        report = migrate_legacy(
            args.source, args.destination, install_runtime=False
        )
        report = {
            key: report[key]
            for key in (
                "destination",
                "rowCount",
                "sourceUnchanged",
                "sourceFileCount",
                "warnings",
                "registrationsChanged",
            )
        }
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
