"""
Custom PyQt5 widgets for Git-Archiver.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QTableWidget, QHeaderView, QMenu, QAction, QApplication, QToolTip
)
from PyQt5.QtGui import QCursor


class EnhancedTableWidget(QTableWidget):
    """
    Extended table widget with improved tooltips and column management.

    Features:
    - Custom tooltips that wrap long text
    - Column visibility management (hide/show)
    - Interactive column resizing
    - Double-click to auto-size columns
    - Right-click header menu for column options
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.viewport().installEventFilter(self)

        # Keep track of which columns are hidden
        self.hidden_columns = set()

        # Limit tooltip width
        self.max_tooltip_width = 400

        # Set up interactive column resizing
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.horizontalHeader().setStretchLastSection(False)

        # Make UI updates more responsive
        self.setUpdatesEnabled(True)

        # Make sure columns resize properly
        self.horizontalHeader().setMinimumSectionSize(10)
        self.horizontalHeader().viewport().setMouseTracking(True)

        # Add right-click menu to column headers
        self.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.horizontalHeader().customContextMenuRequested.connect(self.showHeaderContextMenu)

        # Connect signals for column resizing
        self.horizontalHeader().sectionResized.connect(self.onSectionResized)

        # Connect double-click for auto-sizing columns
        self.horizontalHeader().sectionDoubleClicked.connect(self.autoFitColumn)

    def onSectionResized(self, logicalIndex, oldSize, newSize):
        """Update the UI immediately when a column is resized"""
        QApplication.processEvents()

    def resizeEvent(self, event):
        """Handle window resizing to adjust columns properly"""
        super().resizeEvent(event)
        if self.model() and self.model().columnCount() > 0:
            QApplication.processEvents()

    def resizeColumnsToContents(self):
        """Improve performance when auto-sizing columns"""
        super().resizeColumnsToContents()
        self.viewport().update()

    def eventFilter(self, obj, event):
        """Show rich tooltips for certain columns"""
        if obj is self.viewport():
            if event.type() == event.MouseMove:
                pos = event.pos()
                index = self.indexAt(pos)

                if index.isValid() and index.column() in [0, 1]:  # URL or Description
                    item = self.item(index.row(), index.column())
                    if item and item.text():
                        text = item.text()

                        # Format descriptions with word wrapping
                        if index.column() == 1 and len(text) > 60:
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

                            QToolTip.showText(QCursor.pos(), wrapped_text, self)
                        else:
                            QToolTip.showText(QCursor.pos(), text, self)
                    else:
                        QToolTip.hideText()
                else:
                    QToolTip.hideText()

        return super().eventFilter(obj, event)

    def showHeaderContextMenu(self, pos):
        """Display the right-click menu for column headers"""
        column = self.horizontalHeader().logicalIndexAt(pos)
        if column < 0:
            return

        menu = QMenu(self)
        header_text = self.horizontalHeaderItem(column).text()

        # Add option to hide this column
        hide_action = QAction(f"Hide '{header_text}' Column", self)
        hide_action.triggered.connect(lambda: self.hideColumn(column))
        menu.addAction(hide_action)

        menu.addSeparator()

        # Add option to show all columns
        show_all_action = QAction("Show All Columns", self)
        show_all_action.triggered.connect(self.showAllColumns)
        menu.addAction(show_all_action)

        # Add option to reset column widths
        reset_widths_action = QAction("Reset Column Widths", self)
        reset_widths_action.triggered.connect(self.resetColumnWidths)
        menu.addAction(reset_widths_action)

        menu.exec_(self.horizontalHeader().mapToGlobal(pos))

    def hideColumn(self, column):
        """Hide a column and remember it was hidden"""
        super().hideColumn(column)
        self.hidden_columns.add(column)

    def showColumn(self, column):
        """Show a previously hidden column"""
        super().showColumn(column)
        if column in self.hidden_columns:
            self.hidden_columns.remove(column)

    def showAllColumns(self):
        """Make all hidden columns visible again"""
        for column in list(self.hidden_columns):
            self.showColumn(column)

    def resetColumnWidths(self):
        """Reset all column widths to default sizes"""
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        QApplication.processEvents()
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)

    def getColumnVisibilityState(self) -> dict:
        """Return which columns are visible/hidden for saving settings"""
        state = {}
        for i in range(self.columnCount()):
            header_item = self.horizontalHeaderItem(i)
            if header_item:
                header_text = header_item.text()
                is_visible = i not in self.hidden_columns
                state[header_text] = is_visible
        return state

    def setColumnVisibilityState(self, state: dict):
        """Restore column visibility from saved settings"""
        for i in range(self.columnCount()):
            header_item = self.horizontalHeaderItem(i)
            if header_item:
                header_text = header_item.text()
                if header_text in state:
                    if state[header_text]:
                        self.showColumn(i)
                    else:
                        self.hideColumn(i)

    def autoFitColumn(self, logicalIndex):
        """Resize a column to fit its contents when double-clicked"""
        self.resizeColumnToContents(logicalIndex)
        QApplication.processEvents()
