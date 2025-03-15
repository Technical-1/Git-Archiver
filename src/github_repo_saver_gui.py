#!/usr/bin/env python3
"""
Single-file GitHub Repo Saver with PyQt:
- JSON-based storage (cloned_repos.json) tracks repos and metadata.
- Adds new repos (single or bulk from .txt), clones/updates them in threads.
- If `git pull` actually fetches new commits, we create a timestamped archive.
- Table columns: URL, Description, Status, Last Cloned, Last Updated, and individual columns for:
    "Open Folder", "Archives", "README" => so the buttons don't get cut off.
- Also a "Bulk Upload" button that loads a .txt of multiple repos.

Dependencies:
    pip install pyqt5 requests
"""

import sys
import os
import json
import subprocess
import logging
import datetime
import requests
import tempfile

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QLabel, QLineEdit, QTextEdit, QMessageBox,
    QDialog, QListWidget, QListWidgetItem, QFileDialog,
    QDialog, QVBoxLayout, QHBoxLayout, QWidget
)


###############################################################################
#                               DATA & LOGIC
###############################################################################

CLONED_JSON_PATH = "cloned_repos.json"
DATA_FOLDER = "data"  # local folder where repos will be cloned


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def validate_repo_url(url: str) -> bool:
    """
    Basic check: must start with https://github.com/
    """
    return url.startswith("https://github.com/")


def load_cloned_info() -> dict:
    """
    Load 'cloned_repos.json' which tracks each repo's data:
      {
        "https://github.com/user/repo.git": {
          "last_cloned": "YYYY-MM-DD HH:MM:SS",
          "last_updated": "YYYY-MM-DD HH:MM:SS",
          "local_path": "data/repo.git",
          "online_description": "...",
          "status": "active"/"archived"/"deleted"/"error",
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
    """
    Write the updated dictionary to 'cloned_repos.json'
    """
    with open(CLONED_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def current_timestamp() -> str:
    """Return the current local time as a string."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_online_repo_description(owner, repo_name):
    """
    Query GitHub API to fetch the description + archived/deleted status.
    Returns (description_str, is_archived_bool, is_deleted_bool).
    """
    api_url = f"https://api.github.com/repos/{owner}/{repo_name}"
    try:
        resp = requests.get(api_url, headers={"Accept": "application/vnd.github.v3+json"}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            desc = data.get("description", "") or ""
            archived = data.get("archived", False)
            return desc, archived, False
        elif resp.status_code == 404:
            return "", False, True  # repo does not exist or is private/deleted
        else:
            logging.warning(f"Unexpected status code {resp.status_code} fetching {owner}/{repo_name}")
            return "", False, False
    except requests.RequestException as e:
        logging.warning(f"Failed to fetch {owner}/{repo_name}: {e}")
        return "", False, False


def create_versioned_archive(repo_path: str):
    """
    Compress the entire repo folder into a timestamped archive within repo_path/versions/.
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    versions_folder = os.path.join(repo_path, "versions")
    os.makedirs(versions_folder, exist_ok=True)

    # We'll copy the entire repo into a subfolder first if you like, or just tar directly.
    # For simplicity, let's just tar the current repo. Use 'cp -r' if you prefer a subfolder snapshot.
    archive_path = os.path.join(versions_folder, f"{timestamp}.tar.xz")

    logging.info(f"Creating new archive: {archive_path}")
    try:
        subprocess.run(["tar", "-cJf", archive_path, "-C", repo_path, "."], check=True)
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to create archive for {repo_path}: {e}")


def clone_or_update_repo(repo_url: str):
    """
    - Load existing JSON record (or create a new one).
    - Check GitHub for description/archived/deleted -> 'status'.
    - If not "deleted", clone or pull.
      - If new commits are actually pulled, do an archive.
      - If brand-new clone, optionally archive as an initial snapshot.
    - Save JSON updates.
    """
    repos_data = load_cloned_info()
    repo_name = repo_url.rstrip("/").split("/")[-1]  # e.g. "some-repo.git"
    repo_path = os.path.join(DATA_FOLDER, repo_name)

    # Parse out owner/repo
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

    record["online_description"] = desc
    record["status"] = status
    record["local_path"] = repo_path

    if status != "deleted":
        # If local folder exists, do a pull
        if os.path.isdir(repo_path):
            logging.info(f"Pulling updates for {repo_url}")
            pull_proc = subprocess.run(
                ["git", "-C", repo_path, "pull"],
                check=False,  # handle errors ourselves
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
            if pull_proc.returncode == 0:
                record["last_cloned"] = now
                record["last_updated"] = now

                # Check if we actually got new commits
                pull_out = pull_proc.stdout.lower()
                if "already up to date" not in pull_out and "up to date" not in pull_out:
                    # We appear to have new commits
                    create_versioned_archive(repo_path)
            else:
                logging.error(f"Failed to pull {repo_url}: {pull_proc.stdout}")
        else:
            # clone new
            logging.info(f"Cloning {repo_url} -> {repo_path}")
            os.makedirs(DATA_FOLDER, exist_ok=True)
            clone_proc = subprocess.run(["git", "clone", repo_url, repo_path],
                                        check=False, stdout=subprocess.PIPE, text=True)
            if clone_proc.returncode == 0:
                record["last_cloned"] = now
                record["last_updated"] = now

                # Optionally do an immediate initial archive:
                create_versioned_archive(repo_path)
            else:
                logging.error(f"Failed to clone {repo_url}: {clone_proc.stdout}")

    else:
        logging.warning(f"Skipping clone - GitHub indicates {repo_url} is deleted.")

    repos_data[repo_url] = record
    save_cloned_info(repos_data)


def detect_deleted_or_archived():
    """
    For each repo in JSON, re-check GitHub for archived/deleted status and update.
    """
    data = load_cloned_info()
    changed = False
    for repo_url, rec in data.items():
        parts = repo_url.replace("https://github.com/", "").split("/")
        if len(parts) < 2:
            continue
        owner, raw_repo = parts[0], parts[1].replace(".git", "")
        desc, is_arch, is_del = get_online_repo_description(owner, raw_repo)
        if is_del:
            rec["status"] = "deleted"
        elif is_arch:
            rec["status"] = "archived"
        else:
            rec["status"] = "active"
        rec["online_description"] = desc
        changed = True

    if changed:
        save_cloned_info(data)


###############################################################################
#                               WORKER THREAD
###############################################################################

class CloneWorker(QThread):
    """
    Runs clone_or_update_repo(repo_url) in a background thread.
    """
    logSignal = pyqtSignal(str)     # to display log text in the GUI
    finishedSignal = pyqtSignal(str)  # emits the repo_url when done

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
#                               ARCHIVES DIALOG
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
    - Loads all repos from JSON on startup, each displayed in table columns:
       0: Repo URL
       1: Description
       2: Status
       3: Last Cloned
       4: Last Updated
       5: "Open Folder" button
       6: "Archives" button
       7: "README" button
    - Add new repo (single or bulk from .txt).
    - Refresh statuses => re-check archived/deleted from GitHub.
    - Archives automatically created after new commits are fetched.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("GitHub Repo Saver (Single-file)")
        self.threads = []  # Keep references to background CloneWorker threads
        self.repoData = {}
        self.initUI()
        self.loadRepos()  # auto-load from JSON

    def initUI(self):
        mainLayout = QVBoxLayout()

        # Table
        self.repoTable = QTableWidget()
        self.repoTable.setColumnCount(8)
        self.repoTable.setHorizontalHeaderLabels([
            "Repo URL",
            "Description",
            "Status",
            "Last Cloned",
            "Last Updated",
            "Open Folder",
            "Archives",
            "README"
        ])
        self.repoTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        mainLayout.addWidget(self.repoTable)

        # Add / Bulk / Refresh
        rowLayout = QHBoxLayout()
        self.addRepoEdit = QLineEdit()
        self.addRepoEdit.setPlaceholderText("Paste a single GitHub repo URL (https://github.com/...)")
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

        mainLayout.addLayout(rowLayout)

        # Logging
        self.logText = QTextEdit()
        self.logText.setReadOnly(True)
        mainLayout.addWidget(self.logText)

        self.setLayout(mainLayout)
        self.resize(1200, 600)

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

        # 0. Repo URL
        item_url = QTableWidgetItem(repo_url)
        self.repoTable.setItem(row_idx, 0, item_url)

        # 1. Description
        desc = info.get("online_description", "")
        item_desc = QTableWidgetItem(desc)
        self.repoTable.setItem(row_idx, 1, item_desc)

        # 2. Status
        status = info.get("status", "")
        item_status = QTableWidgetItem(status)
        self.repoTable.setItem(row_idx, 2, item_status)

        # 3. Last Cloned
        last_cloned = info.get("last_cloned", "")
        self.repoTable.setItem(row_idx, 3, QTableWidgetItem(last_cloned))

        # 4. Last Updated
        last_updated = info.get("last_updated", "")
        self.repoTable.setItem(row_idx, 4, QTableWidgetItem(last_updated))

        # 5. "Open Folder" button
        btn_folder = QPushButton("Folder")
        btn_folder.clicked.connect(lambda _, url=repo_url: self.openRepoFolder(url))
        self.repoTable.setCellWidget(row_idx, 5, btn_folder)

        # 6. "Archives" button
        btn_arch = QPushButton("Archives")
        btn_arch.clicked.connect(lambda _, url=repo_url: self.showArchives(url))
        self.repoTable.setCellWidget(row_idx, 6, btn_arch)

        # 7. "README" button
        btn_readme = QPushButton("README")
        btn_readme.clicked.connect(lambda _, url=repo_url: self.viewReadme(url))
        self.repoTable.setCellWidget(row_idx, 7, btn_readme)

    def addRepo(self):
        """Add a single repo from the text field."""
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

        # Insert a placeholder in memory
        self.repoData[url] = {
            "last_cloned": "",
            "last_updated": "",
            "local_path": os.path.join(DATA_FOLDER, url.split("/")[-1]),
            "online_description": "",
            "status": "pending"
        }
        save_cloned_info(self.repoData)

        # Add row
        self.addTableRow(url, self.repoData[url])
        self.addRepoEdit.clear()

        # Clone in background
        worker = CloneWorker(url)
        self.threads.append(worker)  # keep reference
        worker.logSignal.connect(self.appendLog)
        worker.finishedSignal.connect(self.cloneFinished)
        worker.start()

    def bulkUpload(self):
        """
        Prompt for a .txt file, read each line as a GitHub URL, skip duplicates,
        and process similarly to addRepo.
        """
        dlg = QFileDialog(self, "Select .txt file with GitHub URLs", os.getcwd(), "Text Files (*.txt)")
        if dlg.exec_():
            selected = dlg.selectedFiles()
            if not selected:
                return
            txt_file = selected[0]
            if not os.path.isfile(txt_file):
                QMessageBox.warning(self, "File Error", "Selected file not found.")
                return

            with open(txt_file, "r", encoding="utf-8") as f:
                lines = [ln.strip() for ln in f if ln.strip()]

            added_count = 0
            for line in lines:
                url = line
                if not validate_repo_url(url):
                    continue
                if not url.endswith(".git"):
                    url += ".git"
                if url not in self.repoData:
                    # Create a placeholder
                    self.repoData[url] = {
                        "last_cloned": "",
                        "last_updated": "",
                        "local_path": os.path.join(DATA_FOLDER, url.split("/")[-1]),
                        "online_description": "",
                        "status": "pending"
                    }
                    added_count += 1
                    # Show row
                    self.addTableRow(url, self.repoData[url])
                    # Spawn clone
                    worker = CloneWorker(url)
                    self.threads.append(worker)
                    worker.logSignal.connect(self.appendLog)
                    worker.finishedSignal.connect(self.cloneFinished)
                    worker.start()

            save_cloned_info(self.repoData)
            self.appendLog(f"Bulk upload added {added_count} new repos.\n")


    def cloneFinished(self, repo_url):
        """
        Called when a worker finishes. Refresh that row from JSON.
        """
        self.appendLog(f"Clone/Update finished: {repo_url}")
        self.repoData = load_cloned_info()
        self.updateRowForRepo(repo_url)

    def updateRowForRepo(self, repo_url):
        """Refresh the table row for the given repo_url from self.repoData."""
        info = self.repoData.get(repo_url, {})
        row_count = self.repoTable.rowCount()
        for r in range(row_count):
            cell = self.repoTable.item(r, 0)
            if cell and cell.text() == repo_url:
                self.repoTable.item(r, 1).setText(info.get("online_description", ""))
                self.repoTable.item(r, 2).setText(info.get("status", ""))
                self.repoTable.item(r, 3).setText(info.get("last_cloned", ""))
                self.repoTable.item(r, 4).setText(info.get("last_updated", ""))
                break

    def refreshStatuses(self):
        """
        Re-check archived/deleted status for all repos in JSON, update table.
        """
        self.captureLogs()
        detect_deleted_or_archived()
        self.repoData = load_cloned_info()
        self.populateTable()
        self.appendLog("Refreshed repo statuses.\n")

    def openRepoFolder(self, repo_url):
        info = self.repoData.get(repo_url, {})
        path = info.get("local_path", "")
        if path and os.path.isdir(path):
            self.openInFinder(path)
        else:
            QMessageBox.information(self, "Folder Not Found", f"No local folder for {repo_url}")

    def showArchives(self, repo_url):
        info = self.repoData.get(repo_url, {})
        path = info.get("local_path", "")
        if not path or not os.path.isdir(path):
            QMessageBox.information(self, "Repo Not Found", "Clone/update the repo first.")
            return
        dlg = ArchivedVersionsDialog(path, self)
        dlg.exec_()

    def viewReadme(self, repo_url):
        info = self.repoData.get(repo_url, {})
        path = info.get("local_path", "")
        if not path or not os.path.isdir(path):
            QMessageBox.information(self, "Repo Not Found", "Clone/update the repo first.")
            return
        readme_path = os.path.join(path, "README.md")
        if not os.path.isfile(readme_path):
            QMessageBox.information(self, "No README", "No README.md found.")
            return

        with open(readme_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        dlg = QDialog(self)
        dlg.setWindowTitle(f"README - {os.path.basename(path)}")
        lyt = QVBoxLayout()
        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setPlainText(content)
        lyt.addWidget(txt)
        dlg.setLayout(lyt)
        dlg.resize(600, 400)
        dlg.exec_()

    def openInFinder(self, path):
        """Cross-platform folder open."""
        if sys.platform.startswith("darwin"):
            subprocess.run(["open", path])
        elif os.name == "nt":
            os.startfile(path)
        else:
            subprocess.run(["xdg-open", path])

    def appendLog(self, msg):
        self.logText.append(msg)

    def captureLogs(self):
        """Route Python logging to self.logText."""
        logging.getLogger().handlers = []
        class LogHandler(logging.Handler):
            def emit(self2, record):
                self.logText.append(self2.format(record))

        handler = LogHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        )
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)

    def closeEvent(self, event):
        """
        Attempt to gracefully stop any running threads before closing,
        to avoid the "QThread: Destroyed while thread is still running" error.
        """
        still_running = [t for t in self.threads if t.isRunning()]
        if still_running:
            for t in still_running:
                t.quit()
                t.wait()
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
