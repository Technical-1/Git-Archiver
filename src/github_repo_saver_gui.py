#!/usr/bin/env python3
"""
github_repo_saver_gui.py

A simple PyQt-based GUI allowing the user to select a list of GitHub repo URLs,
then call the archiving logic defined in github_repo_saver.py.
"""

import sys
import os
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QFileDialog,
    QTextEdit,
    QMessageBox
)
# If you prefer PySide2 or PySide6, adjust imports accordingly.

import logging
from github_repo_saver import main as run_archiver

class RepoSaverGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.setWindowTitle("GitHub Repo Saver GUI")

        # Instruction Label
        self.instructionLabel = QLabel("Select the text file containing GitHub repo URLs:", self)

        # Text field for selected file path
        self.filePathEdit = QLineEdit(self)
        self.filePathEdit.setPlaceholderText("Path to repo list (e.g., repos.txt)")

        # Browse Button
        self.browseButton = QPushButton("Browse...", self)
        self.browseButton.clicked.connect(self.browseFile)

        # Log/Output Area
        self.logTextEdit = QTextEdit(self)
        self.logTextEdit.setReadOnly(True)

        # Run Button
        self.runButton = QPushButton("Run Archiver", self)
        self.runButton.clicked.connect(self.runArchiver)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.instructionLabel)

        layout.addWidget(self.filePathEdit)
        layout.addWidget(self.browseButton)
        layout.addWidget(self.runButton)
        layout.addWidget(self.logTextEdit)

        self.setLayout(layout)

    def browseFile(self):
        file_dialog = QFileDialog(self, "Open Repo List", os.getcwd(), "Text Files (*.txt)")
        if file_dialog.exec_():
            selected_files = file_dialog.selectedFiles()
            if selected_files:
                self.filePathEdit.setText(selected_files[0])

    def runArchiver(self):
        # Clear log text
        self.logTextEdit.clear()

        repo_list_path = self.filePathEdit.text().strip()
        if not repo_list_path or not os.path.isfile(repo_list_path):
            QMessageBox.warning(self, "Invalid File", "Please specify a valid repo list file path.")
            return

        # Capture logging output
        logging.getLogger().handlers = []

        # Create a handler to capture logs
        class LogCaptureHandler(logging.Handler):
            def emit(self, record):
                msg = self.format(record)
                self.logTextEdit.append(msg)

        handler = LogCaptureHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
        logging.getLogger().setLevel(logging.INFO)
        logging.getLogger().addHandler(handler)
        self.logTextEdit.append("Starting GitHub Repo Saver...")

        # Run archiver logic by simulating command-line args
        saved_argv = sys.argv
        try:
            sys.argv = ["github_repo_saver_gui.py", "--repo-list", repo_list_path]
            run_archiver()
        except Exception as e:
            logging.error(f"Error running archiver: {e}")
        finally:
            sys.argv = saved_argv

        self.logTextEdit.append("Archiver completed!\n")

def main():
    app = QApplication(sys.argv)
    gui = RepoSaverGUI()
    gui.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()