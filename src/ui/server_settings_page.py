import os
import re

from PySide6.QtCore import Signal
from PySide6.QtGui import QDoubleValidator, QIntValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core import config_manager
from core.setting_metadata import get_setting_tooltip
from ui.page import Page
from ui.password_field import PasswordLineEdit
from shared.status import ServerState


class ServerSettingsPage(Page):
    saved = Signal()

    def __init__(self):
        super().__init__("Server Settings", "Edit values from PalWorldSettings.ini")
        self.settings_tabs = QTabWidget()
        self.settings_tabs.tabBar().hide()
        self.category_nav = QWidget()
        self.category_nav.setFixedWidth(270)
        self.category_layout = QVBoxLayout(self.category_nav)
        self.category_layout.setContentsMargins(0, 0, 10, 0)
        self.category_list = QListWidget()
        self.category_list.setSpacing(3)
        self.category_list.setStyleSheet("""
            QListWidget { background: transparent; border: 0; outline: 0; }
            QListWidget::item {
                padding: 8px 10px;
                color: #a7a7ad;
                border-left: 3px solid transparent;
            }
            QListWidget::item:hover { background: #292a2f; color: #eeeeee; }
            QListWidget::item:selected {
                background: #2f333b;
                color: #ffffff;
                border-left: 3px solid #3e7bfa;
            }
        """)
        self.category_list.itemClicked.connect(self._select_category_item)
        self.category_layout.addWidget(self.category_list)
        self.category_categories = []
        self.search_results = QScrollArea()
        self.search_results.setWidgetResizable(True)
        self.search_panel = QWidget()
        self.search_layout = QFormLayout(self.search_panel)
        self.search_results.setWidget(self.search_panel)
        self.settings_view = QStackedWidget()
        self.settings_view.addWidget(self.settings_tabs)
        self.settings_view.addWidget(self.search_results)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search settings by key...")
        self.search.textChanged.connect(self.filter_settings)
        self.content_layout.addWidget(self.search)
        self.settings_body = QWidget()
        self.settings_body_layout = QHBoxLayout(self.settings_body)
        self.settings_body_layout.setContentsMargins(0, 0, 0, 0)
        self.settings_body_layout.addWidget(self.category_nav)
        self.settings_body_layout.addWidget(self.settings_view, 1)
        self.content_layout.addWidget(self.settings_body)
        self.setting_fields = {}
        self.setting_rows = {}
        self.setting_categories = {}
        self.category_forms = {}
        self._search_mode = False
        self.reload_button = QPushButton("Reload settings")
        self.reload_button.setObjectName("secondaryAction")
        self.reload_button.clicked.connect(self.reload_settings)

        buttons = QHBoxLayout()
        buttons.addWidget(self.reload_button)
        self.save_button = QPushButton("Save settings")
        self.save_button.setObjectName("primaryAction")
        self.save_button.clicked.connect(self.save)
        buttons.addWidget(self.save_button)
        self.feedback = QLabel()
        self.feedback.setObjectName("saveFeedback")
        buttons.addWidget(self.feedback)
        buttons.addStretch()
        self.reset_button = QPushButton("Reset to defaults")
        self.reset_button.setObjectName("secondaryAction")
        self.reset_button.clicked.connect(self.reset_to_defaults)
        buttons.addWidget(self.reset_button)
        self.revert_button = QPushButton("Revert to backup")
        self.revert_button.setObjectName("secondaryAction")
        self.revert_button.clicked.connect(self.revert_to_backup)
        buttons.addWidget(self.revert_button)
        self.content_layout.addLayout(buttons)
        self.reload_settings()

    CATEGORY_KEYS = {
        "General & World": {"Difficulty", "RandomizerType", "RandomizerSeed", "bIsRandomizerPalLevelRandom", "DayTimeSpeedRate", "NightTimeSpeedRate", "AutoSaveSpan", "bIsMultiplay", "bIsPvP", "bHardcore", "bPalLost", "bCharacterRecreateInHardcore", "bEnableFastTravel", "bEnableFastTravelOnlyBaseCamp", "bIsStartLocationSelectByMap", "bExistPlayerAfterLogout", "ServerPlayerMaxNum"},
        "Experience & Pal Capture": {"ExpRate", "PalCaptureRate", "PalSpawnNumRate", "PalEggDefaultHatchingTime", "WorkSpeedRate", "MonsterFarmActionSpeedRate"},
        "Player & Pal Survival": {"PlayerStomachDecreaceRate", "PlayerStaminaDecreaceRate", "PlayerAutoHPRegeneRate", "PlayerAutoHpRegeneRateInSleep", "PalStomachDecreaceRate", "PalStaminaDecreaceRate", "PalAutoHPRegeneRate", "PalAutoHPRegeneRateInSleep", "ItemWeightRate", "EquipmentDurabilityDamageRate", "ItemCorruptionMultiplier"},
        "Combat & Damage": {"PalDamageRateAttack", "PalDamageRateDefense", "PlayerDamageRateAttack", "PlayerDamageRateDefense", "bEnableInvaderEnemy", "bActiveUNKO", "bEnableAimAssistPad", "bEnableAimAssistKeyboard", "bEnableDefenseOtherGuildPlayer", "bEnableVoiceChat"},
        "Building, Gathering & Drops": {"BuildObjectHpRate", "BuildObjectDamageRate", "BuildObjectDeteriorationDamageRate", "CollectionDropRate", "CollectionObjectHpRate", "CollectionObjectRespawnSpeedRate", "EnemyDropItemRate", "DropItemMaxNum", "PhysicsActiveDropItemMaxNum", "DropItemMaxNum_UNKO", "DropItemAliveMaxHours", "SupplyDropSpan", "MaxBuildingLimitNum"},
        "Bases, Guilds & Multiplayer": {"BaseCampMaxNum", "BaseCampWorkerMaxNum", "GuildPlayerMaxNum", "BaseCampMaxNumInGuild", "CoopPlayerMaxNum", "bAutoResetGuildNoOnlinePlayers", "AutoResetGuildTimeNoOnlinePlayers", "bCanPickupOtherGuildDeathPenaltyDrop", "GuildRejoinCooldownMinutes", "MaxGuildsPerFrame"},
        "Server Identity & Access": {"ServerName", "ServerDescription", "ServerPassword", "AdminPassword", "Region", "bUseAuth", "bAllowClientMod", "bShowPlayerList", "ChatPostLimitPerMinute", "BanListURL"},
        "Network, API & RCON": {"PublicPort", "PublicIP", "RCONEnabled", "RCONPort", "RESTAPIEnabled", "RESTAPIPort", "CrossplayPlatforms", "AllowConnectPlatform"},
        "Performance, Replication & System": {"bEnableNonLoginPenalty", "bInvisibleOtherGuildBaseCampAreaFX", "bBuildAreaLimit", "bIsUseBackupSaveData", "LogFormatType", "bIsShowJoinLeftMessage", "ServerReplicatePawnCullDistance", "ItemContainerForceMarkDirtyInterval", "PlayerDataPalStorageUpdateCheckTickInterval", "AutoTransferMasterCheckIntervalSeconds", "AutoTransferMasterThresholdDays", "BlockRespawnTime", "RespawnPenaltyDurationThreshold", "RespawnPenaltyTimeScale", "BuildingNameDisplayCacheTTLSeconds"},
        "PvP & Death Penalties": {"DeathPenalty", "bEnablePlayerToPlayerDamage", "bEnableFriendlyFire", "bEnableNonLoginPenalty", "AdditionalDropItemWhenPlayerKillingInPvPMode", "AdditionalDropItemNumWhenPlayerKillingInPvPMode", "bAdditionalDropItemWhenPlayerKillingInPvPMode", "bDisplayPvPItemNumOnWorldMap_BaseCamp", "bDisplayPvPItemNumOnWorldMap_Player"},
        "Voice Chat & Accessibility": {"VoiceChatMaxVolumeDistance", "VoiceChatZeroVolumeDistance", "bAllowEnhanceStat_Health", "bAllowEnhanceStat_Attack", "bAllowEnhanceStat_Stamina", "bAllowEnhanceStat_Weight", "bAllowEnhanceStat_WorkSpeed", "bEnableBuildingPlayerUIdDisplay", "bEnableAimAssistPad", "bEnableAimAssistKeyboard"},
    }

    CATEGORY_ICONS = {
        "General & World": "🌍",
        "Experience & Pal Capture": "✨",
        "Player & Pal Survival": "🧍",
        "Combat & Damage": "⚔️",
        "Building, Gathering & Drops": "🏗️",
        "Bases, Guilds & Multiplayer": "🏠",
        "Server Identity & Access": "🔐",
        "Network, API & RCON": "🌐",
        "Performance, Replication & System": "⚙️",
        "PvP & Death Penalties": "☠️",
        "Voice Chat & Accessibility": "🔊",
        "Advanced / New Settings": "🧩",
    }

    def reload_settings(self):
        settings = config_manager.get_palworld_editor_settings()
        if self._search_mode:
            self._remove_rows(self.search_layout)
        self._search_mode = False
        while self.settings_tabs.count():
            widget = self.settings_tabs.widget(0)
            self.settings_tabs.removeTab(0)
            widget.deleteLater()
        self.setting_fields.clear()
        self.setting_rows.clear()
        self.setting_categories.clear()
        self.category_forms.clear()
        self.category_list.clear()
        self.category_categories.clear()
        categories = {name: [] for name in self.CATEGORY_KEYS}
        categories["Advanced / New Settings"] = []
        for key in settings:
            category = next((name for name, keys in self.CATEGORY_KEYS.items() if key in keys), "Advanced / New Settings")
            categories[category].append(key)
        for category, keys in categories.items():
            if not keys:
                continue
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            panel = QWidget()
            form = QFormLayout(panel)
            self.category_forms[category] = form
            for key in sorted(keys):
                field = self.create_setting_field(settings[key], key)
                label = QLabel(self.display_name(key))
                tooltip = get_setting_tooltip(key)
                label.setToolTip(tooltip)
                field.setToolTip(tooltip)
                form.addRow(label, field)
                self.setting_fields[key] = field
                self.setting_rows[key] = (label, field)
                self.setting_categories[key] = category
                if isinstance(field, QCheckBox):
                    field.stateChanged.connect(self.mark_dirty)
                else:
                    field.textChanged.connect(self.mark_dirty)
            scroll.setWidget(panel)
            self.settings_tabs.addTab(scroll, category)
        self._build_category_navigation(categories)
        self._saved_values = self.current_values()
        self.update_save_button()
        self.update_editability()
        self.filter_settings(self.search.text())

    def _build_category_navigation(self, categories):
        for category in (name for name, keys in categories.items() if keys):
            display_category = category
            item = QListWidgetItem(f"{self.CATEGORY_ICONS.get(category, '🧩')}  {display_category}")
            self.category_list.addItem(item)
            self.category_categories.append(category)
        if self.category_categories:
            self.category_list.setCurrentRow(0)

    def _select_category_item(self, item):
        row = self.category_list.row(item)
        if 0 <= row < len(self.category_categories):
            self._select_category(self.category_categories[row])

    def _select_category(self, category):
        for index in range(self.settings_tabs.count()):
            if self.settings_tabs.tabText(index) == category:
                self.settings_tabs.setCurrentIndex(index)
                break

    def filter_settings(self, text):
        query = text.strip().lower()
        if not query:
            if self._search_mode:
                self._remove_rows(self.search_layout)
                for key, (label, field) in self.setting_rows.items():
                    category_form = self.category_forms[self.setting_categories[key]]
                    self._add_row(category_form, label, field, category_form.parentWidget())
                self._search_mode = False
            self.settings_tabs.setVisible(True)
            self.search_results.setVisible(False)
            self.category_nav.setVisible(True)
            self.category_nav.setFixedWidth(270)
            self.settings_view.setCurrentIndex(0)
            return
        if not self._search_mode:
            for category_form in self.category_forms.values():
                self._remove_rows(category_form)
        else:
            self._remove_rows(self.search_layout)
        for key, (label, field) in self.setting_rows.items():
            if query in key.lower() or query in self.display_name(key).lower():
                self._add_row(self.search_layout, label, field, self.search_panel)
        self._search_mode = True
        self.settings_tabs.setVisible(False)
        self.search_results.setVisible(True)
        self.category_nav.setVisible(False)
        self.settings_view.setCurrentIndex(1)

    def update_editability(self, running=None):
        if running is None:
            running = config_manager.is_server_process_running()
        editable = not running
        self.settings_tabs.setEnabled(editable)
        self.search_results.setEnabled(editable)
        self.reload_button.setEnabled(editable)
        self.save_button.setEnabled(editable)
        self.reset_button.setEnabled(editable)
        self.revert_button.setEnabled(editable and os.path.exists(config_manager.get_palworld_backup_path()))

    def handle_server_status(self, status):
        running = status.state is ServerState.RUNNING
        self.update_editability(running)
        if running:
            self.feedback.setText(
                "The Palworld server is running. Stop it before changing server settings."
            )

    def _remove_rows(self, layout):
        for label, field in self.setting_rows.values():
            layout.takeRow(label)
            label.hide()
            field.hide()

    @staticmethod
    def _add_row(layout, label, field, parent):
        label.setParent(parent)
        field.setParent(parent)
        layout.addRow(label, field)
        label.show()
        field.show()

    @staticmethod
    def create_setting_field(value, key):
        lowered = value.lower()
        if lowered in {"true", "false"}:
            field = QCheckBox()
            field.setChecked(lowered == "true")
            return field
        is_password = "Password" in key or key == "AdminPassword"
        field = PasswordLineEdit(value) if is_password else QLineEdit(value)
        if re.fullmatch(r"-?\d+", value):
            field.setValidator(QIntValidator(field))
        elif re.fullmatch(r"-?\d+\.\d+", value):
            validator = QDoubleValidator(field)
            validator.setNotation(QDoubleValidator.StandardNotation)
            field.setValidator(validator)
        return field

    @staticmethod
    def field_value(field):
        if isinstance(field, QCheckBox):
            return "True" if field.isChecked() else "False"
        return field.text()

    def current_values(self):
        return tuple(
            (key, self.field_value(self.setting_fields[key]))
            for key in sorted(self.setting_fields)
        )

    def mark_dirty(self, *_args):
        self.update_save_button()

    def update_save_button(self):
        dirty = hasattr(self, "_saved_values") and self.current_values() != self._saved_values
        self.save_button.setText("Save settings *" if dirty else "Save settings")

    @staticmethod
    def display_name(key):
        if key.startswith("b") and len(key) > 1 and key[1].isupper():
            key = key[1:]
        key = key.replace("_", " ")
        key = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", key)
        return re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", key)

    def save(self):
        if config_manager.is_server_process_running():
            self.feedback.setText("Stop the Palworld server before changing server settings.")
            self.update_editability()
            return
        for key, field in self.setting_fields.items():
            if isinstance(field, QLineEdit) and field.validator() and not field.hasAcceptableInput():
                self.feedback.setText(f"{self.display_name(key)} must contain a valid number.")
                return
        updates = {key: self.field_value(field) for key, field in self.setting_fields.items()}
        try:
            config_manager.update_palworld_ini_settings(updates)
        except (FileNotFoundError, ValueError) as exc:
            self.feedback.setText(str(exc))
            return
        self._saved_values = self.current_values()
        self.update_save_button()
        self.feedback.clear()
        self.saved.emit()

    def reset_to_defaults(self):
        if config_manager.is_server_process_running():
            self.feedback.setText("Stop the Palworld server before changing server settings.")
            return
        answer = QMessageBox.question(self, "Reset server settings", "Reset settings known by DefaultPalWorldSettings.ini? A backup will be created first.", QMessageBox.Yes | QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        try:
            config_manager.reset_palworld_ini_settings()
        except (FileNotFoundError, ValueError) as exc:
            self.feedback.setText(str(exc))
            return
        self.reload_settings()
        self.feedback.setText("Server settings reset to the Palworld defaults.")

    def revert_to_backup(self):
        if config_manager.is_server_process_running():
            self.feedback.setText("Stop the Palworld server before reverting server settings.")
            return
        try:
            changes = config_manager.get_palworld_backup_changes()
        except FileNotFoundError as exc:
            self.feedback.setText(str(exc))
            return
        if not changes:
            self.feedback.setText("The current settings already match the backup.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Review settings changes")
        dialog.resize(700, 500)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("The following settings will be restored from the backup:"))
        preview = QPlainTextEdit()
        preview.setReadOnly(True)
        preview.setPlainText(self._format_backup_changes(changes))
        layout.addWidget(preview)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No)
        revert_button = buttons.button(QDialogButtonBox.StandardButton.Yes)
        revert_button.setText("Revert to backup")
        revert_button.setObjectName("destructiveAction")
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.No)
        cancel_button.setText("Cancel")
        cancel_button.setObjectName("secondaryAction")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            config_manager.revert_to_palworld_backup()
        except (FileNotFoundError, ValueError) as exc:
            self.feedback.setText(str(exc))
            return
        self.reload_settings()
        self.feedback.setText("Server settings reverted to the backup.")

    def _format_backup_changes(self, changes):
        lines = []
        for key, current, backup in changes:
            if "password" in key.lower():
                current = backup = "••••••••" if current or backup else "(empty)"
            lines.extend((
                self.display_name(key),
                f"  Current: {current or '(empty)'}",
                f"  Backup:  {backup or '(empty)'}",
                "",
            ))
        return "\n".join(lines).rstrip()
