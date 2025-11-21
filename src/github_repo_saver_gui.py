#!/usr/bin/env python3
"""
GitHub Repo Saver GUI Application.
PyQt5-based GUI for managing GitHub repository cloning, updates, and archiving.

Dependencies:
    pip install pyqt5 requests
"""

import sys
import os
import json
import datetime
import tempfile
import threading
import queue
import subprocess
import logging
from concurrent.futures import ThreadPoolExecutor
try:
    import markdown
    MARKDOWN_AVAILABLE = True
except ImportError:
    MARKDOWN_AVAILABLE = False

# Import backend module
from repo_manager import (
    setup_logging,
    validate_repo_url,
    load_cloned_info,
    save_cloned_info,
    clone_or_update_repo,
    detect_deleted_or_archived,
    add_repo_to_database,
    get_last_auto_update_time,
    save_last_auto_update_time,
    should_run_auto_update,
    list_archives,
    get_archive_info,
    delete_archive,
    delete_repo_from_database,
    delete_multiple_repos_from_database,
    DATA_FOLDER,
)

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QRect, QPoint, QEventLoop
from PyQt5.QtGui import QKeyEvent
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QLabel, QLineEdit, QTextEdit, QMessageBox,
    QDialog, QListWidget, QListWidgetItem, QFileDialog,
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QProgressBar, QStatusBar,
    QToolTip, QMenu, QAction, QAbstractItemView, QMainWindow, QSystemTrayIcon,
    QProgressDialog, QSizePolicy
)
from PyQt5.QtGui import QColor, QCursor, QIcon, QFontMetrics


###############################################################################
#                               WORKER THREAD
###############################################################################

class CloneWorker(QThread):
    """
    Runs clone_or_update_repo(repo_url) in a background thread.
    """
    logSignal = pyqtSignal(str)     # to display log text in the GUI
    finishedSignal = pyqtSignal(str)  # emits the repo_url when done
    statusUpdateSignal = pyqtSignal(str, object)  # emits repo_url and updated info - using object instead of dict
    errorSignal = pyqtSignal(str, str)  # emits repo_url and error message

    def __init__(self, url, parent=None):
        super().__init__(parent)
        self.url = url
        self.success = False

    def run(self):
        try:
            self.logSignal.emit(f"Starting clone/update: {self.url}")
            
            # First load data to get initial status in case of GitHub API errors
            initial_data = load_cloned_info()
            if self.url in initial_data:
                self.statusUpdateSignal.emit(self.url, initial_data[self.url])
                
            # Clone/update the repo - this will also update the JSON file
            success, error_msg = clone_or_update_repo(self.url)
            self.success = success
            
            # Get updated data after the operation
            updated_data = load_cloned_info()
            if self.url in updated_data:
                self.statusUpdateSignal.emit(self.url, updated_data[self.url])
                
                # Check if there was an error during the operation
                if not success or updated_data[self.url].get("status") == "error":
                    if error_msg:
                        error_display = error_msg
                    else:
                        error_display = updated_data[self.url].get("online_description", "Unknown error")
                    self.errorSignal.emit(self.url, error_display)
                    self.logSignal.emit(f"Error processing {self.url}: {error_display}")
                else:
                    self.logSignal.emit(f"Finished clone/update: {self.url}")
            else:
                self.errorSignal.emit(self.url, "Repository data not found after clone operation")
                self.logSignal.emit(f"Error: Repository data not found after clone operation: {self.url}")
        except Exception as e:
            self.success = False
            error_msg = str(e)
            self.errorSignal.emit(self.url, error_msg)
            self.logSignal.emit(f"Unexpected error: {error_msg}")
            
            # Update the JSON with the error
            try:
                data = load_cloned_info()
                if self.url in data:
                    data[self.url]["status"] = "error"
                    data[self.url]["online_description"] = f"Error: {error_msg[:100]}"
                    save_cloned_info(data)
                    self.statusUpdateSignal.emit(self.url, data[self.url])
            except Exception as save_err:
                self.logSignal.emit(f"Failed to update error status: {save_err}")
        finally:
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
        self.temp_dirs = []  # Track temp dirs to clean up on exit

        layout = QVBoxLayout()
        
        # Add summary info at the top
        self.infoLabel = QLabel()
        self.updateInfoLabel()
        layout.addWidget(self.infoLabel)
        
        self.archivesList = QListWidget()
        layout.addWidget(self.archivesList)

        buttons_layout = QHBoxLayout()
        
        self.openButton = QPushButton("Open Selected Archive")
        self.openButton.clicked.connect(self.openSelectedArchive)
        buttons_layout.addWidget(self.openButton)
        
        self.compareButton = QPushButton("Compare with Current")
        self.compareButton.clicked.connect(self.compareWithCurrent)
        buttons_layout.addWidget(self.compareButton)
        
        self.deleteButton = QPushButton("Delete Archive")
        self.deleteButton.clicked.connect(self.deleteArchive)
        buttons_layout.addWidget(self.deleteButton)
        
        layout.addLayout(buttons_layout)
        
        self.setLayout(layout)
        self.loadArchivedVersions()

    def updateInfoLabel(self):
        """Update the summary info about archives."""
        archives = list_archives(self.repo_path)
        
        if not archives:
            self.infoLabel.setText("No archives found.")
            return
        
        # Calculate total size
        total_size = 0
        for archive_name in archives:
            archive_info = get_archive_info(self.repo_path, archive_name)
            if archive_info:
                total_size += archive_info["size"]
        
        # Format size in human-readable form
        if total_size < 1024:
            size_str = f"{total_size} bytes"
        elif total_size < 1024**2:
            size_str = f"{total_size/1024:.1f} KB"
        elif total_size < 1024**3:
            size_str = f"{total_size/1024**2:.1f} MB"
        else:
            size_str = f"{total_size/1024**3:.1f} GB"
            
        self.infoLabel.setText(f"Total archives: {len(archives)}, Total size: {size_str}")

    def loadArchivedVersions(self):
        archives = list_archives(self.repo_path)
        
        for archive_name in archives:
            archive_info = get_archive_info(self.repo_path, archive_name)
            if archive_info is None:
                continue
            
            # Format size
            size = archive_info["size"]
            if size < 1024:
                size_str = f"{size} bytes"
            elif size < 1024**2:
                size_str = f"{size/1024:.1f} KB"
            elif size < 1024**3:
                size_str = f"{size/1024**2:.1f} MB"
            else:
                size_str = f"{size/1024**3:.1f} GB"
                
            list_item = QListWidgetItem(f"{archive_info['date_str']} ({size_str})")
            list_item.setData(Qt.UserRole, archive_name)  # Store actual filename as data
            self.archivesList.addItem(list_item)

    def openSelectedArchive(self):
        selected_items = self.archivesList.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "No Selection", "Select an archive to open.")
            return

        archive_name = selected_items[0].data(Qt.UserRole)
        archive_info = get_archive_info(self.repo_path, archive_name)
        
        if archive_info is None:
            QMessageBox.critical(self, "Error", "Archive not found.")
            return
        
        archive_path = archive_info["path"]

        if os.path.isdir(archive_path):
            self.openInFinder(archive_path)
        else:
            # We assume it's a tar.xz
            temp_dir = tempfile.mkdtemp(prefix="repo_archive_")
            self.temp_dirs.append(temp_dir)  # Track for cleanup
            
            try:
                subprocess.run(["tar", "-xJf", archive_path, "-C", temp_dir], check=True)
                self.openInFinder(temp_dir)
                
                # Add info file to explain what this is
                info_path = os.path.join(temp_dir, "ARCHIVE_INFO.txt")
                with open(info_path, "w") as f:
                    f.write(f"This is an archived version of {os.path.basename(self.repo_path)}\n")
                    f.write(f"Archive date: {archive_info['date_str']}\n")
                    f.write(f"Original repo: {self.repo_path}\n")
                    f.write("\nNote: This is a temporary directory and will be deleted when you close the Archives dialog.\n")
                
            except Exception as e:
                QMessageBox.critical(self, "Extraction Error", str(e))

    def compareWithCurrent(self):
        """Compare selected archive with current version using system diff tool."""
        selected_items = self.archivesList.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "No Selection", "Select an archive to compare.")
            return
            
        archive_name = selected_items[0].data(Qt.UserRole)
        archive_info = get_archive_info(self.repo_path, archive_name)
        
        if archive_info is None:
            QMessageBox.critical(self, "Error", "Archive not found.")
            return
        
        archive_path = archive_info["path"]
        
        # Extract to temp dir
        temp_dir = tempfile.mkdtemp(prefix="repo_compare_")
        self.temp_dirs.append(temp_dir)
        
        try:
            subprocess.run(["tar", "-xJf", archive_path, "-C", temp_dir], check=True)
            
            # Try to use system diff tools based on platform
            if sys.platform.startswith("darwin"):  # macOS
                try:
                    # Try to use FileMerge/opendiff
                    subprocess.Popen(["opendiff", temp_dir, self.repo_path])
                except FileNotFoundError:
                    # Fallback to opening both folders
                    self.openInFinder(temp_dir)
                    self.openInFinder(self.repo_path)
                    QMessageBox.information(self, "Manual Compare", 
                                          "Please compare the opened folders manually.")
            elif os.name == "nt":  # Windows
                # Just open both folders, Windows has built-in comparison in Explorer
                self.openInFinder(temp_dir)
                self.openInFinder(self.repo_path)
                QMessageBox.information(self, "Manual Compare", 
                                      "Please compare the opened folders manually.")
            else:  # Linux
                try:
                    # Try meld first, then kdiff3, then fallback
                    subprocess.Popen(["meld", temp_dir, self.repo_path])
                except FileNotFoundError:
                    try:
                        subprocess.Popen(["kdiff3", temp_dir, self.repo_path])
                    except FileNotFoundError:
                        # Fallback to opening both folders
                        self.openInFinder(temp_dir)
                        self.openInFinder(self.repo_path)
                        QMessageBox.information(self, "Manual Compare", 
                                              "Please compare the opened folders manually.")
        except Exception as e:
            QMessageBox.critical(self, "Comparison Error", str(e))

    def deleteArchive(self):
        """Delete the selected archive."""
        selected_items = self.archivesList.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "No Selection", "Select an archive to delete.")
            return
            
        archive_name = selected_items[0].data(Qt.UserRole)
        
        confirm = QMessageBox.question(self, "Confirm Deletion", 
                                      f"Are you sure you want to delete:\n{archive_name}?",
                                      QMessageBox.Yes | QMessageBox.No)
                                      
        if confirm == QMessageBox.Yes:
            if delete_archive(self.repo_path, archive_name):
                self.archivesList.takeItem(self.archivesList.row(selected_items[0]))
                self.updateInfoLabel()
                QMessageBox.information(self, "Success", "Archive deleted successfully.")
            else:
                QMessageBox.critical(self, "Deletion Error", "Failed to delete archive.")

    def openInFinder(self, path):
        """Cross-platform folder open with error handling."""
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "Path Not Found", f"The path does not exist:\n{path}")
            return
        
        try:
            if sys.platform.startswith("darwin"):
                subprocess.run(["open", path], check=True, timeout=5)
            elif os.name == "nt":
                os.startfile(path)
            else:
                subprocess.run(["xdg-open", path], check=True, timeout=5)
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to open folder: {e}")
            QMessageBox.critical(self, "Error", f"Failed to open folder:\n{path}\n\nError: {str(e)}")
        except subprocess.TimeoutExpired:
            logging.error(f"Timeout opening folder: {path}")
            QMessageBox.warning(self, "Timeout", f"Timeout while trying to open folder:\n{path}")
        except Exception as e:
            logging.error(f"Unexpected error opening folder: {e}")
            QMessageBox.critical(self, "Error", f"Unexpected error opening folder:\n{path}\n\nError: {str(e)}")
            
    def closeEvent(self, event):
        """Clean up any temporary directories on close."""
        for temp_dir in self.temp_dirs:
            try:
                if os.path.exists(temp_dir):
                    import shutil
                    shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception as e:
                logging.error(f"Failed to clean up temp dir {temp_dir}: {e}")
        super().closeEvent(event)


###############################################################################
#                               MAIN GUI
###############################################################################

class EnhancedTableWidget(QTableWidget):
    """Extend QTableWidget to allow custom tooltips for cells and column management"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.viewport().installEventFilter(self)
        
        # Track hidden columns
        self.hidden_columns = set()
        
        # Set maximum tooltip width to 400 pixels
        self.max_tooltip_width = 400
        
        # Enable interactive column resizing with smooth updates
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.horizontalHeader().setStretchLastSection(False)
        
        # Improve resize responsiveness
        self.setUpdatesEnabled(True)
        
        # Set minimum column width to prevent columns from becoming too small
        self.horizontalHeader().setMinimumSectionSize(30)
        
        # Enable smooth resizing
        self.horizontalHeader().setDefaultSectionSize(100)
        
        # Setup header context menu
        self.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.horizontalHeader().customContextMenuRequested.connect(self.showHeaderContextMenu)
        
        # Setup row context menu (right-click on rows)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.showRowContextMenu)
        
        # Enable row selection
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)  # Allow multiple selection
        
        # Connect resize signals for smooth updates (without forcing processEvents)
        self.horizontalHeader().sectionResized.connect(self.onSectionResized)
        
        # Connect double click for auto-resize
        self.horizontalHeader().sectionDoubleClicked.connect(self.autoFitColumn)
        
        # Store column widths for persistence
        self.column_widths = {}
        
    def onSectionResized(self, logicalIndex, oldSize, newSize):
        """Handle section resize with smooth visual update"""
        # Store the new width
        self.column_widths[logicalIndex] = newSize
        
        # If description column was resized, recalculate all row heights
        if logicalIndex == 1:  # Description column
            # Use a small delay to ensure the resize is complete
            QTimer.singleShot(10, lambda: self._recalculateAllRowHeights())
        
        # Force immediate update of cell widgets (buttons) in this column
        # This ensures buttons resize smoothly during window resize
        for row in range(self.rowCount()):
            widget = self.cellWidget(row, logicalIndex)
            if widget:
                # Force widget to update its geometry to match the new column width
                widget.updateGeometry()
                widget.update()
        # Update viewport smoothly
        self.viewport().update()
    
    def _recalculateRowHeight(self, row_idx, description_text):
        """Recalculate row height when description column width changes"""
        if not description_text:
            self.setRowHeight(row_idx, self.verticalHeader().defaultSectionSize())
            return
        
        # Get the current description column width
        desc_col_width = self.columnWidth(1)
        if desc_col_width <= 0:
            desc_col_width = 200
        
        # Account for padding (cell padding + scrollbar area)
        available_width = max(100, desc_col_width - 20)
        
        # Calculate text height using font metrics
        font = self.font()
        font_metrics = QFontMetrics(font)
        
        # Calculate bounding rect for wrapped text
        text_rect = font_metrics.boundingRect(
            0, 0, available_width, 0,
            Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop,
            description_text
        )
        
        # Calculate number of lines needed
        line_height = font_metrics.lineSpacing()
        num_lines = max(1, (text_rect.height() // line_height) + 1)
        
        # Set row height: ensure minimum height, add padding
        row_height = max(
            self.verticalHeader().defaultSectionSize(),
            (num_lines * line_height) + 10  # 10px padding
        )
        
        self.setRowHeight(row_idx, row_height)
    
    def _recalculateAllRowHeights(self):
        """Recalculate heights for all rows based on current description column width"""
        for row in range(self.rowCount()):
            desc_item = self.item(row, 1)
            if desc_item:
                desc_text = desc_item.text()
                self._recalculateRowHeight(row, desc_text)
        
    def resizeEvent(self, event):
        """Override resize event to adjust columns on window resize"""
        super().resizeEvent(event)
        
        # When the widget is resized, update all cell widgets immediately
        # This ensures buttons resize smoothly during window resize
        if self.model() and self.model().columnCount() > 0:
            # Schedule widget updates for the next event loop iteration
            # This ensures smooth updates without blocking the resize
            QTimer.singleShot(0, self._updateAllCellWidgets)
    
    def _updateAllCellWidgets(self):
        """Update all cell widget geometries after resize"""
        for col in range(self.columnCount()):
            for row in range(self.rowCount()):
                widget = self.cellWidget(row, col)
                if widget:
                    # Force geometry update - Qt will recalculate based on cell size
                    widget.updateGeometry()
                    widget.update()
    
    def resizeColumnsToContents(self):
        """Override to improve performance"""
        super().resizeColumnsToContents()
        self.viewport().update()
        
    def eventFilter(self, obj, event):
        """Filter mouse events to show tooltips"""
        if obj is self.viewport():
            if event.type() == event.MouseMove:
                pos = event.pos()
                index = self.indexAt(pos)
                
                if index.isValid() and index.column() in [0, 1]:  # URL or Description
                    item = self.item(index.row(), index.column())
                    if item and item.text():
                        # Format the tooltip for better readability
                        text = item.text()
                        
                        # If description column and text is long, wrap it
                        if index.column() == 1 and len(text) > 60:
                            # Format long descriptions with proper word wrapping
                            words = text.split()
                            wrapped_text = ""
                            line = ""
                            
                            for word in words:
                                test_line = line + " " + word if line else word
                                if len(test_line) <= 60:
                                    line = test_line
                                else:
                                    wrapped_text += line + "\n"
                                    line = word
                            
                            if line:
                                wrapped_text += line
                                
                            # Use the wrapped text for the tooltip
                            QToolTip.showText(QCursor.pos(), wrapped_text, self)
                        else:
                            # For URLs or short descriptions, just show the text
                            QToolTip.showText(QCursor.pos(), text, self)
                    else:
                        QToolTip.hideText()
                else:
                    QToolTip.hideText()
                        
        return super().eventFilter(obj, event)
        
    def showHeaderContextMenu(self, pos):
        """Show context menu for header to allow hiding/showing columns"""
        column = self.horizontalHeader().logicalIndexAt(pos)
        if column < 0:  # Clicked outside valid columns
            return
            
        menu = QMenu(self)
        header_text = self.horizontalHeaderItem(column).text()
        
        # Create action for hiding this column
        hide_action = QAction(f"Hide '{header_text}' Column", self)
        hide_action.triggered.connect(lambda: self.hideColumn(column))
        menu.addAction(hide_action)
        
        # Add separator before the other options
        menu.addSeparator()
        
        # Add options for showing all columns
        show_all_action = QAction("Show All Columns", self)
        show_all_action.triggered.connect(self.showAllColumns)
        menu.addAction(show_all_action)
        
        # Add option to reset column widths
        reset_widths_action = QAction("Reset Column Widths", self)
        reset_widths_action.triggered.connect(self.resetColumnWidths)
        menu.addAction(reset_widths_action)
        
        # Show the menu at cursor position
        menu.exec_(self.horizontalHeader().mapToGlobal(pos))
        
    def hideColumn(self, column):
        """Hide the specified column and track it"""
        super().hideColumn(column)
        self.hidden_columns.add(column)
        
    def showColumn(self, column):
        """Show the specified column and untrack it"""
        super().showColumn(column)
        if column in self.hidden_columns:
            self.hidden_columns.remove(column)
            
    def showAllColumns(self):
        """Show all columns that were hidden"""
        for column in list(self.hidden_columns):
            self.showColumn(column)
            
    def resetColumnWidths(self):
        """Reset all column widths to proportional sizes"""
        header = self.horizontalHeader()
        total_width = self.viewport().width()
        column_count = self.columnCount()
        
        # Calculate proportional widths
        if column_count > 0:
            # URL and Description get more space
            url_width = int(total_width * 0.25)
            desc_width = int(total_width * 0.25)
            remaining_width = total_width - url_width - desc_width
            other_width = int(remaining_width / max(1, column_count - 2))
            
            # Apply widths smoothly
            header.resizeSection(0, url_width)
            header.resizeSection(1, desc_width)
            for i in range(2, column_count):
                header.resizeSection(i, other_width)
                self.column_widths[i] = other_width
            
            self.column_widths[0] = url_width
            self.column_widths[1] = desc_width
        
    def getColumnVisibilityState(self):
        """Return a dictionary of column visibility states"""
        state = {}
        for i in range(self.columnCount()):
            header_text = self.horizontalHeaderItem(i).text()
            is_visible = i not in self.hidden_columns
            state[header_text] = is_visible
        return state
        
    def setColumnVisibilityState(self, state):
        """Set column visibility based on provided state dictionary"""
        for i in range(self.columnCount()):
            header_text = self.horizontalHeaderItem(i).text()
            if header_text in state:
                if state[header_text]:
                    self.showColumn(i)
                else:
                    self.hideColumn(i)

    def autoFitColumn(self, logicalIndex):
        """Auto-resize column to fit contents on double-click"""
        # Temporarily switch to ResizeToContents mode for this column
        header = self.horizontalHeader()
        old_mode = header.sectionResizeMode(logicalIndex)
        header.setSectionResizeMode(logicalIndex, QHeaderView.ResizeToContents)
        self.resizeColumnToContents(logicalIndex)
        # Get the calculated width
        width = header.sectionSize(logicalIndex)
        # Switch back to Interactive mode
        header.setSectionResizeMode(logicalIndex, QHeaderView.Interactive)
        # Set the width explicitly for smooth transition
        header.resizeSection(logicalIndex, width)
        self.column_widths[logicalIndex] = width
    
    def showRowContextMenu(self, position):
        """Show context menu when right-clicking on a table row"""
        item = self.itemAt(position)
        if item is None:
            return
        
        row = item.row()
        menu = QMenu(self)
        
        # Delete action
        delete_action = QAction("Delete Repository", self)
        delete_action.setIcon(QIcon.fromTheme("edit-delete"))
        delete_action.triggered.connect(lambda: self.parent().deleteSelectedRepos())
        menu.addAction(delete_action)
        
        # Add separator
        menu.addSeparator()
        
        # Update action
        update_action = QAction("Update Repository", self)
        update_action.triggered.connect(lambda: self.parent().updateSelectedRepos())
        menu.addAction(update_action)
        
        # Show menu at cursor position
        menu.exec_(self.viewport().mapToGlobal(position))
    
    def keyPressEvent(self, event):
        """Handle keyboard shortcuts"""
        if event.key() == Qt.Key_Delete:
            # Delete key pressed - delete selected repos
            if self.parent():
                self.parent().deleteSelectedRepos()
            return
        super().keyPressEvent(event)

class ColumnManagerDialog(QDialog):
    """Dialog for managing table columns (show/hide/reorder)"""
    
    def __init__(self, table, parent=None):
        super().__init__(parent)
        self.table = table
        self.setWindowTitle("Column Manager")
        self.resize(400, 400)
        
        layout = QVBoxLayout()
        
        # Instructions label
        instructions = QLabel("Check columns to show, uncheck to hide. Drag items to reorder.")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        
        # List widget for column management
        self.columnsListWidget = QListWidget()
        self.columnsListWidget.setDragDropMode(QListWidget.InternalMove)
        layout.addWidget(self.columnsListWidget)
        
        # Populate list with current columns and their visibility
        for i in range(table.columnCount()):
            header_text = table.horizontalHeaderItem(i).text()
            item = QListWidgetItem(header_text)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled)
            
            # Set checked state based on column visibility
            if i not in table.hidden_columns:
                item.setCheckState(Qt.Checked)
            else:
                item.setCheckState(Qt.Unchecked)
                
            self.columnsListWidget.addItem(item)
        
        # Buttons
        buttonLayout = QHBoxLayout()
        
        # Reset to default button
        resetButton = QPushButton("Reset to Default")
        resetButton.clicked.connect(self.resetToDefault)
        buttonLayout.addWidget(resetButton)
        
        # Select All / Deselect All
        selectAllButton = QPushButton("Select All")
        selectAllButton.clicked.connect(self.selectAll)
        buttonLayout.addWidget(selectAllButton)
        
        # Apply button
        applyButton = QPushButton("Apply")
        applyButton.clicked.connect(self.applyChanges)
        buttonLayout.addWidget(applyButton)
        
        # Cancel button
        cancelButton = QPushButton("Cancel")
        cancelButton.clicked.connect(self.reject)
        buttonLayout.addWidget(cancelButton)
        
        layout.addLayout(buttonLayout)
        self.setLayout(layout)
        
    def resetToDefault(self):
        """Reset columns to default visibility and order"""
        for i in range(self.columnsListWidget.count()):
            item = self.columnsListWidget.item(i)
            item.setCheckState(Qt.Checked)
    
    def selectAll(self):
        """Toggle between Select All and Deselect All"""
        sender = self.sender()
        
        if sender.text() == "Select All":
            # Check all items
            for i in range(self.columnsListWidget.count()):
                self.columnsListWidget.item(i).setCheckState(Qt.Checked)
            sender.setText("Deselect All")
        else:
            # Uncheck all items
            for i in range(self.columnsListWidget.count()):
                self.columnsListWidget.item(i).setCheckState(Qt.Unchecked)
            sender.setText("Select All")
    
    def applyChanges(self):
        """Apply the column changes to the table"""
        # Get current column header texts for mapping
        header_texts = []
        for i in range(self.table.columnCount()):
            header_texts.append(self.table.horizontalHeaderItem(i).text())
            
        # Apply visibility changes
        for i in range(self.columnsListWidget.count()):
            item = self.columnsListWidget.item(i)
            column_name = item.text()
            
            if column_name in header_texts:
                column_index = header_texts.index(column_name)
                if item.checkState() == Qt.Checked:
                    self.table.showColumn(column_index)
                else:
                    self.table.hideColumn(column_index)
        
        # Reordering not implemented in this version as it requires more complex table manipulation
        # Would need to actually reorder the data as well
        
        self.accept()

class RepoSaverGUI(QWidget):
    """
    Main GUI:
    - Loads all repos from JSON on startup, each displayed in table columns:
       0: Repo URL
       1: Description
       2: Status
       3: Last Cloned
       4: Last Updated
       5: "Open Folder"
       6: "Archives"
       7: "README"
    - Add new repo (single or from bulk .txt).
    - For Bulk Upload, we *always* spawn a thread for *each line*, even if it
      already exists in JSON => ensures 'git pull' + archive if new commits appear.
    - **Key Fix**: Before adding new repos (single or bulk), we reload from JSON
      to preserve any existing repos that might not be in `self.repoData`.
    - Refresh statuses => re-check archived/deleted from GitHub.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("GitHub Repo Saver (Single-file, Bulk Fix, JSON Merging)")
        self.threads = []  # Keep references to background CloneWorker threads
        self.repoData = {}
        
        # Set tooltip style
        QApplication.setStyle('Fusion')  # Use Fusion style for better tooltips
        QToolTip.setFont(QApplication.font())  # Use application font
        QToolTip.setPalette(QApplication.palette())  # Use application palette
        
        # ThreadPool for controlling concurrent operations
        self.max_workers = max(1, os.cpu_count() or 4)  # Default to CPU count or 4
        self.thread_pool = ThreadPoolExecutor(max_workers=self.max_workers)
        self.queue = queue.Queue()  # Queue for tracking pending URLs
        self.active_tasks = 0
        self.queue_lock = threading.Lock()
        self.active_urls = set()  # Track URLs currently being processed
        
        # Auto-update scheduler
        self.last_auto_update = None
        self.auto_update_timer = None
        
        self.initUI()
        self.loadRepos()  # auto-load from JSON
        self.process_queue_thread = threading.Thread(target=self.process_queue, daemon=True)
        self.process_queue_thread.start()
        
        # Start timer for daily check - runs every hour but only updates if 24h passed
        self.setupAutoUpdateTimer()

    def initUI(self):
        mainLayout = QVBoxLayout()

        # Top control buttons layout
        topControlsLayout = QHBoxLayout()
        
        # Column Manager Button
        self.columnManagerBtn = QPushButton("Manage Columns")
        self.columnManagerBtn.setIcon(QIcon.fromTheme("view-list-details"))
        self.columnManagerBtn.setToolTip("Show/hide columns and change their order")
        self.columnManagerBtn.clicked.connect(self.showColumnManager)
        topControlsLayout.addWidget(self.columnManagerBtn)
        
        # Delete Selected Button
        self.deleteBtn = QPushButton("Delete Selected")
        self.deleteBtn.setIcon(QIcon.fromTheme("edit-delete"))
        self.deleteBtn.setToolTip("Delete selected repositories (or press Delete key)")
        self.deleteBtn.clicked.connect(self.deleteSelectedRepos)
        topControlsLayout.addWidget(self.deleteBtn)
        
        # Add stretcher to push the buttons to the right
        topControlsLayout.addStretch(1)
        
        # Add to main layout
        mainLayout.addLayout(topControlsLayout)

        # Table
        self.repoTable = EnhancedTableWidget()
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
        
        # Make the table non-editable by default
        self.repoTable.setEditTriggers(QTableWidget.NoEditTriggers)
        
        # Enable word wrapping for the description column
        self.repoTable.setWordWrap(True)
        
        # Enable real-time visual feedback during column resizing
        self.repoTable.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.repoTable.horizontalHeader().setStretchLastSection(False)
        
        # Enable the horizontal header to respond to mouse move events during resize
        self.repoTable.horizontalHeader().setSectionsMovable(False)
        self.repoTable.horizontalHeader().setSectionsClickable(True)
        
        # Set default widths - use proportional sizing initially
        # This prevents the stretch/jump when switching modes
        self.repoTable.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        
        # Set initial column widths after a short delay to ensure table is rendered
        QTimer.singleShot(50, self.setupColumnWidths)
        
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
        
        self.updateAllBtn = QPushButton("Update All Now")
        self.updateAllBtn.clicked.connect(self.updateAllRepos)
        rowLayout.addWidget(self.updateAllBtn)

        mainLayout.addLayout(rowLayout)

        # Status indicators
        statusLayout = QHBoxLayout()
        
        # Queue status
        queueStatusLabel = QLabel("Queue:")
        statusLayout.addWidget(queueStatusLabel)
        
        self.queueCountLabel = QLabel("0")
        statusLayout.addWidget(self.queueCountLabel)
        
        # Active operations
        activeStatusLabel = QLabel("Active:")
        statusLayout.addWidget(activeStatusLabel)
        
        self.activeCountLabel = QLabel("0")
        statusLayout.addWidget(self.activeCountLabel)
        
        # Last update
        lastUpdateLabel = QLabel("Last Auto-Update:")
        statusLayout.addWidget(lastUpdateLabel)
        
        self.lastUpdateTimeLabel = QLabel("Never")
        statusLayout.addWidget(self.lastUpdateTimeLabel)
        
        # Progress indicator
        self.progressBar = QProgressBar()
        self.progressBar.setRange(0, 100)
        self.progressBar.setValue(0)
        self.progressBar.setTextVisible(True)
        self.progressBar.setFormat("%v/%m repos processed")
        statusLayout.addWidget(self.progressBar)
        
        # Add to main layout
        mainLayout.addLayout(statusLayout)

        # Logging
        self.logText = QTextEdit()
        self.logText.setReadOnly(True)
        mainLayout.addWidget(self.logText)

        self.setLayout(mainLayout)
        self.resize(1200, 600)
        
        # Start status update timer (every 0.5 seconds)
        self.statusUpdateTimer = QTimer(self)
        self.statusUpdateTimer.setInterval(500)
        self.statusUpdateTimer.timeout.connect(self.updateStatusIndicators)
        self.statusUpdateTimer.start()

    def loadRepos(self):
        """Load from JSON and populate the table."""
        self.repoData = load_cloned_info()
        self.populateTable()

    def populateTable(self):
        self.repoTable.setRowCount(0)
        for repo_url, info in self.repoData.items():
            self.addTableRow(repo_url, info)

    def _adjustRowHeight(self, row_idx, description_text):
        """
        Adjust row height based on description text content.
        Calculates how many lines the description needs and sets row height accordingly.
        """
        if not description_text:
            # Default height for empty descriptions
            self.repoTable.setRowHeight(row_idx, self.repoTable.verticalHeader().defaultSectionSize())
            return
        
        # Get the description column width
        desc_col_width = self.repoTable.columnWidth(1)
        if desc_col_width <= 0:
            # If column width not available yet, use a default
            desc_col_width = 200
        
        # Account for padding/margins (subtract ~20px for cell padding)
        available_width = max(100, desc_col_width - 20)
        
        # Get font metrics to calculate text height
        font = self.repoTable.font()
        font_metrics = QFontMetrics(font)
        
        # Calculate how many lines the text will wrap to
        text_rect = font_metrics.boundingRect(
            0, 0, available_width, 0,
            Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop,
            description_text
        )
        
        # Calculate number of lines needed
        line_height = font_metrics.lineSpacing()
        num_lines = max(1, (text_rect.height() // line_height) + 1)
        
        # Set row height: base height + padding for each line
        # Add extra padding for readability
        row_height = max(
            self.repoTable.verticalHeader().defaultSectionSize(),
            (num_lines * line_height) + 10  # 10px padding
        )
        
        self.repoTable.setRowHeight(row_idx, row_height)
    
    def addTableRow(self, repo_url, info):
        """
        Insert a row in the QTableWidget for the given repo.
        """
        row_idx = self.repoTable.rowCount()
        self.repoTable.insertRow(row_idx)

        # 0. Repo URL - Make read-only
        url_item = QTableWidgetItem(repo_url)
        url_item.setToolTip(repo_url)  # Add tooltip for full URL on hover
        url_item.setFlags(url_item.flags() & ~Qt.ItemIsEditable)  # Make non-editable
        self.repoTable.setItem(row_idx, 0, url_item)

        # 1. Description - Make read-only with word wrapping
        desc = info.get("online_description", "")
        desc_item = QTableWidgetItem(desc)
        desc_item.setToolTip(desc)  # Add tooltip for full description on hover
        desc_item.setFlags(desc_item.flags() & ~Qt.ItemIsEditable)  # Make non-editable
        # Enable word wrapping for description - align text to top-left
        desc_item.setTextAlignment(Qt.AlignTop | Qt.AlignLeft)
        # Enable word wrap by setting the item to wrap text
        self.repoTable.setItem(row_idx, 1, desc_item)
        
        # Calculate row height based on description content
        # Use a small delay to ensure column widths are set
        QTimer.singleShot(50, lambda: self._adjustRowHeight(row_idx, desc))

        # 2. Status
        status = info.get("status", "")
        status_item = QTableWidgetItem(status)
        status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)  # Make non-editable
        
        # Color-code the status
        if status == "active":
            status_item.setBackground(QColor(50, 180, 50))  # Darker green
        elif status == "archived":
            status_item.setBackground(QColor(255, 255, 200))  # Light yellow
        elif status == "deleted":
            status_item.setBackground(QColor(255, 200, 200))  # Light red
        elif status == "error":
            status_item.setBackground(QColor(255, 180, 180))  # Darker red
        elif status == "pending":
            status_item.setBackground(QColor(200, 200, 255))  # Light blue
            
        self.repoTable.setItem(row_idx, 2, status_item)

        # 3. Last Cloned
        last_cloned = info.get("last_cloned", "")
        cloned_item = QTableWidgetItem(last_cloned)
        cloned_item.setFlags(cloned_item.flags() & ~Qt.ItemIsEditable)  # Make non-editable
        self.repoTable.setItem(row_idx, 3, cloned_item)

        # 4. Last Updated
        last_updated = info.get("last_updated", "")
        updated_item = QTableWidgetItem(last_updated)
        updated_item.setFlags(updated_item.flags() & ~Qt.ItemIsEditable)  # Make non-editable
        self.repoTable.setItem(row_idx, 4, updated_item)

        # 5. "Open Folder" button
        btn_folder = QPushButton("Folder")
        btn_folder.clicked.connect(lambda _, u=repo_url: self.openRepoFolder(u))
        # Enable smooth resizing for buttons
        btn_folder.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.repoTable.setCellWidget(row_idx, 5, btn_folder)

        # 6. "Archives" button
        btn_arch = QPushButton("Archives")
        btn_arch.clicked.connect(lambda _, u=repo_url: self.showArchives(u))
        btn_arch.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.repoTable.setCellWidget(row_idx, 6, btn_arch)

        # 7. "README" button
        btn_readme = QPushButton("README")
        btn_readme.clicked.connect(lambda _, u=repo_url: self.viewReadme(u))
        btn_readme.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.repoTable.setCellWidget(row_idx, 7, btn_readme)

    def addRepo(self):
        """Add a single repo from the text field, preserving old data in JSON."""
        url = self.addRepoEdit.text().strip()
        if not url:
            QMessageBox.warning(self, "No URL", "Please enter a GitHub repo URL.")
            return
        if not validate_repo_url(url):
            QMessageBox.warning(self, "Invalid URL", "Must start with https://github.com/")
            return
        if not url.endswith(".git"):
            url += ".git"

        # **Reload** the JSON so we don't lose existing data
        all_data = load_cloned_info()

        # If brand-new, add an entry using backend function
        if url not in all_data:
            if add_repo_to_database(url):
                # Reload to get the updated data
                all_data = load_cloned_info()
                # Also update self.repoData in memory
                self.repoData = all_data
                # Add a table row for the new entry
                self.addTableRow(url, all_data[url])

        self.addRepoEdit.clear()

        # Spawn a thread for clone/pull
        self.spawnCloneThread(url)

    def process_queue(self):
        """Background thread to process the URL queue."""
        while True:
            try:
                # Get a URL from the queue
                url = self.queue.get(block=True, timeout=1)
                
                with self.queue_lock:
                    if url in self.active_urls:
                        self.queue.task_done()
                        self.appendLog(f"Skipping duplicate in queue: {url}")
                        continue
                    
                    # Mark URL as being processed and update status
                    self.active_urls.add(url)
                    
                    # Update status in UI to show it's being processed
                    data = load_cloned_info()
                    if url in data:
                        data[url]["status"] = "pending" 
                        save_cloned_info(data)
                        self.updateRowForRepo(url, data[url])
                
                # Process the URL
                self.appendLog(f"Starting to process from queue: {url}")
                self.spawnCloneThread(url)
                
                # Mark task as complete in queue
                self.queue.task_done()
            except queue.Empty:
                # No URLs in queue, just continue
                continue
            except Exception as e:
                logging.error(f"Error in queue processing: {e}")
                self.appendLog(f"Queue processing error: {str(e)}")
                # Don't want to lose the URL if there's an exception
                with self.queue_lock:
                    if 'url' in locals() and url in self.active_urls:
                        self.active_urls.remove(url)
                        self.appendLog(f"Removed from active URLs due to error: {url}")
                        
                # Mark task as complete in queue if URL was retrieved
                if 'url' in locals():
                    self.queue.task_done()

    def spawnCloneThread(self, repo_url):
        """Create a CloneWorker for the given repo_url, ensuring a pull + archive."""
        worker = CloneWorker(repo_url)
        self.threads.append(worker)  # keep a reference
        worker.logSignal.connect(self.appendLog)
        worker.statusUpdateSignal.connect(self.updateRepoStatus)
        worker.errorSignal.connect(self.handleRepoError)
        worker.finishedSignal.connect(lambda url: self.cloneFinished(url))
        worker.start()
        
    def handleRepoError(self, repo_url, error_msg):
        """Handle errors reported during repository processing."""
        self.appendLog(f"ERROR for {repo_url}: {error_msg}")
        
        # Update UI to show error state
        data = load_cloned_info()
        if repo_url in data and data[repo_url].get("status") != "error":
            data[repo_url]["status"] = "error"
            data[repo_url]["online_description"] = f"Error: {error_msg[:100]}"
            save_cloned_info(data)
            self.updateRowForRepo(repo_url, data[repo_url])
            
        # Don't show error messages for every repository in bulk operations
        # This would lead to too many popups
        # Error is already visible in the UI table with red background and in the log

    def updateRepoStatus(self, repo_url, info):
        """
        Update the table with real-time data from a running clone operation.
        This is called by statusUpdateSignal emitted from CloneWorker.
        """
        # Save to our in-memory cache
        self.repoData[repo_url] = info
        
        # Update the UI row
        self.updateRowForRepo(repo_url, info)
        
        # Log the update
        status = info.get("status", "unknown")
        self.appendLog(f"Status update for {repo_url}: {status}, description: {info.get('online_description', '')}")

    def cloneFinished(self, repo_url):
        """
        Called when a worker finishes. Refresh that row from JSON.
        """
        self.appendLog(f"Clone/Update finished: {repo_url}")
        
        # Reload the latest data from the JSON file
        latest_data = load_cloned_info()
        if repo_url in latest_data:
            # Update our in-memory data and UI
            self.repoData[repo_url] = latest_data[repo_url]
            self.updateRowForRepo(repo_url, latest_data[repo_url])
        
        # Remove from active URLs set
        with self.queue_lock:
            if repo_url in self.active_urls:
                self.active_urls.remove(repo_url)

    def updateRowForRepo(self, repo_url, info=None):
        """
        Refresh the table row for the given repo_url from self.repoData or passed info.
        If info is None, retrieve from self.repoData.
        """
        if info is None:
            info = self.repoData.get(repo_url, {})
        else:
            # Update our in-memory data
            self.repoData[repo_url] = info
            
        row_count = self.repoTable.rowCount()
        row_found = False
        
        for r in range(row_count):
            cell = self.repoTable.item(r, 0)
            if cell and cell.text() == repo_url:
                # Update URL tooltip (in case it changed)
                cell.setToolTip(repo_url)
                
                # Update description
                desc = info.get("online_description", "")
                desc_item = QTableWidgetItem(desc)
                desc_item.setToolTip(desc)  # Add tooltip for full description on hover
                desc_item.setFlags(desc_item.flags() & ~Qt.ItemIsEditable)  # Make non-editable
                desc_item.setTextAlignment(Qt.AlignTop | Qt.AlignLeft)
                self.repoTable.setItem(r, 1, desc_item)
                
                # Adjust row height based on description
                self._adjustRowHeight(r, desc)
                
                # Update status with color coding
                status = info.get("status", "")
                status_item = QTableWidgetItem(status)
                status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)  # Make non-editable
                
                # Color-code the status
                if status == "active":
                    status_item.setBackground(QColor(50, 180, 50))  # Darker green
                elif status == "archived":
                    status_item.setBackground(QColor(255, 255, 200))  # Light yellow
                elif status == "deleted":
                    status_item.setBackground(QColor(255, 200, 200))  # Light red
                elif status == "error":
                    status_item.setBackground(QColor(255, 180, 180))  # Darker red
                elif status == "pending":
                    status_item.setBackground(QColor(200, 200, 255))  # Light blue
                
                self.repoTable.setItem(r, 2, status_item)
                
                # Update dates
                last_cloned = QTableWidgetItem(info.get("last_cloned", ""))
                last_cloned.setFlags(last_cloned.flags() & ~Qt.ItemIsEditable)  # Make non-editable
                self.repoTable.setItem(r, 3, last_cloned)
                
                last_updated = QTableWidgetItem(info.get("last_updated", ""))
                last_updated.setFlags(last_updated.flags() & ~Qt.ItemIsEditable)  # Make non-editable
                self.repoTable.setItem(r, 4, last_updated)
                
                row_found = True
                break
                
        # Force the UI to update
        self.repoTable.viewport().update()
        
        return row_found

    def refreshStatuses(self):
        """Re-check archived/deleted status for all repos in JSON, update table."""
        self.captureLogs()
        detect_deleted_or_archived()
        
        # Reload data from JSON and update UI
        self.repoData = load_cloned_info()
        
        # Update each row with color coding
        self.repoTable.setRowCount(0)
        self.populateTable()
        
        self.appendLog("Refreshed repo statuses.\n")

    def openRepoFolder(self, repo_url):
        """Open the repository folder in the system file manager."""
        try:
            info = self.repoData.get(repo_url, {})
            if not info:
                QMessageBox.warning(self, "Repository Not Found", f"Repository not found in database:\n{repo_url}")
                return
            
            path = info.get("local_path", "")
            if not path:
                QMessageBox.information(self, "Folder Not Found", f"No local path configured for:\n{repo_url}")
                return
            
            if os.path.isdir(path):
                self.openInFinder(path)
            else:
                QMessageBox.information(
                    self, 
                    "Folder Not Found", 
                    f"The local folder does not exist:\n{path}\n\n"
                    f"Repository: {repo_url}\n\n"
                    f"Try updating the repository first."
                )
        except Exception as e:
            logging.error(f"Error opening repo folder: {e}")
            QMessageBox.critical(
                self, 
                "Error", 
                f"An error occurred while opening the folder:\n{str(e)}"
            )

    def showArchives(self, repo_url):
        info = self.repoData.get(repo_url, {})
        path = info.get("local_path", "")
        if not path or not os.path.isdir(path):
            QMessageBox.information(self, "Repo Not Found", "Clone/update the repo first.")
            return
        dlg = ArchivedVersionsDialog(path, self)
        dlg.exec_()

    def viewReadme(self, repo_url):
        """View README.md file with markdown parsing and rendering."""
        info = self.repoData.get(repo_url, {})
        path = info.get("local_path", "")
        if not path or not os.path.isdir(path):
            QMessageBox.information(self, "Repo Not Found", "Clone/update the repo first.")
            return
        
        # Try to find README file (case-insensitive, various extensions)
        readme_files = [
            "README.md", "readme.md", "Readme.md", "README.MD",
            "README.txt", "readme.txt", "README", "readme"
        ]
        readme_path = None
        for filename in readme_files:
            test_path = os.path.join(path, filename)
            if os.path.isfile(test_path):
                readme_path = test_path
                break
        
        if not readme_path:
            QMessageBox.information(self, "No README", "No README file found in this repository.")
            return

        try:
            with open(readme_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to read README file:\n{str(e)}")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"README - {os.path.basename(path)}")
        lyt = QVBoxLayout()
        txt = QTextEdit()
        txt.setReadOnly(True)
        # Set light mode background
        txt.setStyleSheet("background-color: #ffffff; color: #24292e;")
        
        # Parse markdown if available and file is .md
        if MARKDOWN_AVAILABLE and readme_path.lower().endswith('.md'):
            try:
                # Convert markdown to HTML
                html_content = markdown.markdown(
                    content,
                    extensions=['extra', 'codehilite', 'tables', 'fenced_code']
                )
                
                # Add CSS styling for better appearance (light mode)
                styled_html = f"""
                <html>
                <head>
                    <style>
                        body {{
                            font-family: Helvetica, Arial, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                            line-height: 1.6;
                            color: #24292e;
                            background-color: #ffffff;
                            padding: 20px;
                            max-width: 900px;
                            margin: 0 auto;
                        }}
                        h1, h2, h3, h4, h5, h6 {{
                            color: #24292e;
                            margin-top: 24px;
                            margin-bottom: 16px;
                        }}
                        h1 {{ border-bottom: 2px solid #eaecef; padding-bottom: 8px; }}
                        h2 {{ border-bottom: 1px solid #eaecef; padding-bottom: 8px; }}
                        code {{
                            background-color: #f6f8fa;
                            color: #24292e;
                            border-radius: 3px;
                            padding: 2px 6px;
                            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', 'Consolas', 'Courier New', monospace;
                            font-size: 85%;
                        }}
                        pre {{
                            background-color: #f6f8fa;
                            color: #24292e;
                            border-radius: 6px;
                            padding: 16px;
                            overflow-x: auto;
                            line-height: 1.45;
                        }}
                        pre code {{
                            background-color: transparent;
                            padding: 0;
                        }}
                        blockquote {{
                            border-left: 4px solid #dfe2e5;
                            padding-left: 16px;
                            color: #6a737d;
                            background-color: #f9f9f9;
                            margin-left: 0;
                        }}
                        table {{
                            border-collapse: collapse;
                            width: 100%;
                            margin: 16px 0;
                            background-color: #ffffff;
                        }}
                        th, td {{
                            border: 1px solid #dfe2e5;
                            padding: 8px 12px;
                            background-color: #ffffff;
                        }}
                        th {{
                            background-color: #f6f8fa;
                            font-weight: 600;
                            color: #24292e;
                        }}
                        td {{
                            color: #24292e;
                        }}
                        a {{
                            color: #0366d6;
                            text-decoration: none;
                        }}
                        a:hover {{
                            text-decoration: underline;
                        }}
                        img {{
                            max-width: 100%;
                            height: auto;
                        }}
                        ul, ol {{
                            padding-left: 30px;
                        }}
                        li {{
                            margin: 4px 0;
                        }}
                    </style>
                </head>
                <body>
                    {html_content}
                </body>
                </html>
                """
                txt.setHtml(styled_html)
            except Exception as e:
                logging.error(f"Error parsing markdown: {e}")
                # Fallback to plain text if markdown parsing fails
                txt.setPlainText(content)
        else:
            # Plain text display if markdown library not available or not a .md file
            if not MARKDOWN_AVAILABLE:
                # Add a note that markdown parsing is not available
                content_with_note = content + "\n\n---\nNote: Install 'markdown' package for formatted markdown rendering."
            txt.setPlainText(content)
        
        lyt.addWidget(txt)
        dlg.setLayout(lyt)
        dlg.resize(800, 600)
        dlg.exec_()

    def openInFinder(self, path):
        """Cross-platform folder open with error handling."""
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "Path Not Found", f"The path does not exist:\n{path}")
            return
        
        try:
            if sys.platform.startswith("darwin"):
                subprocess.run(["open", path], check=True, timeout=5)
            elif os.name == "nt":
                os.startfile(path)
            else:
                subprocess.run(["xdg-open", path], check=True, timeout=5)
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to open folder: {e}")
            QMessageBox.critical(self, "Error", f"Failed to open folder:\n{path}\n\nError: {str(e)}")
        except subprocess.TimeoutExpired:
            logging.error(f"Timeout opening folder: {path}")
            QMessageBox.warning(self, "Timeout", f"Timeout while trying to open folder:\n{path}")
        except Exception as e:
            logging.error(f"Unexpected error opening folder: {e}")
            QMessageBox.critical(self, "Error", f"Unexpected error opening folder:\n{path}\n\nError: {str(e)}")

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

    def setupAutoUpdateTimer(self):
        """Set up a timer to check for updates every hour."""
        self.auto_update_timer = QTimer(self)
        # Check every hour - 3600000 ms
        self.auto_update_timer.setInterval(3600000)
        self.auto_update_timer.timeout.connect(self.checkDailyUpdate)
        self.auto_update_timer.start()
        
        # Also do an immediate check
        QTimer.singleShot(5000, self.checkDailyUpdate)
        
        # Get last update time from config
        self.last_auto_update = get_last_auto_update_time()
        
    def checkDailyUpdate(self):
        """Check if it's been 24h since the last update, and if so, update all repos."""
        should_run, last_update = should_run_auto_update()
        
        if not should_run:
            return
        
        now = datetime.datetime.now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")
        
        self.appendLog(f"Starting scheduled daily update at {now_str}")
        
        # Update all repos
        for repo_url in self.repoData.keys():
            # Only queue if not already being processed
            with self.queue_lock:
                if repo_url not in self.active_urls:
                    self.queue.put(repo_url)
        
        # Save the new time
        save_last_auto_update_time(now_str)
        self.last_auto_update = now_str
        
        # Also run status check
        self.refreshStatuses()

    def updateAllRepos(self):
        """Manually trigger an update of all repositories."""
        if not self.repoData:
            QMessageBox.information(self, "No Repositories", "No repositories to update.")
            return
            
        self.appendLog("Starting manual update of all repositories")
        count = 0
        
        for repo_url in self.repoData.keys():
            # Only queue if not already being processed
            with self.queue_lock:
                if repo_url not in self.active_urls:
                    self.queue.put(repo_url)
                    count += 1
        
        # Track start time for completion summary            
        self.bulk_operation_start_time = datetime.datetime.now()
        self.repos_queued_count = count
        
        # Set up a timer to check if all operations are complete
        self.bulk_completion_timer = QTimer(self)
        self.bulk_completion_timer.setInterval(2000)  # Check every 2 seconds
        self.bulk_completion_timer.timeout.connect(self.checkBulkOperationCompletion)
        self.bulk_completion_timer.start()
        
        QMessageBox.information(self, "Update Started", 
                               f"Update started for {count} repositories. Check the log for progress.")
    
    def checkBulkOperationCompletion(self):
        """Check if bulk operation is complete and show summary if it is."""
        # If no queue and no active operations, we're done
        if self.queue.empty() and len(self.active_urls) == 0:
            # Stop the timer
            self.bulk_completion_timer.stop()
            
            # Calculate elapsed time
            elapsed_time = datetime.datetime.now() - self.bulk_operation_start_time
            
            # Check error counts
            error_count = 0
            for repo_url, info in self.repoData.items():
                if info.get("status") == "error":
                    error_count += 1
            
            # Show summary
            success_count = self.repos_queued_count - error_count
            self.appendLog(
                f"\nBulk operation completed in {elapsed_time.total_seconds():.1f} seconds\n"
                f"Processed: {self.repos_queued_count} repositories\n"
                f"Successful: {success_count}\n"
                f"Errors: {error_count}\n"
            )
            
            # Only show a dialog if there were errors
            if error_count > 0:
                QMessageBox.warning(
                    self,
                    "Bulk Operation Complete with Errors",
                    f"Bulk operation completed in {elapsed_time.total_seconds():.1f} seconds.\n\n"
                    f"Successfully processed: {success_count} repositories\n"
                    f"Errors: {error_count} repositories\n\n"
                    "Please check the error status in the table for details."
                )

    def updateStatusIndicators(self):
        """Update status indicators with current counts."""
        # Queue count
        queue_size = self.queue.qsize()
        self.queueCountLabel.setText(str(queue_size))
        
        # Active count
        with self.queue_lock:
            active_count = len(self.active_urls)
        self.activeCountLabel.setText(str(active_count))
        
        # Last update time
        if self.last_auto_update:
            self.lastUpdateTimeLabel.setText(self.last_auto_update)
        else:
            self.lastUpdateTimeLabel.setText("Never")
            
        # Progress bar
        total = queue_size + active_count
        if total > 0:
            self.progressBar.setRange(0, total)
            self.progressBar.setValue(active_count)
        else:
            self.progressBar.setRange(0, 1)
            self.progressBar.setValue(0)

    def closeEvent(self, event):
        """
        Attempt to gracefully stop any running threads before closing,
        to avoid the "QThread: Destroyed while thread is still running" error.
        """
        # Stop all timers
        if self.auto_update_timer:
            self.auto_update_timer.stop()
            
        if hasattr(self, 'statusUpdateTimer') and self.statusUpdateTimer:
            self.statusUpdateTimer.stop()
            
        if hasattr(self, 'bulk_completion_timer') and self.bulk_completion_timer:
            self.bulk_completion_timer.stop()
            
        # Shutdown the thread pool
        self.thread_pool.shutdown(wait=False)
        
        still_running = [t for t in self.threads if t.isRunning()]
        if still_running:
            for t in still_running:
                t.quit()
                t.wait()
        super().closeEvent(event)

    def bulkUpload(self):
        """
        Prompt for a .txt file, read each line as a GitHub URL.
        Reload the existing JSON first to preserve old data.
        Then for each line, if it's brand new, add it.
        Then queue each URL for sequential processing.
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

            try:
                # Read all lines from the file
                with open(txt_file, "r", encoding="utf-8") as f:
                    lines = [ln.strip() for ln in f if ln.strip()]
                
                if not lines:
                    QMessageBox.warning(self, "Empty File", "No URLs found in the selected file.")
                    return
                    
                # Confirm the operation with user
                confirm = QMessageBox.question(
                    self, 
                    "Confirm Bulk Upload", 
                    f"Found {len(lines)} URLs in the file. Proceed with processing?",
                    QMessageBox.Yes | QMessageBox.No
                )
                
                if confirm != QMessageBox.Yes:
                    return
                
                # Reload existing JSON so we don't overwrite older entries
                all_data = load_cloned_info()

                # Pre-process URLs for validation and unique counting
                valid_urls = []
                invalid_urls = []
                added_count = 0
                
                for line in lines:
                    url = line.strip()
                    if not url:
                        continue
                        
                    if not validate_repo_url(url):
                        invalid_urls.append(url)
                        continue
                        
                    if not url.endswith(".git"):
                        url += ".git"
                    
                    valid_urls.append(url)
                    
                    # If brand new, add an entry
                    if url not in all_data:
                        all_data[url] = {
                            "last_cloned": "",
                            "last_updated": "",
                            "local_path": os.path.join(DATA_FOLDER, url.split("/")[-1]),
                            "online_description": "",
                            "status": "pending"
                        }
                        added_count += 1

                # Save the merged data
                save_cloned_info(all_data)
                # Also update our in-memory store and table
                self.repoData = all_data
                self.populateTable()  # re-draw table with all updates

                # Queue URLs for processing
                queued_count = 0
                for url in valid_urls:
                    # Each valid URL gets queued for sequential processing
                    self.queue.put(url)
                    queued_count += 1

                # Log the results
                status_msg = (
                    f"Bulk upload processed {len(lines)} lines.\n"
                    f"- Added {added_count} new repos to database\n"
                    f"- Queued {queued_count} valid repos for processing\n"
                )
                
                if invalid_urls:
                    status_msg += f"- Found {len(invalid_urls)} invalid URLs that were skipped\n"
                    for i, invalid in enumerate(invalid_urls[:5], 1):
                        status_msg += f"  {i}. {invalid}\n"
                    if len(invalid_urls) > 5:
                        status_msg += f"  ... and {len(invalid_urls) - 5} more\n"
                
                self.appendLog(status_msg)
                
                # Track start time for completion summary            
                self.bulk_operation_start_time = datetime.datetime.now()
                self.repos_queued_count = queued_count
                
                # Set up a timer to check if all operations are complete
                self.bulk_completion_timer = QTimer(self)
                self.bulk_completion_timer.setInterval(2000)  # Check every 2 seconds
                self.bulk_completion_timer.timeout.connect(self.checkBulkOperationCompletion)
                self.bulk_completion_timer.start()
                
                # Show a summary dialog
                QMessageBox.information(
                    self, 
                    "Bulk Upload Started", 
                    f"Started processing {queued_count} repositories.\n\n"
                    f"Added {added_count} new repositories to the database.\n"
                    f"Invalid URLs skipped: {len(invalid_urls)}\n\n"
                    "Check the log for progress updates."
                )
                
            except Exception as e:
                logging.error(f"Error during bulk upload: {e}")
                QMessageBox.critical(
                    self, 
                    "Bulk Upload Error", 
                    f"An error occurred during the bulk upload process:\n{str(e)}"
                )

    def showColumnManager(self):
        """Show the column manager dialog"""
        dialog = ColumnManagerDialog(self.repoTable, self)
        dialog.exec_()

    def setupColumnWidths(self):
        """Set up column widths after initial layout with smooth sizing"""
        self._adjustColumnWidthsToFill()
    
    def _adjustColumnWidthsToFill(self):
        """Adjust column widths to fill the full table width proportionally"""
        header = self.repoTable.horizontalHeader()
        
        # Ensure we're in interactive mode
        header.setSectionResizeMode(QHeaderView.Interactive)
        
        # Get available width
        total_width = self.repoTable.viewport().width()
        column_count = self.repoTable.columnCount()
        
        if total_width > 0 and column_count > 0:
            # Calculate proportional widths
            # First 2 columns (URL, Description) get more space
            url_width = max(150, int(total_width * 0.25))  # Minimum 150px, 25% of width
            desc_width = max(150, int(total_width * 0.25))  # Minimum 150px, 25% of width
            
            # Remaining width distributed among other columns
            remaining_width = total_width - url_width - desc_width
            other_column_width = max(80, int(remaining_width / max(1, column_count - 2)))
            
            # Set widths smoothly
            header.resizeSection(0, url_width)  # URL
            header.resizeSection(1, desc_width)  # Description
            
            # Set remaining column widths
            for i in range(2, column_count):
                header.resizeSection(i, other_column_width)
            
            # Store widths for future reference
            if hasattr(self.repoTable, 'column_widths'):
                self.repoTable.column_widths[0] = url_width
                self.repoTable.column_widths[1] = desc_width
                for i in range(2, column_count):
                    self.repoTable.column_widths[i] = other_column_width
    
    def resizeEvent(self, event):
        """Handle window resize - adjust columns to fill full width"""
        super().resizeEvent(event)
        
        # Adjust column widths to fill the table when window is resized
        # Use a small delay to ensure the table has updated its size
        QTimer.singleShot(10, self._adjustColumnWidthsToFill)
        # Also recalculate row heights after columns are adjusted
        QTimer.singleShot(50, self._recalculateAllRowHeights)
    
    def _recalculateAllRowHeights(self):
        """Recalculate heights for all rows based on current description column width"""
        for row in range(self.repoTable.rowCount()):
            desc_item = self.repoTable.item(row, 1)
            if desc_item:
                desc_text = desc_item.text()
                self._adjustRowHeight(row, desc_text)
    
    def getSelectedRepoUrls(self):
        """Get list of repository URLs for currently selected rows"""
        selected_rows = set()
        for item in self.repoTable.selectedItems():
            selected_rows.add(item.row())
        
        repo_urls = []
        for row in selected_rows:
            url_item = self.repoTable.item(row, 0)
            if url_item:
                repo_urls.append(url_item.text())
        
        return repo_urls
    
    def deleteSelectedRepos(self):
        """Delete selected repositories from the database and table"""
        selected_urls = self.getSelectedRepoUrls()
        
        if not selected_urls:
            QMessageBox.information(self, "No Selection", "Please select one or more repositories to delete.")
            return
        
        # Confirm deletion
        if len(selected_urls) == 1:
            confirm_msg = f"Are you sure you want to delete this repository?\n\n{selected_urls[0]}"
        else:
            confirm_msg = f"Are you sure you want to delete {len(selected_urls)} repositories?"
        
        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            confirm_msg + "\n\nNote: This will remove the repository from the list, but local files and archives will remain.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # Delete from database
        results = delete_multiple_repos_from_database(selected_urls)
        
        # Count successes and failures
        deleted_count = sum(1 for success in results.values() if success)
        failed_count = len(results) - deleted_count
        
        # Remove from in-memory data
        for repo_url in selected_urls:
            if repo_url in self.repoData:
                del self.repoData[repo_url]
        
        # Reload table to reflect changes
        self.populateTable()
        
        # Show result message
        if deleted_count > 0:
            self.appendLog(f"Deleted {deleted_count} repository/repositories from the list.")
            if failed_count > 0:
                QMessageBox.warning(
                    self,
                    "Partial Success",
                    f"Deleted {deleted_count} repository/repositories.\n{failed_count} could not be deleted."
                )
        else:
            QMessageBox.warning(self, "Deletion Failed", "No repositories were deleted.")
    
    def updateSelectedRepos(self):
        """Update selected repositories"""
        selected_urls = self.getSelectedRepoUrls()
        
        if not selected_urls:
            QMessageBox.information(self, "No Selection", "Please select one or more repositories to update.")
            return
        
        # Queue selected repos for update
        count = 0
        for repo_url in selected_urls:
            with self.queue_lock:
                if repo_url not in self.active_urls:
                    self.queue.put(repo_url)
                    count += 1
        
        if count > 0:
            self.appendLog(f"Queued {count} repository/repositories for update.")
        else:
            QMessageBox.information(self, "No Updates", "Selected repositories are already being processed.")


###############################################################################
#                               MAIN ENTRY
###############################################################################

def main():
    setup_logging()
    
    # Suppress Qt console warnings by redirecting stderr before creating QApplication
    # This won't affect logging, just the Qt warnings
    if not os.environ.get('DEBUG_QT'):
        import sys
        original_stderr = sys.stderr
        class QtWarningFilter:
            def write(self, text):
                # Filter out common Qt warnings that don't affect functionality
                if text:
                    # Skip Qt meta type registration warnings
                    skip_patterns = [
                        "QVector<int>",
                        "QTextCursor",
                        "qRegisterMetaType",
                        "QObject::connect",
                        "Cannot queue arguments",
                        "Make sure",
                        "IMKClient subclass",
                        "IMKInputSession subclass",
                        "chose IMK"
                    ]
                    if not any(pattern in text for pattern in skip_patterns):
                        original_stderr.write(text)
            def flush(self):
                original_stderr.flush()
        sys.stderr = QtWarningFilter()
        
    app = QApplication(sys.argv)
    
    # Fix font warning by using a font that actually exists on macOS
    # Don't use -apple-system, use the system default or a specific font
    font = app.font()
    if sys.platform.startswith("darwin"):
        # Use Helvetica Neue which exists on macOS and won't cause warnings
        # If it doesn't exist, Qt will fall back to the default font
        try:
            test_font = font
            test_font.setFamily("Helvetica Neue")
            # Verify the font exists by checking if it's available
            if test_font.exactMatch():
                font = test_font
        except:
            pass  # Use default font if Helvetica Neue isn't available
    app.setFont(font)
    
    gui = RepoSaverGUI()
    gui.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
