"""
Git-Archiver - GitHub Repository Saver

A PyQt5 application to clone, track, and archive GitHub repositories.
"""

__version__ = "2.0.0"
__author__ = "Git-Archiver Team"

from .main import main
from .cli import run_headless_update

__all__ = ['main', 'run_headless_update']
