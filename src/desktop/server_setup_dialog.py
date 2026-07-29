import os
import sys

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from core import config_manager, docker_deployment


class ServerSetupDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Set up Palworld server")
        self.setModal(True)
        self.resize(620, 330)

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Choose how this computer manages the Palworld server. "
            "You can use Docker Compose on Windows or Linux."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.native_backend = QRadioButton("Native Windows server")
        self.docker_backend = QRadioButton("Docker Compose server")
        self.native_backend.setVisible(sys.platform == "win32")
        self.native_backend.toggled.connect(self._update_backend_fields)
        self.docker_backend.toggled.connect(self._update_backend_fields)
        layout.addWidget(self.native_backend)
        layout.addWidget(self.docker_backend)

        self.native_fields = QWidget()
        native_form = QFormLayout(self.native_fields)
        self.native_directory = QLineEdit(config.get("palworld_dir", ""))
        native_form.addRow(
            "Palworld folder",
            self._path_picker(self.native_directory, "Select Palworld server folder"),
        )
        layout.addWidget(self.native_fields)

        self.docker_fields = QWidget()
        docker_form = QFormLayout(self.docker_fields)
        self.compose_directory = QLineEdit(config.get("docker_compose_dir", ""))
        docker_form.addRow(
            "Compose folder",
            self._path_picker(self.compose_directory, "Select Docker Compose folder"),
        )
        self.create_stack = QCheckBox("Create a new Palworld Docker Compose stack")
        self.create_stack.setChecked(False)
        self.create_stack.toggled.connect(self._update_community_option)
        docker_form.addRow("Setup", self.create_stack)
        self.community_server = QCheckBox(
            "Start as a community server (listed in the community browser)"
        )
        self.community_server.setToolTip(
            "For an existing Compose stack, set COMMUNITY in its .env file."
        )
        docker_form.addRow("Visibility", self.community_server)
        self.compose_service = QLineEdit(config.get("docker_service_name", "palworld"))
        docker_form.addRow("Compose service", self.compose_service)
        layout.addWidget(self.docker_fields)

        self.error = QLabel()
        self.error.setStyleSheet("color: #ff6b6b;")
        self.error.setWordWrap(True)
        layout.addWidget(self.error)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        if sys.platform == "win32":
            self.native_backend.setChecked(True)
        else:
            self.docker_backend.setChecked(True)
        self._update_backend_fields()
        self._update_community_option(self.create_stack.isChecked())

    def _path_picker(self, field, title):
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(field)
        browse = QPushButton("Browse...")
        browse.clicked.connect(lambda: self._browse(field, title))
        row.addWidget(browse)
        return container

    def _browse(self, field, title):
        chosen = QFileDialog.getExistingDirectory(self, title, field.text().strip())
        if chosen:
            field.setText(chosen)

    def _update_backend_fields(self):
        use_native = self.native_backend.isVisible() and self.native_backend.isChecked()
        self.native_fields.setVisible(use_native)
        self.docker_fields.setVisible(not use_native)

    def _update_community_option(self, creating_stack):
        self.community_server.setEnabled(creating_stack)

    def _save(self):
        self.error.clear()
        try:
            if self.native_backend.isVisible() and self.native_backend.isChecked():
                directory = os.path.abspath(
                    os.path.expanduser(self.native_directory.text().strip())
                )
                if not os.path.isfile(os.path.join(directory, "PalServer.exe")):
                    raise FileNotFoundError("The selected folder does not contain PalServer.exe.")
                config_manager.update_paths_from_dir(directory)
                config_manager.CONFIG["server_backend"] = "windows_native"
                config_manager.save_config()
            else:
                directory = os.path.abspath(
                    os.path.expanduser(self.compose_directory.text().strip())
                )
                if not self.compose_directory.text().strip():
                    raise ValueError("Select a Docker Compose folder.")
                docker_deployment.validate_docker()
                if self.create_stack.isChecked():
                    docker_deployment.create_deployment(
                        directory,
                        community=self.community_server.isChecked(),
                    )
                config_manager.configure_docker_backend(
                    directory,
                    service_name=self.compose_service.text().strip() or "palworld",
                )
        except Exception as exc:
            self.error.setText(str(exc))
            return
        self.accept()
