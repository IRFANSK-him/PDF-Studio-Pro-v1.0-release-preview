"""Part 2 editing dialogs; kept separate from the main PySide6 window."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFormLayout, QDialogButtonBox,
    QLineEdit, QDoubleSpinBox, QComboBox, QCheckBox, QPushButton,
    QFileDialog, QPlainTextEdit, QSpinBox, QWidget,
)


DIALOG_CSS = """
QDialog { background: #1d2734; color: #edf3fa; }
QLabel, QCheckBox { color: #edf3fa; }
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
  background: #263445; color: #edf3fa; border: 1px solid #526174;
  border-radius: 5px; padding: 5px; min-height: 26px;
}
QPushButton { background: #354760; color: white; border: 1px solid #526174;
  border-radius: 5px; padding: 7px; }
QPushButton:hover { background: #446081; }
"""


class EditorDialog(QDialog):
    def __init__(self, title: str, parent=None, width: int = 430):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(width)
        self.setStyleSheet(DIALOG_CSS)
        self.outer = QVBoxLayout(self)
        self.form = QFormLayout()
        self.form.setSpacing(9)
        self.outer.addLayout(self.form)

    def add_buttons(self):
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.outer.addWidget(buttons)

    @staticmethod
    def number(default: float, maximum: float = 2000, step: float = 5) -> QDoubleSpinBox:
        number = QDoubleSpinBox()
        number.setRange(0, maximum)
        number.setValue(default)
        number.setDecimals(1)
        number.setSingleStep(step)
        number.setSuffix(" pt")
        return number


class TextDialog(EditorDialog):
    def __init__(self, page_size: tuple[float, float], parent=None):
        super().__init__("Insert PDF text", parent)
        self.outer.insertWidget(0, QLabel("Insert selectable text on the current page."))
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("Text to insert")
        self.text.setMaximumHeight(100)
        self.form.addRow("Text", self.text)
        self.x = self.number(min(72, page_size[0]), page_size[0])
        self.y = self.number(min(120, page_size[1]), page_size[1])
        self.size = self.number(14, 144, 1)
        self.size.setMinimum(4)
        self.color = QComboBox()
        self.color.addItems(["Black", "Dark blue", "Red", "Green", "Gray"])
        self.font_path = QLineEdit()
        self.font_path.setPlaceholderText("Optional custom TTF/OTF font")
        browse = QPushButton("Browse font…")
        browse.clicked.connect(self._browse_font)
        font_row = QWidget()
        row = QHBoxLayout(font_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.font_path, 1)
        row.addWidget(browse)
        for label, widget in (("X position", self.x), ("Y baseline", self.y),
                              ("Font size", self.size), ("Text color", self.color),
                              ("Custom font", font_row)):
            self.form.addRow(label, widget)
        self.add_buttons()

    def _browse_font(self):
        path = QFileDialog.getOpenFileName(self, "Choose font", "", "Fonts (*.ttf *.otf)")[0]
        if path:
            self.font_path.setText(path)

    def values(self):
        colors = [(0, 0, 0), (0.05, 0.16, 0.40), (0.85, 0.13, 0.18),
                  (0.12, 0.45, 0.24), (0.45, 0.45, 0.45)]
        return dict(text=self.text.toPlainText(), x=self.x.value(), y=self.y.value(),
                    font_size=self.size.value(), color=colors[self.color.currentIndex()],
                    font_file=self.font_path.text().strip() or None)


class ImageDialog(EditorDialog):
    def __init__(self, page_size: tuple[float, float], filename: str, parent=None):
        super().__init__("Insert image on current page", parent)
        self.outer.insertWidget(0, QLabel(f"Selected file: {Path(filename).name}"))
        self.x = self.number(min(72, page_size[0]), page_size[0])
        self.y = self.number(min(72, page_size[1]), page_size[1])
        self.width = self.number(min(180, max(1, page_size[0] - self.x.value())), page_size[0])
        self.height = self.number(min(120, max(1, page_size[1] - self.y.value())), page_size[1])
        self.width.setMinimum(1)
        self.height.setMinimum(1)
        for label, field in (("X position", self.x), ("Y position", self.y),
                             ("Width", self.width), ("Height", self.height)):
            self.form.addRow(label, field)
        self.add_buttons()

    def values(self):
        return dict(x=self.x.value(), y=self.y.value(),
                    width=self.width.value(), height=self.height.value())


class PhraseDialog(EditorDialog):
    def __init__(self, action: str, parent=None):
        super().__init__(f"{action} text", parent)
        self.text = QLineEdit()
        self.text.setPlaceholderText("Exact phrase (searchable text only)")
        self.scope = QCheckBox("Apply to all pages")
        self.form.addRow("Find phrase", self.text)
        self.form.addRow("Scope", self.scope)
        self.add_buttons()


class WatermarkDialog(EditorDialog):
    def __init__(self, parent=None):
        super().__init__("Add text watermark", parent)
        self.text = QLineEdit("PDF STUDIO PRO")
        self.size = self.number(44, 144, 1)
        self.size.setMinimum(8)
        self.opacity = QSpinBox()
        self.opacity.setRange(5, 100)
        self.opacity.setSuffix("%")
        self.opacity.setValue(25)
        self.position = QComboBox()
        self.position.addItems(["center", "top-right", "bottom-right"])
        self.scope = QCheckBox("Apply to all pages")
        self.scope.setChecked(True)
        self.form.addRow("Watermark text", self.text)
        self.form.addRow("Text size", self.size)
        self.form.addRow("Opacity", self.opacity)
        self.form.addRow("Position", self.position)
        self.form.addRow("Scope", self.scope)
        self.add_buttons()

    def values(self):
        return dict(text=self.text.text(), all_pages=self.scope.isChecked(),
                    font_size=self.size.value(), opacity=self.opacity.value()/100,
                    position=self.position.currentText())


class MetadataDialog(EditorDialog):
    def __init__(self, metadata: dict[str, str], parent=None):
        super().__init__("Edit PDF metadata", parent)
        self.fields: dict[str, QLineEdit] = {}
        for key in ("title", "author", "subject", "keywords", "creator", "producer"):
            field = QLineEdit(metadata.get(key, ""))
            field.setMaxLength(1000)
            self.form.addRow(key.capitalize(), field)
            self.fields[key] = field
        self.add_buttons()

    def values(self) -> dict[str, str]:
        return {key: input_.text() for key, input_ in self.fields.items()}


class ProtectDialog(EditorDialog):
    def __init__(self, parent=None):
        super().__init__("Protect PDF — AES-256", parent, width=470)
        self.outer.insertWidget(0, QLabel("Applies when the PDF is saved. Keep the owner password safe."))
        self.user = QLineEdit()
        self.owner = QLineEdit()
        self.user_confirm = QLineEdit()
        self.owner_confirm = QLineEdit()
        for widget in (self.user, self.owner, self.user_confirm, self.owner_confirm):
            widget.setEchoMode(QLineEdit.EchoMode.Password)
        self.allow_print = QCheckBox("Allow printing")
        self.allow_print.setChecked(True)
        self.allow_copy = QCheckBox("Allow copying text and images")
        self.allow_copy.setChecked(True)
        self.form.addRow("Open password", self.user)
        self.form.addRow("Confirm open", self.user_confirm)
        self.form.addRow("Owner password", self.owner)
        self.form.addRow("Confirm owner", self.owner_confirm)
        self.form.addRow("Permissions", self.allow_print)
        self.form.addRow("", self.allow_copy)
        self.add_buttons()

    def values(self):
        from .engine import PDFStudioError
        import fitz
        if self.user.text() != self.user_confirm.text() or self.owner.text() != self.owner_confirm.text():
            raise PDFStudioError("Passwords and confirmation fields do not match.")
        permissions = fitz.PDF_PERM_ACCESSIBILITY
        if self.allow_print.isChecked():
            permissions |= fitz.PDF_PERM_PRINT | fitz.PDF_PERM_PRINT_HQ
        if self.allow_copy.isChecked():
            permissions |= fitz.PDF_PERM_COPY
        return self.user.text(), self.owner.text(), permissions
