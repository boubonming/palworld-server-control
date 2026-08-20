import csv
import io

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStyle,
    QVBoxLayout,
    QWidget,
)


class CheckableListWidget(QListWidget):
    """Make clicking a checkable item's text toggle its checkbox too."""

    def mouseReleaseEvent(self, event):
        position = event.position().toPoint()
        index = self.indexAt(position)
        item = self.itemFromIndex(index) if index.isValid() else None
        clicked_indicator = False
        if item is not None:
            # The native checkbox occupies the leading edge of the item. Keep
            # its built-in toggle, and toggle explicitly for the rest of the row.
            item_rect = self.visualItemRect(item)
            indicator_width = self.style().pixelMetric(
                QStyle.PM_IndicatorWidth,
                None,
                self,
            )
            clicked_indicator = position.x() <= item_rect.left() + indicator_width + 8

        super().mouseReleaseEvent(event)
        if item is not None and not clicked_indicator:
            item.setCheckState(
                Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked
            )


class MultiSelectField(QWidget):
    """Compact field that edits an INI-style parenthesized list."""

    textChanged = Signal(str)

    def __init__(self, value, options, quote_values=False, parent=None):
        super().__init__(parent)
        self._quote_values = quote_values
        self._selected = self._parse(value)
        known_values = {option_value for _label, option_value in options}
        self._options = list(options)
        self._options.extend(
            (unknown, unknown) for unknown in self._selected if unknown not in known_values
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.button = QPushButton()
        self.button.setObjectName("secondaryAction")
        self.button.clicked.connect(self._open_dialog)
        layout.addWidget(self.button)
        self._update_button()

    @staticmethod
    def _parse(value):
        value = value.strip()
        if value.startswith("(") and value.endswith(")"):
            value = value[1:-1]
        if not value.strip():
            return []
        try:
            return [
                item.strip().strip('"')
                for item in next(csv.reader(io.StringIO(value), skipinitialspace=True))
                if item.strip().strip('"')
            ]
        except (csv.Error, StopIteration):
            return [item.strip().strip('"') for item in value.split(",") if item.strip()]

    def text(self):
        if self._quote_values:
            values = ",".join(f'"{value.replace(chr(34), chr(92) + chr(34))}"' for value in self._selected)
        else:
            values = ",".join(self._selected)
        return f"({values})"

    def _update_button(self):
        count = len(self._selected)
        if not count:
            summary = "None selected"
            full_summary = ""
        else:
            labels = dict((value, label) for label, value in self._options)
            full_summary = ", ".join(
                labels.get(value, value) for value in self._selected
            )
            if self.button.fontMetrics().horizontalAdvance(full_summary) <= 360:
                summary = full_summary
            else:
                summary = f"{count} selected"
        self.button.setToolTip(
            full_summary if full_summary and full_summary != summary and count <= 20 else ""
        )
        self.button.setText(f"{summary}  ▾")

    def _open_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Select values")
        dialog.resize(620, 560)
        layout = QVBoxLayout(dialog)

        search = QLineEdit()
        search.setPlaceholderText("Search by name or ID...")
        layout.addWidget(search)

        custom_row = QHBoxLayout()
        custom_value = QLineEdit()
        custom_value.setPlaceholderText("Add a value not listed...")
        custom_row.addWidget(custom_value)
        add_custom_button = QPushButton("Add value")
        add_custom_button.setObjectName("secondaryAction")
        custom_row.addWidget(add_custom_button)
        layout.addLayout(custom_row)

        choices = CheckableListWidget()
        choices.setAlternatingRowColors(True)
        for label, value in self._options:
            item = QListWidgetItem(f"{label}  ({value})" if label != value else value)
            item.setData(Qt.UserRole, value)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if value in self._selected else Qt.Unchecked)
            choices.addItem(item)
        layout.addWidget(choices)

        def filter_choices(query):
            query = query.strip().lower()
            for index in range(choices.count()):
                item = choices.item(index)
                item.setHidden(query not in item.text().lower())

        search.textChanged.connect(filter_choices)

        def add_custom_value():
            value = custom_value.text().strip()
            if not value:
                return
            for index in range(choices.count()):
                item = choices.item(index)
                if item.data(Qt.UserRole) == value:
                    item.setCheckState(Qt.Checked)
                    item.setHidden(False)
                    break
            else:
                item = QListWidgetItem(value)
                item.setData(Qt.UserRole, value)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked)
                choices.addItem(item)
            search.clear()
            custom_value.clear()

        add_custom_button.clicked.connect(add_custom_value)
        custom_value.returnPressed.connect(add_custom_value)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        clear_button = buttons.addButton("Clear all", QDialogButtonBox.ResetRole)
        clear_button.setObjectName("secondaryAction")

        def clear_choices():
            for index in range(choices.count()):
                choices.item(index).setCheckState(Qt.Unchecked)

        clear_button.clicked.connect(clear_choices)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.Accepted:
            return
        self._selected = [
            choices.item(index).data(Qt.UserRole)
            for index in range(choices.count())
            if choices.item(index).checkState() == Qt.Checked
        ]
        known_values = {value for _label, value in self._options}
        self._options.extend(
            (value, value) for value in self._selected if value not in known_values
        )
        self._update_button()
        self.textChanged.emit(self.text())
