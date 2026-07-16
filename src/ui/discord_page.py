from datetime import datetime

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core import config_manager
from integrations import discord_bot as bot_module
from ui.page import Page
from ui.password_field import PasswordLineEdit
from shared.discord_activity import normalize_channel_id
from shared.status import status_stylesheet


class DiscordPage(Page):
    def __init__(self):
        super().__init__("Discord Bot", "Connect, monitor, and control your Discord bot")

        self.status = QLabel("Discord bot is stopped")
        self.status.setObjectName("statusValue")

        controls = QHBoxLayout()
        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self.start)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop)
        self.restart_button = QPushButton("Restart")
        self.restart_button.clicked.connect(self.restart)
        for button in (self.start_button, self.stop_button, self.restart_button):
            controls.addWidget(button)
        controls.addStretch()

        status_section = QGroupBox("Bot status")
        status_layout = QVBoxLayout(status_section)
        status_layout.addWidget(self.status)
        status_layout.addLayout(controls)
        self.apply_status_color("Stopped")

        connection_section = QGroupBox("Connection")
        connection_layout = QFormLayout(connection_section)
        self.token = QWidget()
        token_layout = QHBoxLayout(self.token)
        token_layout.setContentsMargins(0, 0, 0, 0)
        self.token_input = PasswordLineEdit(config_manager.CONFIG.get("discord_bot_token", ""))
        self.token_input.setPlaceholderText("Discord bot token")
        token_layout.addWidget(self.token_input)
        self.save_token_button = QPushButton("Save token")
        self.save_token_button.clicked.connect(self.save_token)
        token_layout.addWidget(self.save_token_button)
        connection_layout.addRow("Bot token", self.token)

        startup = QCheckBox("Start Discord bot when app starts (saved immediately)")
        startup.setChecked(config_manager.get_discord_bot_auto_start())
        startup.toggled.connect(self.save_auto_start)
        connection_layout.addRow("", startup)
        self.auto_start = startup

        left_column = QVBoxLayout()
        left_column.addWidget(status_section)
        left_column.addWidget(connection_section)

        channels_section = QGroupBox("Control channels")
        channels_layout = QVBoxLayout(channels_section)
        self.channel_ids = QListWidget()
        self.channel_ids.setAlternatingRowColors(True)
        self.channel_ids.setStyleSheet("QListWidget::item { padding: 0px; }")
        for channel_id in config_manager.CONFIG.get("palworld_channel_ids", []):
            self.add_channel_item(str(channel_id))
        self.channel_ids.setMinimumHeight(110)
        self.channel_ids.setMaximumHeight(220)
        channels_layout.addWidget(self.channel_ids)

        channel_buttons = QHBoxLayout()
        add_channel = QToolButton()
        add_channel.setText("+")
        add_channel.setToolTip("Add control channel")
        add_channel.setFixedSize(34, 34)
        add_channel.clicked.connect(self.add_channel)
        channel_buttons.addWidget(add_channel)
        channel_buttons.addWidget(QLabel("Add, edit, and remove actions save immediately"))
        channel_buttons.addStretch()
        channels_layout.addLayout(channel_buttons)

        upper_layout = QHBoxLayout()
        upper_layout.addLayout(left_column, 1)
        upper_layout.addWidget(channels_section, 1)
        self.content_layout.addLayout(upper_layout)

        activity_section = QGroupBox("Recent Discord activity")
        activity_layout = QVBoxLayout(activity_section)
        self.activity_log = QPlainTextEdit()
        self.activity_log.setReadOnly(True)
        self.activity_log.setPlaceholderText("Discord commands and results will appear here.")
        self.activity_log.setMinimumHeight(220)
        activity_layout.addWidget(self.activity_log)
        self.content_layout.addWidget(activity_section, 1)

        self._saved_values = self.current_values()
        self.token_input.textChanged.connect(self.mark_dirty)
        self.channel_ids.itemChanged.connect(self.mark_dirty)
        bot_module.signals.bot_status_changed.connect(self.update_status)
        bot_module.signals.discord_activity.connect(self.record_activity)
        bot_module.signals.discord_channel_info.connect(self.update_channel_info)
        self.update_buttons()

    def current_channel_ids(self):
        channel_ids = []
        for index in range(self.channel_ids.count()):
            item = self.channel_ids.item(index)
            channel_id = item.data(Qt.ItemDataRole.UserRole)
            if not channel_id:
                text = item.text().strip()
                channel_id = text.rsplit("(", 1)[-1].rstrip(")") if text.endswith(")") else text
            if channel_id and str(channel_id).isdigit():
                channel_ids.append(str(channel_id))
        return channel_ids

    def current_values(self):
        return self.token_input.text().strip(), tuple(self.current_channel_ids())

    def has_unsaved_changes(self):
        return self.current_values() != self._saved_values

    def has_configured_token(self):
        return bool(self.token_input.text().strip())

    def mark_dirty(self, *_args):
        token_dirty = self.current_values()[0] != self._saved_values[0]
        self.save_token_button.setText("Save token *" if token_dirty else "Save token")
        self.update_buttons()

    def add_channel(self):
        channel_id, accepted = QInputDialog.getText(
            self, "Add control channel", "Discord channel ID (numbers only):"
        )
        self._add_channel_id(channel_id, accepted)

    def edit_channel(self):
        item = self.channel_ids.currentItem()
        if not item:
            return
        channel_id, accepted = QInputDialog.getText(
            self, "Edit control channel", "Discord channel ID (numbers only):",
            text=str(item.data(Qt.ItemDataRole.UserRole))
        )
        if not accepted:
            return
        channel_id = channel_id.strip()
        if not self.valid_channel_id(channel_id):
            self.show_channel_id_warning()
            return
        if channel_id != item.data(Qt.ItemDataRole.UserRole) and channel_id in self.current_channel_ids():
            QMessageBox.warning(self, "Channel already added", "That Discord channel ID is already in the control channel list.")
            return
        item.setData(Qt.ItemDataRole.UserRole, channel_id)
        display = f"Channel ID: {channel_id}"
        item.setText(display)
        row = self.channel_ids.itemWidget(item)
        channel_label = row.findChild(QLabel, "channelLabel") if row else None
        if channel_label:
            channel_label.setText(display)
        self.save_channels()

    def _add_channel_id(self, channel_id, accepted):
        channel_id = channel_id.strip()
        if not accepted:
            return
        if not self.valid_channel_id(channel_id):
            self.show_channel_id_warning()
            return
        if channel_id in self.current_channel_ids():
            QMessageBox.warning(self, "Channel already added", "That Discord channel ID is already in the control channel list.")
            return
        self.add_channel_item(channel_id)
        self.save_channels()

    def show_channel_id_warning(self):
        QMessageBox.warning(
            self,
            "Invalid Discord channel ID",
            "Discord channel IDs must contain numbers only.\n\nExample: 123456789012345678",
        )

    def add_channel_item(self, channel_id, label=None):
        display = label or f"Channel ID: {channel_id}"
        item = QListWidgetItem(display)
        item.setData(Qt.ItemDataRole.UserRole, channel_id)
        self.channel_ids.addItem(item)

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(6, 2, 4, 2)
        row_layout.setSpacing(4)
        channel_label = QLabel(display)
        channel_label.setObjectName("channelLabel")
        channel_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row_layout.addWidget(channel_label, 1)

        edit = QToolButton()
        edit.setText("\u270e")
        edit.setToolTip("Edit channel")
        edit.setFixedSize(28, 28)
        edit.clicked.connect(lambda _checked=False, target=item: self.edit_channel_item(target))
        row_layout.addWidget(edit)

        remove = QToolButton()
        remove.setText("\u00d7")
        remove.setToolTip("Remove channel")
        remove.setFixedSize(28, 28)
        remove.clicked.connect(lambda _checked=False, target=item: self.remove_channel_item(target))
        row_layout.addWidget(remove)

        row.setMinimumHeight(34)
        item.setSizeHint(QSize(0, 38))
        self.channel_ids.setItemWidget(item, row)

    def edit_channel_item(self, item):
        self.channel_ids.setCurrentItem(item)
        self.edit_channel()

    def remove_channel_item(self, item):
        row = self.channel_ids.row(item)
        if row >= 0:
            self.channel_ids.takeItem(row)
            self.save_channels()

    def update_channel_info(self, channel_id, label):
        for index in range(self.channel_ids.count()):
            item = self.channel_ids.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == channel_id:
                display = f"{label} ({channel_id})"
                item.setText(display)
                row = self.channel_ids.itemWidget(item)
                channel_label = row.findChild(QLabel, "channelLabel") if row else None
                if channel_label:
                    channel_label.setText(display)
                return

    @staticmethod
    def valid_channel_id(channel_id):
        return normalize_channel_id(channel_id) is not None

    def remove_channel(self):
        row = self.channel_ids.currentRow()
        if row >= 0:
            self.channel_ids.takeItem(row)
            self.save_channels()

    def save_token(self):
        config_manager.CONFIG["discord_bot_token"] = self.token_input.text().strip()
        config_manager.save_config()
        self._saved_values = (self.current_values()[0], self._saved_values[1])
        self.record_activity("Discord bot token saved")
        self.update_buttons()

    def save_channels(self):
        config_manager.CONFIG["palworld_channel_ids"] = self.current_channel_ids()
        config_manager.save_config()
        self._saved_values = self.current_values()
        self.record_activity("Discord control channels saved")
        self.update_buttons()

    def save_auto_start(self, enabled):
        config_manager.set_discord_bot_auto_start(enabled)

    def start(self):
        if not self.has_configured_token():
            self.update_status("Discord bot is stopped: token is missing")
        elif bot_module.discord_manager.state != "stopped":
            self.update_status("Discord bot is already started")
        elif bot_module.discord_manager.start(self.token_input.text().strip()):
            self.update_status("Starting Discord bot...")
        self.update_buttons()

    def stop(self):
        if bot_module.discord_manager.stop():
            self.update_status("Stopping Discord bot...")
        else:
            self.update_status("Discord bot is already stopped")
        self.update_buttons()

    def restart(self):
        if not self.has_configured_token():
            self.update_status("Discord bot is stopped: token is missing")
        elif bot_module.discord_manager.restart(self.token_input.text().strip()):
            self.update_status("Restarting Discord bot...")
        self.update_buttons()

    def update_status(self, status):
        self.status.setText(status)
        self.apply_status_color(status)
        self.update_buttons()

    def record_activity(self, activity):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.activity_log.appendPlainText(f"[{timestamp}] {activity}")

    def update_buttons(self):
        dirty = self.has_unsaved_changes()
        token_dirty = self.current_values()[0] != self._saved_values[0]
        has_token = self.has_configured_token()
        state = bot_module.discord_manager.state
        self.start_button.setEnabled(not dirty and has_token and state == "stopped")
        self.stop_button.setEnabled(state in {"starting", "running"})
        self.restart_button.setEnabled(not dirty and has_token and state == "running")
        self.save_token_button.setEnabled(token_dirty)

    def apply_status_color(self, status):
        self.status.setStyleSheet(status_stylesheet(status))
