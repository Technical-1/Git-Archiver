#!/usr/bin/env python3
"""
Convenience script to run Git-Archiver.

Usage:
    python run.py                    # Launch GUI
    python run.py --headless         # Headless, process pending only
    python run.py --headless --update-all  # Headless, update all
    python run.py --headless --import-file urls.txt  # Import and process
"""

from src.main import main

if __name__ == "__main__":
    main()
