#!/usr/bin/env python3
"""
Single-file GitHub Repo Saver with PyQt:
- JSON-based storage (cloned_repos.json) tracks repos.
- Adds new repos, clones/updates them in threads.
- Displays each repo's info (URL, description, status, last cloned/updated) in a table.
- Refresh button re-checks "archived/deleted" statuses on GitHub.
- Buttons to open folder, show archives, view README, etc.

No separate 'github_repo_saver.py' is needed; everything is in one file.
"""

import sys
import os
import json
import subprocess
import logging
import datetime
import requests

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QLabel, QLineEdit, QTextEdit, QMessageBox,
    QDialog, QListWidget, QListWidgetItem, QFileDialog, 
    QHBoxLayout, QVBoxLayout, QWidget
)
from PyQt5.QtWidgets import QDialog


###############################################################################
#                               DATA & LOGIC
###############################################################################

CLONED_JSON_PATH = "src/cloned_repos.json"
DATA_FOLDER = "data"  # local folder where repos will be cloned

def setup_logging():
    """Configure logging (not strictly necessary for a single-file demo)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

def validate_repo_url(url: str) -> bool:
    """
    Check if URL starts with 'https://github.com/'.
    Also optionally ensure .git suffix if you like.
    """
    return url.startswith("https://github.com/")

def load_cloned_info() -> dict:
    """
    Loads cloned_repos.json which tracks each repo's data.
    Structure example:
    {
      "https://github.com/user/repo.git": {
         "last_cloned": "YYYY-MM-DD HH:MM:SS",
         "last_updated": "YYYY-MM-DD HH:MM:SS",
         "local_path": "data/repo.git",
         "online_description": "...",
         "status": "active"   # or "archived", "deleted", "error"
      },
      ...
    }
    """
    if not os.path.isfile(CLONED_JSON_PATH):
        return {}
    try:
        with open(CLONED_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

def save_cloned_info(data: dict):
    """Writes out the updated dictionary to cloned_repos.json."""
    with open(CLONED_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def current_timestamp() -> str:
    """Return current local time as a nice string."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def get_online_repo_description(owner, repo_name):
    """
    Query GitHub API to fetch the description and archived/deleted status.
    Returns a tuple: (description, is_archived, is_deleted)
    """
    api_url = f"https://api.github.com/repos/{owner}/{repo_name}"
    try:
        resp = requests.get(api_url, headers={"Accept": "application/vnd.github.v3+json"}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            desc = data.get("description", "") or ""
            archived = data.get("archived", False)
            return (desc, archived, False)
        elif resp.status_code == 404:
            return ("", False, True)  # not found => deleted
        else:
            logging.warning(f"Unexpected status {resp.status_code} from GitHub for {owner}/{repo_name}")
            return ("", False, False)
    except requests.RequestException as e:
        logging.warning(f"Failed to fetch {owner}/{repo_name}: {e}")
        return ("", False, False)

def clone_or_update_repo(repo_url: str):
    """
    Clone/pull the repo. Also fetch info from GitHub:
      - description, archived/deleted => status
    Save everything to cloned_repos.json
    """
    repos_data = load_cloned_info()
    repo_name = repo_url.rstrip("/").split("/")[-1]  # e.g. 'my-repo.git'
    repo_path = os.path.join(DATA_FOLDER, repo_name)

    # Attempt to parse out owner/repo
    parts = repo_url.replace("https://github.com/", "").split("/")
    if len(parts) >= 2:
        owner, raw_repo = parts[0], parts[1].replace(".git", "")
        desc, is_arch, is_del = get_online_repo_description(owner, raw_repo)
        if is_del:
            status = "deleted"
        elif is_arch:
            status = "archived"
        else:
            status = "active"
    else:
        desc = ""
        status = "error"

    now = current_timestamp()
    record = repos_data.get(repo_url, {
        "last_cloned": "",
        "last_updated": "",
        "local_path": repo_path,
        "online_description": desc,
        "status": status,
    })

    # Overwrite these fields in case they've changed
    record["online_description"] = desc
    record["status"] = status
    record["local_path"] = repo_path

    # If not deleted, proceed to clone/pull
    if status != "deleted":
        if os.path.isdir(repo_path):
            # do a pull
            logging.info(f"Pulling updates for {repo_url}")
            try:
                subprocess.run(["git", "-C", repo_path, "pull"], check=True)
                record["last_cloned"] = now
                record["last_updated"] = now
            except subprocess.CalledProcessError as e:
                logging.error(f"Failed to pull {repo_url}: {e}")
        else:
            # clone new
            logging.info(f"Cloning {repo_url} into {repo_path}")
            os.makedirs(DATA_FOLDER, exist_ok=True)
            try:
                subprocess.run(["git", "clone", repo_url, repo_path], check=True)
                record["last_cloned"] = now
                record["last_updated"] = now
            except subprocess.CalledProcessError as e:
                logging.error(f"Failed to clone {repo_url}: {e}")
    else:
        logging.warning(f"Skipping clone - GitHub indicates {repo_url} is deleted.")

    repos_data[repo_url] = record
    save_cloned_info(repos_data)

def detect_deleted_or_archived():
    """
    Loop over everything in cloned_repos.json and re-check if it's archived or deleted.
    Update 'status' and 'online_description' accordingly.
    """
    repos_data = load_cloned_info()
    changed = False
    for repo_url, record in repos_data.items():
        parts = repo_url.replace("https://github.com/", "").split("/")
        if len(parts) < 2:
            continue
        owner, raw_repo = parts[0], parts[1].replace(".git", "")
        desc, is_arch, is_del = get_online_repo_description(owner, raw_repo)
        if is_del:
            record["status"] = "deleted"
        elif is_arch:
            record["status"] = "archived"
        else:
            record["status"] = "active"
        record["online_description"] = desc
        changed = True

    if changed:
        save_cloned_info(repos_data)


###############################################################################
#                           WORKER THREAD
###############################################################################

class CloneWorker(QThread):
    """
    Runs clone_or_update_repo(repo_url) in the background.
    We keep references to these threads in the GUI so they don't get GC'd.
    """
    logSignal = pyqtSignal(str)    # to show logs in GUI
    finishedSignal = pyqtSignal(str)  # emits repo_url when done

    def __init__(self, url, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        try:
            self.logSignal.emit(f"Starting clone/update: {self.url}")
            clone_or_update_repo(self.url)
            self.logSignal.emit(f"Finished clone/update: {self.url}")
        except Exception as e:
            self.logSignal.emit(f"Error: {str(e)}")

        self.finishedSignal.emit(self.url)


###############################################################################
#                          ARCHIVES DIALOG
###############################################################################

class ArchivedVersionsDialog(QDialog):
    """
    Lists & opens any "versions" archives for a given local repo folder.
    """
    def __init__(self, repo_path, parent=None):
        super().__init__(parent)
        self.repo_path = repo_path
        self.setWindowTitle(f"Archived Versions - {os.path.basename(repo_path)}")
        self.resize(500, 300)

        layout = QVBoxLayout()
        self.archivesList = QListWidget()
        layout.addWidget(self.archivesList)

        self.openButton = QPushButton("Open Selected Archive")
        self.openButton.clicked.connect(self.openSelectedArchive)
        layout.addWidget(self.openButton)

        self.setLayout(layout)
        self.loadArchivedVersions()

    def loadArchivedVersions(self):
        versions_dir = os.path.join(self.repo_path, "versions")
        if not os.path.isdir(versions_dir):
            return
        for item in os.listdir(versions_dir):
            item_path = os.path.join(versions_dir, item)
            if os.path.isdir(item_path):
                self.archivesList.addItem(item)
            elif item.endswith(".tar.xz"):
                self.archivesList.addItem(item)

    def openSelectedArchive(self):
        selected_items = self.archivesList.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "No Selection", "Select an archive to open.")
            return

        archive_name = selected_items[0].text()
        versions_dir = os.path.join(self.repo_path, "versions")
        archive_path = os.path.join(versions_dir, archive_name)

        if os.path.isdir(archive_path):
            self.openInFinder(archive_path)
        else:
            # We assume it's a tar.xz
            temp_dir = tempfile.mkdtemp(prefix="repo_archive_")
            try:
                subprocess.run(["tar", "-xJf", archive_path, "-C", temp_dir], check=True)
                self.openInFinder(temp_dir)
            except Exception as e:
                QMessageBox.critical(self, "Extraction Error", str(e))

    def openInFinder(self, path):
        if sys.platform.startswith("darwin"):
            subprocess.run(["open", path])
        elif os.name == "nt":
            os.startfile(path)
        else:
            subprocess.run(["xdg-open", path])


###############################################################################
#                               MAIN GUI
###############################################################################

class RepoSaverGUI(QWidget):
    """
    Main GUI:
    - Loads all repos from JSON on startup.
    - Displays them in a table.
    - Add new repo (in separate thread).
    - Refresh statuses => re-check archived/deleted.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GitHub Repo Saver - Single File")
        self.threads = []  # keep references to CloneWorker threads
        self.repoData = {}
        self.initUI()
        self.loadRepos()  # auto-load from JSON

    def initUI(self):
        mainLayout = QVBoxLayout()

        # Table
        self.repoTable = QTableWidget()
        self.repoTable.setColumnCount(6)
        self.repoTable.setHorizontalHeaderLabels([
            "Repo URL",
            "Description",
            "Status",
            "Last Cloned",
            "Last Updated",
            "Actions"
        ])
        self.repoTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        mainLayout.addWidget(self.repoTable)

        # Add / Refresh
        rowLayout = QHBoxLayout()
        self.addRepoEdit = QLineEdit()
        self.addRepoEdit.setPlaceholderText("Paste a GitHub repo URL (https://github.com/...)")
        rowLayout.addWidget(self.addRepoEdit)

        self.addRepoBtn = QPushButton("Add Repo")
        self.addRepoBtn.clicked.connect(self.addRepo)
        rowLayout.addWidget(self.addRepoBtn)

        self.refreshBtn = QPushButton("Refresh Statuses")
        self.refreshBtn.clicked.connect(self.refreshStatuses)
        rowLayout.addWidget(self.refreshBtn)

        mainLayout.addLayout(rowLayout)

        # Logging
        self.logText = QTextEdit()
        self.logText.setReadOnly(True)
        mainLayout.addWidget(self.logText)

        self.setLayout(mainLayout)
        self.resize(1100, 600)

    def loadRepos(self):
        """Load from JSON and populate the table."""
        self.repoData = load_cloned_info()
        self.populateTable()

    def populateTable(self):
        self.repoTable.setRowCount(0)
        for repo_url, info in self.repoData.items():
            self.addTableRow(repo_url, info)

    def addTableRow(self, repo_url, info):
        row_idx = self.repoTable.rowCount()
        self.repoTable.insertRow(row_idx)

        # URL
        item_url = QTableWidgetItem(repo_url)
        self.repoTable.setItem(row_idx, 0, item_url)

        # Description
        desc = info.get("online_description", "")
        item_desc = QTableWidgetItem(desc)
        self.repoTable.setItem(row_idx, 1, item_desc)

        # Status
        status = info.get("status", "")
        item_status = QTableWidgetItem(status)
        self.repoTable.setItem(row_idx, 2, item_status)

        # Last Cloned
        last_cloned = info.get("last_cloned", "")
        item_cloned = QTableWidgetItem(last_cloned)
        self.repoTable.setItem(row_idx, 3, item_cloned)

        # Last Updated
        last_updated = info.get("last_updated", "")
        item_updated = QTableWidgetItem(last_updated)
        self.repoTable.setItem(row_idx, 4, item_updated)

        # Actions: open folder, archives, README
        actionLayout = QHBoxLayout()
        btn_open = QPushButton("Folder")
        btn_open.clicked.connect(lambda _, url=repo_url: self.openRepoFolder(url))
        actionLayout.addWidget(btn_open)

        btn_arch = QPushButton("Archives")
        btn_arch.clicked.connect(lambda _, url=repo_url: self.showArchives(url))
        actionLayout.addWidget(btn_arch)

        btn_readme = QPushButton("README")
        btn_readme.clicked.connect(lambda _, url=repo_url: self.viewReadme(url))
        actionLayout.addWidget(btn_readme)

        widget = QWidget()
        widget.setLayout(actionLayout)
        self.repoTable.setCellWidget(row_idx, 5, widget)

    def addRepo(self):
        """Add a new repo based on user input, clone it in background."""
        url = self.addRepoEdit.text().strip()
        if not url:
            QMessageBox.warning(self, "No URL", "Please enter a GitHub repo URL.")
            return
        if not validate_repo_url(url):
            QMessageBox.warning(self, "Invalid URL", "Must start with https://github.com/")
            return
        if not url.endswith(".git"):
            url += ".git"

        # Check if already in JSON
        if url in self.repoData:
            QMessageBox.information(self, "Duplicate", "That repo is already in cloned_repos.json.")
            return

        # Create an entry in memory and JSON
        self.repoData[url] = {
            "last_cloned": "",
            "last_updated": "",
            "local_path": os.path.join(DATA_FOLDER, url.split("/")[-1]),
            "online_description": "",
            "status": "pending",
        }
        save_cloned_info(self.repoData)

        # Show in table immediately
        self.addTableRow(url, self.repoData[url])
        self.addRepoEdit.clear()

        # Spawn a worker to actually do the clone/update
        worker = CloneWorker(url)
        self.threads.append(worker)  # keep reference
        worker.logSignal.connect(self.appendLog)
        worker.finishedSignal.connect(self.cloneFinished)
        worker.start()

    def cloneFinished(self, repo_url):
        """Triggered when the background clone finishes. Update that row's data."""
        self.appendLog(f"Clone finished for: {repo_url}")
        # reload from JSON to see updated fields
        self.repoData = load_cloned_info()
        self.updateRowForRepo(repo_url)

        # We can remove the worker from self.threads if we want
        # so it doesn't accumulate forever
        # (only do so after it's actually finished).
        # Since we have the url, we can find which worker in self.threads
        # if that matters. Or do:
        # self.threads = [t for t in self.threads if t is not sender]

    def updateRowForRepo(self, repo_url):
        """Refresh the row in the table for the given repo_url."""
        row_count = self.repoTable.rowCount()
        info = self.repoData.get(repo_url, {})
        for row in range(row_count):
            cell = self.repoTable.item(row, 0)
            if cell and cell.text() == repo_url:
                self.repoTable.item(row, 1).setText(info.get("online_description", ""))
                self.repoTable.item(row, 2).setText(info.get("status", ""))
                self.repoTable.item(row, 3).setText(info.get("last_cloned", ""))
                self.repoTable.item(row, 4).setText(info.get("last_updated", ""))
                break

    def refreshStatuses(self):
        """Re-check archived/deleted status for all repos."""
        self.captureLogs()
        detect_deleted_or_archived()
        self.repoData = load_cloned_info()
        self.populateTable()
        self.appendLog("Refreshed repo statuses.\n")

    def openRepoFolder(self, repo_url):
        info = self.repoData.get(repo_url, {})
        local_path = info.get("local_path", "")
        if local_path and os.path.isdir(local_path):
            self.openInFinder(local_path)
        else:
            QMessageBox.information(self, "Folder Not Found", f"No local folder for {repo_url}")

    def showArchives(self, repo_url):
        info = self.repoData.get(repo_url, {})
        local_path = info.get("local_path", "")
        if not local_path or not os.path.isdir(local_path):
            QMessageBox.information(self, "Repo Not Found", "Clone the repo first.")
            return
        dlg = ArchivedVersionsDialog(local_path, self)
        dlg.exec_()

    def viewReadme(self, repo_url):
        info = self.repoData.get(repo_url, {})
        local_path = info.get("local_path", "")
        if not local_path or not os.path.isdir(local_path):
            QMessageBox.information(self, "Repo Not Found", "Clone the repo first.")
            return
        readme_path = os.path.join(local_path, "README.md")
        if not os.path.isfile(readme_path):
            QMessageBox.information(self, "No README", "No README.md found.")
            return

        with open(readme_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        dlg = QDialog(self)
        dlg.setWindowTitle(f"README - {os.path.basename(local_path)}")
        layout = QVBoxLayout()
        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setPlainText(content)
        layout.addWidget(txt)
        dlg.setLayout(layout)
        dlg.resize(600, 400)
        dlg.exec_()

    def appendLog(self, msg):
        self.logText.append(msg)

    def captureLogs(self):
        """
        Route standard logging to the text box.
        """
        logging.getLogger().handlers = []
        class LogHandler(logging.Handler):
            def emit(self2, record):
                self.logText.append(self2.format(record))

        handler = LogHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)

    def openInFinder(self, path):
        """
        Cross-platform open folder.
        """
        if sys.platform.startswith("darwin"):
            subprocess.run(["open", path])
        elif os.name == "nt":
            os.startfile(path)
        else:
            subprocess.run(["xdg-open", path])

    def closeEvent(self, event):
        """
        Try to ensure no active threads are running to avoid
        QThread: Destroyed while thread is still running error.
        """
        still_running = [t for t in self.threads if t.isRunning()]
        if still_running:
            # Optionally, ask user or forcibly wait
            for t in still_running:
                t.quit()
                t.wait()  # wait for them to clean up
        super().closeEvent(event)


###############################################################################
#                               MAIN ENTRY
###############################################################################

def main():
    setup_logging()
    app = QApplication(sys.argv)
    gui = RepoSaverGUI()
    gui.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
