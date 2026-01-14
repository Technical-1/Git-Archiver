"""
Dialog windows for Git-Archiver.
"""

import os
import sys
import logging
import tempfile
import subprocess
import requests

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QListWidgetItem, QMessageBox
)

from ..config import load_settings, save_settings
from ..github_api import get_rate_limit_status


class ArchivedVersionsDialog(QDialog):
    """
    Dialog showing all archived versions of a repository.

    Users can:
    - See all timestamped archives
    - Extract an archive to view its contents
    - Open the extracted folder
    """

    def __init__(self, repo_url, repo_path, parent=None):
        super().__init__(parent)
        self.repo_url = repo_url
        self.repo_path = repo_path
        self.temp_dirs = []

        self.setWindowTitle(f"Archives for {repo_url}")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

        layout = QVBoxLayout()

        # Title label
        title_label = QLabel(f"Archived versions of:\n{repo_url}")
        title_label.setWordWrap(True)
        layout.addWidget(title_label)

        # List of archives
        self.archivesList = QListWidget()
        layout.addWidget(self.archivesList)

        # Populate the list
        self.loadArchives()

        # Buttons
        buttonLayout = QHBoxLayout()

        extractBtn = QPushButton("Extract Selected")
        extractBtn.clicked.connect(self.extractSelected)
        buttonLayout.addWidget(extractBtn)

        closeBtn = QPushButton("Close")
        closeBtn.clicked.connect(self.accept)
        buttonLayout.addWidget(closeBtn)

        layout.addLayout(buttonLayout)
        self.setLayout(layout)

    def loadArchives(self):
        """Load list of archives from the versions folder"""
        versions_path = os.path.join(self.repo_path, "versions")

        if not os.path.exists(versions_path):
            self.archivesList.addItem("No archives found")
            return

        archives = []
        for f in os.listdir(versions_path):
            if f.endswith(".tar.xz"):
                full_path = os.path.join(versions_path, f)
                size = os.path.getsize(full_path)
                size_str = self._format_size(size)
                archives.append((f, full_path, size_str))

        # Sort by name (timestamp) descending
        archives.sort(key=lambda x: x[0], reverse=True)

        if not archives:
            self.archivesList.addItem("No archives found")
            return

        for name, path, size in archives:
            item = QListWidgetItem(f"{name} ({size})")
            item.setData(Qt.UserRole, path)
            self.archivesList.addItem(item)

    def _format_size(self, size: int) -> str:
        """Format file size in human-readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def extractSelected(self):
        """Extract the selected archive to a temporary directory"""
        item = self.archivesList.currentItem()
        if not item:
            QMessageBox.warning(self, "No Selection", "Please select an archive to extract")
            return

        archive_path = item.data(Qt.UserRole)
        if not archive_path or not os.path.exists(archive_path):
            QMessageBox.warning(self, "Not Found", "Archive file not found")
            return

        # Create a temporary directory
        temp_dir = tempfile.mkdtemp(prefix="git_archiver_")
        self.temp_dirs.append(temp_dir)

        try:
            # Extract the archive
            subprocess.run(
                ["tar", "-xJf", archive_path, "-C", temp_dir],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            # Open the extracted folder
            self._open_folder(temp_dir)

            QMessageBox.information(
                self,
                "Extracted",
                f"Archive extracted to:\n{temp_dir}\n\nThe folder will be cleaned up when you close this dialog."
            )

        except subprocess.CalledProcessError as e:
            QMessageBox.critical(self, "Error", f"Failed to extract archive:\n{e}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Unexpected error:\n{e}")

    def _open_folder(self, path: str):
        """Open a folder in the system file browser"""
        if sys.platform == "darwin":
            subprocess.run(["open", path])
        elif sys.platform == "win32":
            subprocess.run(["explorer", path])
        else:
            subprocess.run(["xdg-open", path])

    def closeEvent(self, event):
        """Clean up temporary directories when the dialog is closed"""
        import shutil
        for temp_dir in self.temp_dirs:
            try:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception as e:
                logging.error(f"Failed to clean up temp dir {temp_dir}: {e}")
        super().closeEvent(event)


class ColumnManagerDialog(QDialog):
    """
    Dialog for managing table columns - which are visible and which are hidden.

    Users can:
    - Check/uncheck boxes to show/hide columns
    - Reset visibility to default (all shown)
    - Select/deselect all columns at once
    """

    def __init__(self, table, parent=None):
        super().__init__(parent)
        self.table = table
        self.setWindowTitle("Column Manager")
        self.resize(400, 400)

        layout = QVBoxLayout()

        # Instructions
        instructions = QLabel("Check columns to show, uncheck to hide.")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # List widget showing all columns with checkboxes
        self.columnsListWidget = QListWidget()
        layout.addWidget(self.columnsListWidget)

        # Add an entry for each column
        for i in range(table.columnCount()):
            header_item = table.horizontalHeaderItem(i)
            if header_item:
                header_text = header_item.text()
                item = QListWidgetItem(header_text)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)

                if i not in table.hidden_columns:
                    item.setCheckState(Qt.Checked)
                else:
                    item.setCheckState(Qt.Unchecked)

                self.columnsListWidget.addItem(item)

        # Action buttons
        buttonLayout = QHBoxLayout()

        resetButton = QPushButton("Reset to Default")
        resetButton.clicked.connect(self.resetToDefault)
        buttonLayout.addWidget(resetButton)

        selectAllButton = QPushButton("Select All")
        selectAllButton.clicked.connect(self.selectAll)
        buttonLayout.addWidget(selectAllButton)

        applyButton = QPushButton("Apply")
        applyButton.clicked.connect(self.applyChanges)
        buttonLayout.addWidget(applyButton)

        cancelButton = QPushButton("Cancel")
        cancelButton.clicked.connect(self.reject)
        buttonLayout.addWidget(cancelButton)

        layout.addLayout(buttonLayout)
        self.setLayout(layout)

    def resetToDefault(self):
        """Reset all columns to be visible"""
        for i in range(self.columnsListWidget.count()):
            item = self.columnsListWidget.item(i)
            item.setCheckState(Qt.Checked)

    def selectAll(self):
        """Toggle between Select All and Deselect All"""
        sender = self.sender()

        if sender.text() == "Select All":
            for i in range(self.columnsListWidget.count()):
                self.columnsListWidget.item(i).setCheckState(Qt.Checked)
            sender.setText("Deselect All")
        else:
            for i in range(self.columnsListWidget.count()):
                self.columnsListWidget.item(i).setCheckState(Qt.Unchecked)
            sender.setText("Select All")

    def applyChanges(self):
        """Apply the column changes to the table"""
        header_texts = []
        for i in range(self.table.columnCount()):
            header_item = self.table.horizontalHeaderItem(i)
            if header_item:
                header_texts.append(header_item.text())

        for i in range(self.columnsListWidget.count()):
            item = self.columnsListWidget.item(i)
            column_name = item.text()

            if column_name in header_texts:
                column_index = header_texts.index(column_name)
                if item.checkState() == Qt.Checked:
                    self.table.showColumn(column_index)
                else:
                    self.table.hideColumn(column_index)

        self.accept()


class SettingsDialog(QDialog):
    """
    Dialog for configuring application settings.

    Allows users to:
    - Set GitHub personal access token for higher API rate limits
    - View current rate limit status
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(500)

        layout = QVBoxLayout()

        # GitHub Token section
        token_group = QVBoxLayout()
        token_label = QLabel("GitHub Personal Access Token (optional):")
        token_label.setToolTip(
            "With a token: 5000 API requests/hour\n"
            "Without token: 60 API requests/hour\n\n"
            "Create a token at: github.com/settings/tokens"
        )
        token_group.addWidget(token_label)

        self.tokenEdit = QLineEdit()
        self.tokenEdit.setPlaceholderText("ghp_xxxxxxxxxxxxxxxxxxxx")
        self.tokenEdit.setEchoMode(QLineEdit.Password)
        token_group.addWidget(self.tokenEdit)

        # Show/hide token button
        self.showTokenBtn = QPushButton("Show Token")
        self.showTokenBtn.clicked.connect(self.toggleTokenVisibility)
        token_group.addWidget(self.showTokenBtn)

        token_help = QLabel(
            '<a href="https://github.com/settings/tokens">Create a token on GitHub</a>'
        )
        token_help.setOpenExternalLinks(True)
        token_group.addWidget(token_help)

        layout.addLayout(token_group)
        layout.addSpacing(20)

        # Rate limit status
        self.rateLimitLabel = QLabel("Rate Limit Status: Checking...")
        layout.addWidget(self.rateLimitLabel)

        layout.addStretch(1)

        # Buttons
        buttonLayout = QHBoxLayout()
        self.saveBtn = QPushButton("Save")
        self.saveBtn.clicked.connect(self.saveSettings)
        buttonLayout.addWidget(self.saveBtn)

        self.cancelBtn = QPushButton("Cancel")
        self.cancelBtn.clicked.connect(self.reject)
        buttonLayout.addWidget(self.cancelBtn)

        layout.addLayout(buttonLayout)
        self.setLayout(layout)

        self.loadCurrentSettings()

    def loadCurrentSettings(self):
        """Load and display current settings"""
        settings = load_settings()
        self.tokenEdit.setText(settings.get("github_token", ""))
        self.checkRateLimit()

    def toggleTokenVisibility(self):
        """Toggle between showing and hiding the token"""
        if self.tokenEdit.echoMode() == QLineEdit.Password:
            self.tokenEdit.setEchoMode(QLineEdit.Normal)
            self.showTokenBtn.setText("Hide Token")
        else:
            self.tokenEdit.setEchoMode(QLineEdit.Password)
            self.showTokenBtn.setText("Show Token")

    def checkRateLimit(self):
        """Check current GitHub API rate limit status"""
        token = self.tokenEdit.text().strip()
        result = get_rate_limit_status(token if token else None)

        if result:
            self.rateLimitLabel.setText(
                f"Rate Limit: {result['remaining']}/{result['limit']} requests remaining"
            )
        else:
            self.rateLimitLabel.setText("Rate Limit: Could not check")

    def saveSettings(self):
        """Save settings and close dialog"""
        settings = load_settings()
        settings["github_token"] = self.tokenEdit.text().strip()
        save_settings(settings)
        self.accept()
