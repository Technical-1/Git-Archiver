"""
Background worker threads for Git-Archiver.
"""

import logging
from PyQt5.QtCore import QThread, pyqtSignal

from ..repo_manager import clone_or_update_repo


class CloneWorker(QThread):
    """
    Background thread for cloning or updating a repository.

    Signals:
        finished_signal: Emitted when operation completes with (url, success) tuple
        progress_signal: Emitted with progress updates (url, message)
    """

    finished_signal = pyqtSignal(str, bool)
    progress_signal = pyqtSignal(str, str)

    def __init__(self, repo_url: str, parent=None):
        super().__init__(parent)
        self.repo_url = repo_url

    def run(self):
        """Execute the clone/update operation"""
        try:
            self.progress_signal.emit(self.repo_url, "Starting...")
            success = clone_or_update_repo(self.repo_url)
            self.finished_signal.emit(self.repo_url, success)
        except Exception as e:
            logging.error(f"CloneWorker error for {self.repo_url}: {e}")
            self.finished_signal.emit(self.repo_url, False)


class RefreshWorker(QThread):
    """
    Background thread for refreshing repository statuses.

    Signals:
        finished_signal: Emitted when refresh completes
        progress_signal: Emitted with (current, total) progress
    """

    finished_signal = pyqtSignal()
    progress_signal = pyqtSignal(int, int)

    def __init__(self, repos_data: dict, parent=None):
        super().__init__(parent)
        self.repos_data = repos_data

    def run(self):
        """Refresh status for all repositories"""
        from ..repo_manager import detect_deleted_or_archived

        try:
            detect_deleted_or_archived()
        except Exception as e:
            logging.error(f"RefreshWorker error: {e}")

        self.finished_signal.emit()


class BulkCloneWorker(QThread):
    """
    Background thread for processing multiple repositories.

    Signals:
        finished_signal: Emitted when all operations complete
        progress_signal: Emitted with (current, total, url) progress
        repo_finished_signal: Emitted when single repo completes with (url, success)
    """

    finished_signal = pyqtSignal()
    progress_signal = pyqtSignal(int, int, str)
    repo_finished_signal = pyqtSignal(str, bool)

    def __init__(self, urls: list, parent=None):
        super().__init__(parent)
        self.urls = urls
        self._stop_requested = False

    def run(self):
        """Process all URLs in sequence"""
        total = len(self.urls)

        for i, url in enumerate(self.urls):
            if self._stop_requested:
                break

            self.progress_signal.emit(i + 1, total, url)

            try:
                success = clone_or_update_repo(url)
                self.repo_finished_signal.emit(url, success)
            except Exception as e:
                logging.error(f"BulkCloneWorker error for {url}: {e}")
                self.repo_finished_signal.emit(url, False)

        self.finished_signal.emit()

    def stop(self):
        """Request the worker to stop after the current operation"""
        self._stop_requested = True
