from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDoubleValidator, QIntValidator
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QSlider, QVBoxLayout, QWidget


class NumericSettingField(QWidget):
    """Numeric input with a visible, enforced range from Palworld metadata."""

    textChanged = Signal(str)

    def __init__(self, value, minimum=None, maximum=None, hint="", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        self.input = QLineEdit(value)
        is_integer = value.lstrip("-").isdigit()
        if is_integer:
            validator = QIntValidator(self.input)
            if minimum is not None:
                validator.setBottom(int(minimum))
            if maximum is not None:
                validator.setTop(int(maximum))
        else:
            validator = QDoubleValidator(self.input)
            validator.setNotation(QDoubleValidator.StandardNotation)
            if minimum is not None:
                validator.setBottom(float(minimum))
            if maximum is not None:
                validator.setTop(float(maximum))
        self.input.setValidator(validator)
        self.input.textChanged.connect(self.textChanged.emit)
        layout.addWidget(self.input)

        if is_integer and minimum is not None and maximum is not None:
            slider_row = QHBoxLayout()
            slider_row.setContentsMargins(0, 0, 0, 0)
            minimum_label = QLabel(f"{int(minimum):,}")
            maximum_label = QLabel(f"{int(maximum):,}")
            self.slider = QSlider(Qt.Horizontal)
            self.slider.setRange(int(minimum), int(maximum))
            interval = max(1, (int(maximum) - int(minimum)) // 10)
            self.slider.setPageStep(interval)
            self.slider.setTickInterval(interval)
            self.slider.setTickPosition(QSlider.TicksBelow)

            current = int(value)
            self.slider.setValue(
                max(int(minimum), min(current, int(maximum)))
            )
            self.slider.valueChanged.connect(
                lambda slider_value: self.input.setText(str(slider_value))
            )

            def update_slider(text):
                try:
                    input_value = int(text)
                except ValueError:
                    return
                if (
                    int(minimum) <= input_value <= int(maximum)
                    and self.slider.value() != input_value
                ):
                    self.slider.setValue(input_value)

            self.input.textChanged.connect(update_slider)
            slider_row.addWidget(minimum_label)
            slider_row.addWidget(self.slider, 1)
            slider_row.addWidget(maximum_label)
            layout.addLayout(slider_row)

        if minimum is not None and maximum is not None:
            self.validation_message = f"must be between {minimum:g} and {maximum:g}."
        elif minimum is not None:
            self.validation_message = f"must be at least {minimum:g}."
        elif maximum is not None:
            self.validation_message = f"must be no more than {maximum:g}."
        else:
            self.validation_message = "must contain a valid number."

        if hint:
            hint_label = QLabel(hint)
            hint_label.setWordWrap(True)
            hint_label.setStyleSheet("color: #9c9da5; font-size: 11px;")
            layout.addWidget(hint_label)

    def text(self):
        return self.input.text()

    def validator(self):
        return self.input.validator()

    def hasAcceptableInput(self):
        return self.input.hasAcceptableInput()
