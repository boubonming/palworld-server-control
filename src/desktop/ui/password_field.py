from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLineEdit, QToolButton


class PasswordLineEdit(QLineEdit):
    """Password field with a visible temporary Show/Hide control."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setEchoMode(QLineEdit.Password)
        self.toggle_button = QToolButton(self)
        self.toggle_button.setObjectName("passwordToggle")
        self.toggle_button.setText("Show")
        self.toggle_button.setCheckable(True)
        self.toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_button.toggled.connect(self._set_password_visibility)
        self.setTextMargins(0, 0, 54, 0)
        self._position_toggle()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_toggle()

    def _position_toggle(self):
        self.toggle_button.setGeometry(self.width() - 52, 1, 48, self.height() - 2)

    def _set_password_visibility(self, visible):
        self.setEchoMode(QLineEdit.Normal if visible else QLineEdit.Password)
        self.toggle_button.setText("Hide" if visible else "Show")
