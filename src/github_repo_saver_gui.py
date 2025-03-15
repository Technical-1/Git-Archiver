#!/usr/bin/env python3
"""
github_repo_saver_gui.py

PyQt-based GUI for GitHub Repo Saver:
- Single or bulk addition of GitHub repos (stored in a text file).
- Automatic detection & skipping of duplicates using 'main-links.txt'.
- Each repo is cloned/updated exactly once (subsequent runs do a pull only),
  thanks to cloned_repos.json from github_repo_saver.py.

Modified so that *as each repo is cloned*, we add a new row to the table.
"""

import sys
import os
import subprocess
import logging
import tempfile
from datetime import datetime

import requests
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout,
    QFileDialog, QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QHBoxLayout, QTextEdit, QDialog, QListWidget, QListWidgetItem
)

# Import saver logic
from github_repo_saver import (
    main as run_archiver,
    check_for_updates,
    create_versioned_archive,
    clone_or_update_repo,
    detect_deleted_or_archived,
    validate_repo_url
)

class CloneWorker(QThread):
    """
    Thread worker to clone or update a single repository.
    Emits signals to update the GUI when finished or to display logs.
    """
    logSignal = pyqtSignal(str)
    finishedSignal = pyqtSignal(str, str)  
    # finishedSignal will emit (repo_url, status_message)

    def __init__(self, url, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        try:
            self.logSignal.emit(f"Cloning/Updating: {self.url}")
            clone_or_update_repo(self.url, base_path="data")
            self.logSignal.emit(f"Finished cloning/updating: {self.url}")
            status_msg = "Cloned/Updated"
        except Exception as e:
            status_msg = f"Error: {e}"
            self.logSignal.emit(status_msg)

        self.finishedSignal.emit(self.url, status_msg)

class ArchivedVersionsDialog(QDialog):
    """
    Dialog to list and open archived versions for a given repository.
    """
    def __init__(self, repo_path, parent=None):
        super().__init__(parent)
        self.repo_path = repo_path
        self.setWindowTitle("Archived Versions - {}".format(os.path.basename(repo_path)))
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
            else:
                if item.endswith(".tar.xz"):
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

class RepoSaverGUI(QWidget):
    """
    Main GUI for GitHub Repo Saver:
    - Table is updated row-by-row each time a single repo is cloned/updated.
    - Single/Bulk Repo addition to 'main-links.txt'
    - Then user can clone all repos from a specified .txt file or run archiver, etc.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GitHub Repo Saver - GUI")
        self.initUI()

    def initUI(self):
        mainLayout = QVBoxLayout()

        # File selection row
        topLayout = QHBoxLayout()
        self.instructionLabel = QLabel("Select the text file containing GitHub repo URLs:")
        topLayout.addWidget(self.instructionLabel)

        self.filePathEdit = QLineEdit()
        self.filePathEdit.setPlaceholderText("Path to repo list (e.g., repos.txt)")
        topLayout.addWidget(self.filePathEdit)

        self.browseButton = QPushButton("Browse...")
        self.browseButton.clicked.connect(self.browseFile)
        topLayout.addWidget(self.browseButton)
        mainLayout.addLayout(topLayout)

        # Repo Table
        self.repoTable = QTableWidget()
        self.repoTable.setColumnCount(8)
        self.repoTable.setHorizontalHeaderLabels([
            "URL",
            "Description",
            "Status",
            "Last Cloned",
            "Last Archived",
            "Open Folder",
            "Archives",
            "View README"
        ])
        self.repoTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        mainLayout.addWidget(self.repoTable)

        # Control buttons (Load, Run, Refresh)
        buttonLayout = QHBoxLayout()
        self.loadButton = QPushButton("Clone Repos")
        self.loadButton.clicked.connect(self.cloneReposFromFile)
        buttonLayout.addWidget(self.loadButton)

        self.runButton = QPushButton("Run Archiver")
        self.runButton.clicked.connect(self.runArchiver)
        buttonLayout.addWidget(self.runButton)

        self.refreshButton = QPushButton("Refresh Status")
        self.refreshButton.clicked.connect(self.refreshStatus)
        buttonLayout.addWidget(self.refreshButton)
        mainLayout.addLayout(buttonLayout)

        # Add single/bulk
        addRepoLayout = QHBoxLayout()
        self.singleRepoEdit = QLineEdit()
        self.singleRepoEdit.setPlaceholderText("Paste a single GitHub repo URL...")
        addRepoLayout.addWidget(self.singleRepoEdit)

        self.addRepoButton = QPushButton("Add Single Repo")
        self.addRepoButton.clicked.connect(self.addSingleRepo)
        addRepoLayout.addWidget(self.addRepoButton)

        self.bulkUploadButton = QPushButton("Bulk Upload (.txt)")
        self.bulkUploadButton.clicked.connect(self.bulkUploadRepos)
        addRepoLayout.addWidget(self.bulkUploadButton)

        mainLayout.addLayout(addRepoLayout)

        # Logging
        self.logTextEdit = QTextEdit()
        self.logTextEdit.setReadOnly(True)
        mainLayout.addWidget(self.logTextEdit)

        self.setLayout(mainLayout)
        self.resize(1200, 600)

    def browseFile(self):
        dialog = QFileDialog(self, "Open Repo List", os.getcwd(), "Text Files (*.txt)")
        if dialog.exec_():
            selected = dialog.selectedFiles()
            if selected:
                self.filePathEdit.setText(selected[0])

    def cloneReposFromFile(self):
        """
        Read lines from self.filePathEdit, for each valid repo, spawn a worker thread
        to clone/update. As each completes, we add a row to the table.
        """
        path = self.filePathEdit.text().strip()
        if not path or not os.path.isfile(path):
            QMessageBox.warning(self, "Invalid File", "Please specify a valid repo list file path.")
            return

        # Clear the table for a fresh start
        self.repoTable.setRowCount(0)

        with open(path, "r", encoding="utf-8") as f:
            lines = [ln.strip() for ln in f if ln.strip()]

        # Start a worker for each line
        for url in lines:
            if not url.endswith(".git"):
                url += ".git"

            if validate_repo_url(url):
                worker = CloneWorker(url)
                worker.logSignal.connect(self.appendLog)
                worker.finishedSignal.connect(self.cloneFinished)
                worker.start()
            else:
                self.logTextEdit.append(f"Invalid URL skipped: {url}")

    def cloneFinished(self, url, statusMsg):
        """
        Called when a single repo clone/update operation finishes.
        We'll insert a new row with the relevant info.
        """
        rowIndex = self.repoTable.rowCount()
        self.repoTable.insertRow(rowIndex)

        # Basic columns
        self.repoTable.setItem(rowIndex, 0, QTableWidgetItem(url))  # URL
        self.repoTable.setItem(rowIndex, 1, QTableWidgetItem(""))   # Description (placeholder)
        self.repoTable.setItem(rowIndex, 2, QTableWidgetItem(statusMsg))  # Status

        # Evaluate lastCloned, lastArchived
        lastCloned, lastArchived = self.getLocalRepoTimestamps(url)
        self.repoTable.setItem(rowIndex, 3, QTableWidgetItem(lastCloned))
        self.repoTable.setItem(rowIndex, 4, QTableWidgetItem(lastArchived))

        # Add buttons
        btn_open = QPushButton("Open Folder")
        btn_open.clicked.connect(lambda _, u=url: self.openRepoFolder(u))
        self.repoTable.setCellWidget(rowIndex, 5, btn_open)

        btn_arch = QPushButton("Archives")
        btn_arch.clicked.connect(lambda _, u=url: self.showArchives(u))
        self.repoTable.setCellWidget(rowIndex, 6, btn_arch)

        btn_readme = QPushButton("View README")
        btn_readme.clicked.connect(lambda _, u=url: self.viewReadme(u))
        self.repoTable.setCellWidget(rowIndex, 7, btn_readme)

    def getLocalRepoTimestamps(self, repo_url):
        """
        Check if local folder is present, return lastCloned & lastArchived.
        """
        repo_name = repo_url.rstrip("/").split("/")[-1]
        repo_path = os.path.join("data", repo_name)

        if os.path.isdir(repo_path):
            last_cloned_dt = datetime.fromtimestamp(os.path.getmtime(repo_path))
            lastCloned = last_cloned_dt.strftime("%Y-%m-%d %H:%M:%S")

            versions_path = os.path.join(repo_path, "versions")
            if os.path.isdir(versions_path):
                latest_time = None
                for item in os.listdir(versions_path):
                    item_path = os.path.join(versions_path, item)
                    t = os.path.getmtime(item_path)
                    if latest_time is None or t > latest_time:
                        latest_time = t
                if latest_time:
                    lastArchived = datetime.fromtimestamp(latest_time).strftime("%Y-%m-%d %H:%M:%S")
                else:
                    lastArchived = ""
            else:
                lastArchived = ""
        else:
            lastCloned = ""
            lastArchived = ""

        return lastCloned, lastArchived

    def addSingleRepo(self):
        """
        Read the single URL from self.singleRepoEdit, append it to main-links.txt if unique.
        """
        url = self.singleRepoEdit.text().strip()
        if not url:
            QMessageBox.warning(self, "No URL", "Please enter a GitHub repo URL.")
            return
        if not url.startswith("https://github.com/"):
            QMessageBox.warning(self, "Invalid URL", "URL must start with https://github.com/")
            return

        # We'll store the repos in 'main-links.txt' (feel free to rename if needed)
        links_path = os.path.join(os.path.dirname(__file__), "main-links.txt")
        if not os.path.isfile(links_path):
            open(links_path, "w").close()

        with open(links_path, "r", encoding="utf-8") as f:
            existing_lines = [ln.strip() for ln in f if ln.strip()]

        if url in existing_lines:
            QMessageBox.information(self, "Duplicate", "That repo URL already exists.")
            return

        with open(links_path, "a", encoding="utf-8") as f:
            f.write(url + "\n")

        self.logTextEdit.append(f"Added single repo: {url} to main-links.txt")
        self.singleRepoEdit.clear()

    def bulkUploadRepos(self):
        """
        Prompt for a .txt file, read each line, skip duplicates, append to main-links.txt
        """
        dialog = QFileDialog(self, "Select .txt file with repo URLs", os.getcwd(), "Text Files (*.txt)")
        if dialog.exec_():
            selected = dialog.selectedFiles()
            if not selected:
                return
            bulk_file = selected[0]

            if not os.path.isfile(bulk_file):
                QMessageBox.warning(self, "File Error", "Selected file not found.")
                return

            links_path = os.path.join(os.path.dirname(__file__), "main-links.txt")
            if not os.path.isfile(links_path):
                open(links_path, "w").close()

            with open(links_path, "r", encoding="utf-8") as lf:
                existing_lines = [ln.strip() for ln in lf if ln.strip()]

            with open(bulk_file, "r", encoding="utf-8") as bf:
                lines_to_add = [ln.strip() for ln in bf if ln.strip()]

            added_count = 0
            with open(links_path, "a", encoding="utf-8") as lf:
                for line in lines_to_add:
                    if line not in existing_lines and line.startswith("https://github.com/"):
                        lf.write(line + "\n")
                        existing_lines.append(line)
                        added_count += 1

            self.logTextEdit.append(f"Bulk upload complete. Added {added_count} new repos to main-links.txt")

    def openRepoFolder(self, repo_url):
        """
        Open the local folder for the specified repo if it exists.
        """
        repo_name = repo_url.rstrip("/").split("/")[-1]
        repo_path = os.path.join("data", repo_name)
        if os.path.isdir(repo_path):
            self.openInFinder(repo_path)
        else:
            QMessageBox.information(self, "Folder Not Found", f"No folder found for {repo_url}")

    def showArchives(self, repo_url):
        """
        Show archived versions for the selected repo in a dialog.
        """
        repo_name = repo_url.rstrip("/").split("/")[-1]
        repo_path = os.path.join("data", repo_name)
        if not os.path.isdir(repo_path):
            QMessageBox.information(self, "Repo Not Found", "Clone/Update the repo first.")
            return

        dlg = ArchivedVersionsDialog(repo_path, self)
        dlg.exec_()

    def viewReadme(self, repo_url):
        """
        If README.md is present, display its contents in a dialog.
        """
        repo_name = repo_url.rstrip("/").split("/")[-1]
        repo_path = os.path.join("data", repo_name)
        readme_path = os.path.join(repo_path, "README.md")
        if not os.path.isfile(readme_path):
            QMessageBox.information(self, "No README Found", "No README.md found.")
            return

        with open(readme_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        dlg = QDialog(self)
        dlg.setWindowTitle(f"README - {repo_name}")
        layout = QVBoxLayout()
        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setPlainText(content)
        layout.addWidget(txt)
        dlg.setLayout(layout)
        dlg.resize(600, 400)
        dlg.exec_()

    def runArchiver(self):
        """
        Calls the archiver logic via 'github_repo_saver.py --repo-list <path>'.
        """
        path = self.filePathEdit.text().strip()
        if not path or not os.path.isfile(path):
            QMessageBox.warning(self, "Invalid File", "Please specify a valid repo list file path.")
            return

        self.captureLogs()
        self.logTextEdit.append("Running archiver on all valid repos...")

        saved_argv = sys.argv
        try:
            # Rebuild sys.argv to emulate command line usage
            sys.argv = ["github_repo_saver_gui.py", "--repo-list", path]
            run_archiver()
        except Exception as e:
            logging.error(f"Error running archiver: {e}")
        finally:
            sys.argv = saved_argv

        self.logTextEdit.append("Archiver completed.\n")
        self.refreshStatus()

    def refreshStatus(self):
        """
        For each row in the table, re-check lastCloned/lastArchived. 
        Then check if archived or deleted on GitHub.
        """
        self.captureLogs()

        # Gather all repos from the table
        row_count = self.repoTable.rowCount()
        urls = []
        for row in range(row_count):
            item = self.repoTable.item(row, 0)
            if item:
                urls.append(item.text())

        # Refresh local info in the table
        for row in range(row_count):
            item = self.repoTable.item(row, 0)
            if not item:
                continue
            url = item.text()
            lastCloned, lastArchived = self.getLocalRepoTimestamps(url)
            self.repoTable.setItem(row, 3, QTableWidgetItem(lastCloned))
            self.repoTable.setItem(row, 4, QTableWidgetItem(lastArchived))

        # Check archived/deleted in remote
        detect_deleted_or_archived(urls)

        self.logTextEdit.append("Refreshed repo statuses.\n")

    def captureLogs(self):
        """
        Direct logging output to self.logTextEdit.
        """
        logging.getLogger().handlers = []

        class LogCaptureHandler(logging.Handler):
            def emit(self2, record):
                msg = self2.format(record)
                self.logTextEdit.append(msg)

        handler = LogCaptureHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", 
                              datefmt="%Y-%m-%d %H:%M:%S"))
        logging.getLogger().setLevel(logging.INFO)
        logging.getLogger().addHandler(handler)

    def appendLog(self, text):
        self.logTextEdit.append(text)

    def openInFinder(self, path):
        """
        Cross-platform way to open a path in the default file explorer.
        """
        if sys.platform.startswith("darwin"):
            subprocess.run(["open", path])
        elif os.name == "nt":
            os.startfile(path)
        else:
            subprocess.run(["xdg-open", path])


def main():
    app = QApplication(sys.argv)
    gui = RepoSaverGUI()
    gui.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
