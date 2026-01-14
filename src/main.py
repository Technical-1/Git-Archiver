#!/usr/bin/env python3
"""
Git-Archiver - Main Entry Point

This is the main entry point for Git-Archiver.
Run this file to start either the GUI or headless CLI mode.

Usage:
    python -m src.main                    # Launch GUI
    python -m src.main --headless         # Headless, process pending only
    python -m src.main --headless --update-all  # Headless, update all
    python -m src.main --headless --import-file urls.txt  # Import and process
"""

import argparse
import json
import os
import sys

from .config import CLONED_JSON_PATH, DATA_FOLDER
from .utils import setup_logging
from .cli import run_headless_update


def main():
    """
    Application entry point.

    Supports both GUI mode and headless CLI mode.
    """
    parser = argparse.ArgumentParser(
        description="GitHub Repo Saver - Clone and archive GitHub repositories"
    )
    parser.add_argument("--headless", action="store_true",
                        help="Run in headless mode (no GUI)")
    parser.add_argument("--update-all", action="store_true",
                        help="Update all repos, not just pending ones")
    parser.add_argument("--include-archived", action="store_true",
                        help="Include archived/deleted repos in processing")
    parser.add_argument("--import-file", type=str, metavar="FILE",
                        help="Import URLs from a text file before processing")

    args = parser.parse_args()

    setup_logging()

    # Make sure our data directory exists
    os.makedirs(DATA_FOLDER, exist_ok=True)

    # Headless mode
    if args.headless:
        run_headless_update(
            update_all=args.update_all,
            active_only=not args.include_archived,
            import_file=args.import_file
        )
        return

    # GUI mode - startup verification
    print("*** Startup Check ***")
    try:
        if os.path.exists(CLONED_JSON_PATH):
            print(f"Found {CLONED_JSON_PATH}, checking contents...")
            with open(CLONED_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            print(f"Successfully loaded {len(data)} repositories")

            # Count repositories by status
            status_counts = {"active": 0, "archived": 0, "deleted": 0, "error": 0, "pending": 0, "other": 0}
            for url, info in data.items():
                status = info.get("status", "")
                if status in status_counts:
                    status_counts[status] += 1
                else:
                    status_counts["other"] += 1

            print("Repository status counts:")
            for status, count in status_counts.items():
                if count > 0:
                    print(f"  {status}: {count}")

            # Check for any deleted repositories still in the file
            deleted = [url for url, info in data.items() if info.get("status") == "deleted"]
            if deleted:
                print(f"WARNING: Found {len(deleted)} deleted repositories in the file")
                print("First 3 deleted repos:", deleted[:3])

            # Check for any repositories with errors
            errors = [url for url, info in data.items() if info.get("status") == "error"]
            if errors:
                print(f"WARNING: Found {len(errors)} repositories with errors")
                print("First 3 error repos:", errors[:3])
        else:
            print(f"No {CLONED_JSON_PATH} file found, will be created when needed")
    except Exception as e:
        print(f"ERROR checking JSON file: {e}")
    print("*** End Startup Check ***")

    # Filter out annoying Qt console warnings
    if not os.environ.get('DEBUG_QT'):
        original_stderr = sys.stderr

        class QtWarningFilter:
            def write(self, text):
                # Only show important warnings, not the common Qt noise
                qt_warnings = [
                    "QVector<int>",
                    "QTextCursor",
                    "qRegisterMetaType",
                    "Cannot queue arguments",
                    "is registered using qRegisterMetaType()",
                    "QObject::connect",
                    "overrides the method identifier"
                ]
                if not any(warning in text for warning in qt_warnings):
                    original_stderr.write(text)

            def flush(self):
                original_stderr.flush()

        sys.stderr = QtWarningFilter()

    # Import GUI components only when needed (avoid import errors in headless mode)
    from PyQt5.QtWidgets import QApplication
    from .gui import RepoSaverGUI

    app = QApplication(sys.argv)
    gui = RepoSaverGUI()
    gui.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
