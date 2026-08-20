from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class Page(QWidget):
    def __init__(self, title, subtitle=""):
        super().__init__()
        layout = QVBoxLayout(self)
        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")
        layout.addWidget(title_label)
        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setObjectName("pageSubtitle")
            layout.addWidget(subtitle_label)
        self.content_layout = layout
