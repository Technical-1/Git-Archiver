"""
Main application window for Git-Archiver.
"""

import os
import sys
import queue
import logging
import threading
import webbrowser
import datetime
from concurrent.futures import ThreadPoolExecutor

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QTableWidgetItem, QHeaderView,
    QMessageBox, QFileDialog, QProgressBar, QMenu, QAction,
    QApplication, QComboBox, QDialog
)
from PyQt5.QtGui import QColor, QIcon

from ..config import DATA_FOLDER, get_last_auto_update_time, save_last_auto_update_time
from ..utils import validate_repo_url, normalize_repo_url, is_internet_connected, current_timestamp
from ..data_store import load_cloned_info, save_cloned_info, get_repo_count_by_status
from ..repo_manager import clone_or_update_repo

from .widgets import EnhancedTableWidget
from .dialogs import ArchivedVersionsDialog, ColumnManagerDialog, SettingsDialog
from .workers import CloneWorker


class RepoSaverGUI(QWidget):
    """
    Main application interface that displays and manages GitHub repositories.

    Features:
    - Table view of all tracked repositories
    - Add single or bulk import repositories
    - Search and filter by URL, description, or status
    - Context menu for quick actions
    - Automatic daily updates
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Git-Archiver - GitHub Repository Saver")
        self.threads = []
        self.repoData = {}

        # Thread pool for background operations
        self.max_workers = max(1, os.cpu_count() or 4)
        self.thread_pool = ThreadPoolExecutor(max_workers=self.max_workers)
        self.queue = queue.Queue()
        self.active_tasks = 0
        self.queue_lock = threading.Lock()
        self.active_urls = set()

        # Auto-update scheduler
        self.last_auto_update = None
        self.auto_update_timer = None

        self.initUI()
        self.loadRepos()

        # Start queue processor
        self.process_queue_thread = threading.Thread(target=self.process_queue, daemon=True)
        self.process_queue_thread.start()

        # Start auto-update timer with delay
        QTimer.singleShot(30000, self.setupAutoUpdateTimer)

        # Log startup
        self.appendLog("Application started successfully")
        self.appendLog(f"Loaded {len(self.repoData)} repositories")

        # Display status summary
        counts = get_repo_count_by_status(self.repoData)
        status_parts = [f"{k}: {v}" for k, v in counts.items() if v > 0]
        self.appendLog(f"Status summary: {', '.join(status_parts)}")

    def initUI(self):
        """Set up the user interface"""
        mainLayout = QVBoxLayout()

        # Top controls - search and filter
        topControlsLayout = QHBoxLayout()

        searchLabel = QLabel("Search:")
        topControlsLayout.addWidget(searchLabel)

        self.searchEdit = QLineEdit()
        self.searchEdit.setPlaceholderText("Filter by URL or description...")
        self.searchEdit.setMinimumWidth(200)
        self.searchEdit.textChanged.connect(self.applyFilters)
        topControlsLayout.addWidget(self.searchEdit)

        statusLabel = QLabel("Status:")
        topControlsLayout.addWidget(statusLabel)

        self.statusFilter = QComboBox()
        self.statusFilter.addItems(["All", "active", "pending", "archived", "deleted", "error"])
        self.statusFilter.currentTextChanged.connect(self.applyFilters)
        topControlsLayout.addWidget(self.statusFilter)

        topControlsLayout.addStretch(1)

        # Column manager button
        self.columnManagerBtn = QPushButton("Manage Columns")
        self.columnManagerBtn.clicked.connect(self.showColumnManager)
        topControlsLayout.addWidget(self.columnManagerBtn)

        # Settings button
        self.settingsBtn = QPushButton("Settings")
        self.settingsBtn.clicked.connect(self.showSettings)
        topControlsLayout.addWidget(self.settingsBtn)

        mainLayout.addLayout(topControlsLayout)

        # Repository table
        self.repoTable = EnhancedTableWidget()
        self.repoTable.setColumnCount(8)
        self.repoTable.setHorizontalHeaderLabels([
            "Repo URL", "Description", "Status",
            "Last Cloned", "Last Updated",
            "Open Folder", "Archives", "README"
        ])

        self.repoTable.setEditTriggers(EnhancedTableWidget.NoEditTriggers)
        self.repoTable.setContextMenuPolicy(Qt.CustomContextMenu)
        self.repoTable.customContextMenuRequested.connect(self.showRowContextMenu)

        self.repoTable.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.repoTable.horizontalHeader().setStretchLastSection(False)
        self.repoTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        QTimer.singleShot(100, self.setupColumnWidths)

        mainLayout.addWidget(self.repoTable)

        # Add repo controls
        rowLayout = QHBoxLayout()

        self.addRepoEdit = QLineEdit()
        self.addRepoEdit.setPlaceholderText("Paste a GitHub repo URL (https://github.com/...)")
        self.addRepoEdit.returnPressed.connect(self.addRepo)
        rowLayout.addWidget(self.addRepoEdit)

        self.addRepoBtn = QPushButton("Add Repo")
        self.addRepoBtn.clicked.connect(self.addRepo)
        rowLayout.addWidget(self.addRepoBtn)

        self.bulkBtn = QPushButton("Bulk Upload")
        self.bulkBtn.clicked.connect(self.bulkUpload)
        rowLayout.addWidget(self.bulkBtn)

        self.refreshBtn = QPushButton("Refresh Statuses")
        self.refreshBtn.clicked.connect(self.refreshStatuses)
        rowLayout.addWidget(self.refreshBtn)

        self.updateAllBtn = QPushButton("Update All Now")
        self.updateAllBtn.clicked.connect(self.updateAllRepos)
        rowLayout.addWidget(self.updateAllBtn)

        mainLayout.addLayout(rowLayout)

        # Status indicators
        statusLayout = QHBoxLayout()

        statusLayout.addWidget(QLabel("Queue:"))
        self.queueCountLabel = QLabel("0")
        statusLayout.addWidget(self.queueCountLabel)

        statusLayout.addWidget(QLabel("Active:"))
        self.activeCountLabel = QLabel("0")
        statusLayout.addWidget(self.activeCountLabel)

        statusLayout.addWidget(QLabel("Last Auto-Update:"))
        self.lastUpdateTimeLabel = QLabel("Never")
        statusLayout.addWidget(self.lastUpdateTimeLabel)

        self.progressBar = QProgressBar()
        self.progressBar.setRange(0, 100)
        self.progressBar.setValue(0)
        self.progressBar.setTextVisible(True)
        self.progressBar.setFormat("%v/%m repos processed")
        statusLayout.addWidget(self.progressBar)

        mainLayout.addLayout(statusLayout)

        # Log area
        self.logText = QTextEdit()
        self.logText.setReadOnly(True)
        self.logText.setMaximumHeight(150)
        mainLayout.addWidget(self.logText)

        self.setLayout(mainLayout)
        self.resize(1200, 700)

        # Status update timer
        self.statusUpdateTimer = QTimer(self)
        self.statusUpdateTimer.setInterval(500)
        self.statusUpdateTimer.timeout.connect(self.updateStatusIndicators)
        self.statusUpdateTimer.start()

    def loadRepos(self):
        """Load repositories from the JSON file"""
        self.repoData = load_cloned_info()
        self.populateTable()

    def populateTable(self):
        """Fill the table with data, applying current filters"""
        self.repoTable.setRowCount(0)

        search_text = self.searchEdit.text().lower() if hasattr(self, 'searchEdit') else ""
        status_filter = self.statusFilter.currentText() if hasattr(self, 'statusFilter') else "All"

        for repo_url, info in self.repoData.items():
            # Apply status filter
            if status_filter != "All" and info.get("status", "") != status_filter:
                continue

            # Apply search filter
            if search_text:
                url_match = search_text in repo_url.lower()
                desc_match = search_text in info.get("online_description", "").lower()
                if not url_match and not desc_match:
                    continue

            self.addTableRow(repo_url, info)

    def addTableRow(self, repo_url, info):
        """Add a single repository to the table"""
        row_idx = self.repoTable.rowCount()
        self.repoTable.insertRow(row_idx)

        # URL
        url_item = QTableWidgetItem(repo_url)
        url_item.setToolTip(repo_url)
        url_item.setFlags(url_item.flags() & ~Qt.ItemIsEditable)
        self.repoTable.setItem(row_idx, 0, url_item)

        # Description
        desc = info.get("online_description", "")
        desc_item = QTableWidgetItem(desc)
        desc_item.setToolTip(desc)
        desc_item.setFlags(desc_item.flags() & ~Qt.ItemIsEditable)
        self.repoTable.setItem(row_idx, 1, desc_item)

        # Status with color coding
        status = info.get("status", "")
        status_item = QTableWidgetItem(status)
        status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)

        color_map = {
            "active": QColor(50, 180, 50),
            "archived": QColor(255, 255, 200),
            "deleted": QColor(255, 200, 200),
            "error": QColor(255, 180, 180),
            "pending": QColor(200, 200, 255)
        }
        if status in color_map:
            status_item.setBackground(color_map[status])

        last_error = info.get("last_error", "")
        if last_error:
            status_item.setToolTip(f"Error: {last_error}")

        self.repoTable.setItem(row_idx, 2, status_item)

        # Timestamps
        for col, key in [(3, "last_cloned"), (4, "last_updated")]:
            item = QTableWidgetItem(info.get(key, ""))
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.repoTable.setItem(row_idx, col, item)

        # Action buttons
        btn_folder = QPushButton("Folder")
        btn_folder.clicked.connect(lambda _, u=repo_url: self.openRepoFolder(u))
        self.repoTable.setCellWidget(row_idx, 5, btn_folder)

        btn_arch = QPushButton("Archives")
        btn_arch.clicked.connect(lambda _, u=repo_url: self.showArchives(u))
        self.repoTable.setCellWidget(row_idx, 6, btn_arch)

        btn_readme = QPushButton("README")
        btn_readme.clicked.connect(lambda _, u=repo_url: self.viewReadme(u))
        self.repoTable.setCellWidget(row_idx, 7, btn_readme)

    def applyFilters(self):
        """Reapply filters when search or status filter changes"""
        self.populateTable()

    def showRowContextMenu(self, pos):
        """Show context menu when right-clicking on a row"""
        row = self.repoTable.rowAt(pos.y())
        if row < 0:
            return

        url_item = self.repoTable.item(row, 0)
        if not url_item:
            return
        repo_url = url_item.text()

        menu = QMenu(self)

        copy_action = QAction("Copy URL", self)
        copy_action.triggered.connect(lambda: QApplication.clipboard().setText(repo_url))
        menu.addAction(copy_action)

        open_github_action = QAction("Open on GitHub", self)
        open_github_action.triggered.connect(lambda: webbrowser.open(repo_url.replace(".git", "")))
        menu.addAction(open_github_action)

        menu.addSeparator()

        update_action = QAction("Update This Repo", self)
        update_action.triggered.connect(lambda: self.updateSingleRepo(repo_url))
        menu.addAction(update_action)

        menu.addSeparator()

        remove_action = QAction("Remove from Tracking", self)
        remove_action.triggered.connect(lambda: self.removeRepoFromTracking(repo_url))
        menu.addAction(remove_action)

        delete_action = QAction("Delete Local Copy", self)
        delete_action.triggered.connect(lambda: self.deleteLocalCopy(repo_url))
        menu.addAction(delete_action)

        menu.exec_(self.repoTable.mapToGlobal(pos))

    def addRepo(self):
        """Add a single repository from the text field"""
        if not is_internet_connected():
            QMessageBox.warning(self, "No Connection", "Internet connection required")
            return

        url = self.addRepoEdit.text().strip()
        if not url:
            return

        if not validate_repo_url(url):
            QMessageBox.warning(self, "Invalid URL", "Please enter a valid GitHub repository URL")
            return

        url = normalize_repo_url(url)

        if url in self.repoData:
            self.appendLog(f"Repository already tracked: {url}")
            return

        # Add to tracking
        repo_name = url.rstrip("/").split("/")[-1]
        self.repoData[url] = {
            "last_cloned": "",
            "last_updated": "",
            "local_path": os.path.join(DATA_FOLDER, repo_name),
            "online_description": "",
            "status": "pending"
        }
        save_cloned_info(self.repoData)
        self.addTableRow(url, self.repoData[url])
        self.appendLog(f"Added new repository: {url}")

        # Start clone worker
        worker = CloneWorker(url)
        worker.finished_signal.connect(self.onCloneFinished)
        worker.start()
        self.threads.append(worker)

        self.addRepoEdit.clear()

    def bulkUpload(self):
        """Import multiple repositories from a text file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select URL List File", "", "Text Files (*.txt);;All Files (*)"
        )
        if not file_path:
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            added = 0
            for line in lines:
                url = line.strip()
                if not url or url.startswith("#"):
                    continue
                if not validate_repo_url(url):
                    continue

                url = normalize_repo_url(url)
                if url not in self.repoData:
                    repo_name = url.rstrip("/").split("/")[-1]
                    self.repoData[url] = {
                        "last_cloned": "",
                        "last_updated": "",
                        "local_path": os.path.join(DATA_FOLDER, repo_name),
                        "online_description": "",
                        "status": "pending"
                    }
                    added += 1

            save_cloned_info(self.repoData)
            self.populateTable()
            self.appendLog(f"Bulk import: Added {added} new repositories")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to import: {e}")

    def onCloneFinished(self, url, success):
        """Handle clone/update completion"""
        self.repoData = load_cloned_info()
        self.updateRowForRepo(url)

        if success:
            self.appendLog(f"Successfully processed: {url}")
        else:
            self.appendLog(f"Failed to process: {url}")

    def updateRowForRepo(self, repo_url):
        """Update the table row for a specific repository"""
        info = self.repoData.get(repo_url, {})

        for r in range(self.repoTable.rowCount()):
            cell = self.repoTable.item(r, 0)
            if cell and cell.text() == repo_url:
                # Update description
                desc = info.get("online_description", "")
                desc_item = QTableWidgetItem(desc)
                desc_item.setToolTip(desc)
                desc_item.setFlags(desc_item.flags() & ~Qt.ItemIsEditable)
                self.repoTable.setItem(r, 1, desc_item)

                # Update status
                status = info.get("status", "")
                status_item = QTableWidgetItem(status)
                status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)

                color_map = {
                    "active": QColor(50, 180, 50),
                    "archived": QColor(255, 255, 200),
                    "deleted": QColor(255, 200, 200),
                    "error": QColor(255, 180, 180),
                    "pending": QColor(200, 200, 255)
                }
                if status in color_map:
                    status_item.setBackground(color_map[status])

                last_error = info.get("last_error", "")
                if last_error:
                    status_item.setToolTip(f"Error: {last_error}")

                self.repoTable.setItem(r, 2, status_item)

                # Update timestamps
                for col, key in [(3, "last_cloned"), (4, "last_updated")]:
                    item = QTableWidgetItem(info.get(key, ""))
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    self.repoTable.setItem(r, col, item)

                break

        self.repoTable.viewport().update()

    def openRepoFolder(self, repo_url):
        """Open the repository folder in the file browser"""
        info = self.repoData.get(repo_url, {})
        local_path = info.get("local_path", "")

        if not local_path or not os.path.exists(local_path):
            QMessageBox.warning(self, "Not Found", "Repository folder not found")
            return

        if sys.platform == "darwin":
            os.system(f'open "{local_path}"')
        elif sys.platform == "win32":
            os.system(f'explorer "{local_path}"')
        else:
            os.system(f'xdg-open "{local_path}"')

    def showArchives(self, repo_url):
        """Show the archives dialog for a repository"""
        info = self.repoData.get(repo_url, {})
        local_path = info.get("local_path", "")

        if not local_path or not os.path.exists(local_path):
            QMessageBox.warning(self, "Not Found", "Repository folder not found")
            return

        dialog = ArchivedVersionsDialog(repo_url, local_path, self)
        dialog.exec_()

    def viewReadme(self, repo_url):
        """Open the repository's README file"""
        info = self.repoData.get(repo_url, {})
        local_path = info.get("local_path", "")

        if not local_path or not os.path.exists(local_path):
            QMessageBox.warning(self, "Not Found", "Repository folder not found")
            return

        # Look for README file
        readme_names = ["README.md", "README.txt", "README", "readme.md", "Readme.md"]
        for name in readme_names:
            readme_path = os.path.join(local_path, name)
            if os.path.exists(readme_path):
                if sys.platform == "darwin":
                    os.system(f'open "{readme_path}"')
                elif sys.platform == "win32":
                    os.system(f'start "" "{readme_path}"')
                else:
                    os.system(f'xdg-open "{readme_path}"')
                return

        QMessageBox.information(self, "Not Found", "No README file found in repository")

    def updateSingleRepo(self, repo_url):
        """Update a single repository"""
        self.appendLog(f"Updating {repo_url}...")
        worker = CloneWorker(repo_url)
        worker.finished_signal.connect(self.onCloneFinished)
        worker.start()
        self.threads.append(worker)

    def removeRepoFromTracking(self, repo_url):
        """Remove a repository from tracking"""
        reply = QMessageBox.question(
            self, "Remove Repository",
            f"Remove '{repo_url}' from tracking?\n\nThis will NOT delete local files.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            if repo_url in self.repoData:
                del self.repoData[repo_url]
                save_cloned_info(self.repoData)
                self.populateTable()
                self.appendLog(f"Removed from tracking: {repo_url}")

    def deleteLocalCopy(self, repo_url):
        """Delete the local copy of a repository"""
        import shutil

        info = self.repoData.get(repo_url, {})
        local_path = info.get("local_path", "")

        if not local_path or not os.path.exists(local_path):
            QMessageBox.warning(self, "Not Found", f"Local copy not found at: {local_path}")
            return

        reply = QMessageBox.warning(
            self, "Delete Local Copy",
            f"Delete local copy at:\n{local_path}\n\nThis cannot be undone!",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                shutil.rmtree(local_path)
                self.repoData[repo_url]["last_cloned"] = ""
                self.repoData[repo_url]["last_updated"] = ""
                self.repoData[repo_url]["status"] = "pending"
                save_cloned_info(self.repoData)
                self.populateTable()
                self.appendLog(f"Deleted local copy: {local_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete: {e}")

    def refreshStatuses(self):
        """Refresh all repository statuses from GitHub"""
        self.appendLog("Refreshing repository statuses...")
        from ..repo_manager import detect_deleted_or_archived
        detect_deleted_or_archived(self.repoData)
        self.populateTable()
        self.appendLog("Status refresh complete")

    def updateAllRepos(self):
        """Update all repositories"""
        reply = QMessageBox.question(
            self, "Update All",
            f"Update all {len(self.repoData)} repositories?\n\nThis may take a while.",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        self.appendLog("Starting update of all repositories...")

        for url in self.repoData.keys():
            with self.queue_lock:
                if url not in self.active_urls:
                    self.queue.put(url)

    def process_queue(self):
        """Process URLs from the queue (runs in background thread)"""
        while True:
            try:
                url = self.queue.get(timeout=1)
                with self.queue_lock:
                    if url in self.active_urls:
                        continue
                    self.active_urls.add(url)

                try:
                    clone_or_update_repo(url)
                finally:
                    with self.queue_lock:
                        self.active_urls.discard(url)

            except queue.Empty:
                continue
            except Exception as e:
                logging.error(f"Queue processing error: {e}")

    def updateStatusIndicators(self):
        """Update the status bar indicators"""
        queue_size = self.queue.qsize()
        self.queueCountLabel.setText(str(queue_size))

        with self.queue_lock:
            active_count = len(self.active_urls)
        self.activeCountLabel.setText(str(active_count))

        if self.last_auto_update:
            self.lastUpdateTimeLabel.setText(self.last_auto_update)

        total = queue_size + active_count
        if total > 0:
            self.progressBar.setRange(0, total)
            self.progressBar.setValue(total - queue_size)
        else:
            self.progressBar.setRange(0, 100)
            self.progressBar.setValue(0)

    def setupAutoUpdateTimer(self):
        """Set up automatic daily updates"""
        self.appendLog("Setting up automatic update scheduler")

        self.auto_update_timer = QTimer(self)
        self.auto_update_timer.setInterval(3600000)  # Check hourly
        self.auto_update_timer.timeout.connect(self.checkDailyUpdate)
        self.auto_update_timer.start()

        self.last_auto_update = get_last_auto_update_time()

        if self.last_auto_update:
            self.appendLog(f"Last automatic update: {self.last_auto_update}")

        QTimer.singleShot(120000, self.delayedFirstCheck)

    def delayedFirstCheck(self):
        """Perform the first automatic update check after a delay"""
        if not is_internet_connected():
            self.appendLog("Skipping auto-update check - No internet connection")
            return
        self.checkDailyUpdate()

    def checkDailyUpdate(self):
        """Check if it's time for a daily update"""
        if not is_internet_connected():
            return

        now = datetime.datetime.now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")

        if self.last_auto_update is None:
            self.last_auto_update = now_str
            save_last_auto_update_time(now_str)
            return

        try:
            last_time = datetime.datetime.strptime(self.last_auto_update, "%Y-%m-%d %H:%M:%S")
            time_diff = now - last_time

            if time_diff.total_seconds() >= 86400:  # 24 hours
                self.appendLog(f"Starting scheduled daily update at {now_str}")

                for repo_url in self.repoData.keys():
                    with self.queue_lock:
                        if repo_url not in self.active_urls:
                            self.queue.put(repo_url)

                self.last_auto_update = now_str
                save_last_auto_update_time(now_str)
                self.refreshStatuses()

        except Exception as e:
            logging.error(f"Error checking daily update: {e}")

    def showColumnManager(self):
        """Show the column manager dialog"""
        dialog = ColumnManagerDialog(self.repoTable, self)
        dialog.exec_()

    def showSettings(self):
        """Show the settings dialog"""
        dialog = SettingsDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            self.appendLog("Settings saved")

    def setupColumnWidths(self):
        """Set initial column widths"""
        header = self.repoTable.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)

    def appendLog(self, message: str):
        """Append a message to the log area"""
        timestamp = current_timestamp()
        self.logText.append(f"[{timestamp}] {message}")

    def closeEvent(self, event):
        """Handle window close event"""
        if self.auto_update_timer:
            self.auto_update_timer.stop()

        if hasattr(self, 'statusUpdateTimer') and self.statusUpdateTimer:
            self.statusUpdateTimer.stop()

        self.thread_pool.shutdown(wait=False)
        event.accept()
