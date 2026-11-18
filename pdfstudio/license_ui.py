"""Qt activation gate. No PDF window is shown until server verification succeeds."""
from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton,
                                QHBoxLayout, QMessageBox)
from .licensing import LicenseManager, ActivationError


class LicenseDialog(QDialog):
    def __init__(self, manager: LicenseManager, reason: str = '', parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle('PDF Studio Pro — License Activation')
        self.setMinimumWidth(460)
        self.setStyleSheet('''QDialog {background:#171e29;color:#f1f5f9;}
            QLabel {color:#e7edf5;font-size:12px;}
            QLineEdit {background:#273447;color:#fff;padding:10px;border:1px solid #58667b;border-radius:5px;}
            QPushButton {background:#db2030;color:white;font-weight:bold;padding:10px;border-radius:5px;}''')
        layout = QVBoxLayout(self)
        title = QLabel('PDF Studio Pro  |  Lifetime License')
        title.setStyleSheet('font-size:18px;font-weight:bold;')
        layout.addWidget(title)
        hint = QLabel('A license must be activated online on one Windows PC.\n'
                      'Existing activations are verified with the license server at every startup.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.key = QLineEdit()
        self.key.setPlaceholderText('PSP-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX')
        layout.addWidget(self.key)
        self.message = QLabel(reason)
        self.message.setWordWrap(True)
        self.message.setStyleSheet('color:#ffc0c0;')
        layout.addWidget(self.message)
        buttons = QHBoxLayout()
        activate_btn = QPushButton('Activate online')
        activate_btn.clicked.connect(self.activate)
        buttons.addWidget(activate_btn)
        cancel_btn = QPushButton('Exit')
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)

    def activate(self):
        self.message.setText('Contacting the license server…')
        self.repaint()
        try:
            self.manager.activate(self.key.text())
        except ActivationError as exc:
            self.message.setText(str(exc))
            return
        self.accept()
