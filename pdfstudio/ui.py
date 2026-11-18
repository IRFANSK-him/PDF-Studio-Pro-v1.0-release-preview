"""PDF Studio Pro v1.0 desktop shell, based on the approved UI reference."""
from __future__ import annotations

from pathlib import Path
import sys
import threading

from PySide6.QtCore import Qt, QSize, QRectF, QRect, Signal, QSignalBlocker, QTimer, QObject
from PySide6.QtGui import QAction, QIcon, QImage, QPainter, QColor, QPixmap, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QToolButton, QTabWidget, QScrollArea, QSplitter, QListWidget,
    QListWidgetItem, QAbstractItemView, QLineEdit, QComboBox, QFileDialog,
    QMessageBox, QInputDialog, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QFrame, QSlider, QSpinBox, QStyle, QSizePolicy, QRubberBand,
)
from .engine import PDFDocument, PDFStudioError, PasswordRequired, SearchHit
from .licensing import LicenseManager, ActivationError
from .license_ui import LicenseDialog
from .dialogs import (TextDialog, ImageDialog, PhraseDialog, WatermarkDialog,
                      MetadataDialog, ProtectDialog)

ASSET_ROOT = Path(__file__).resolve().parent.parent / "assets"

STYLESHEET = """
QMainWindow, QWidget#main, QWidget#titleRow { background: #171e29; color: #eaf0f7; }
QWidget { font-family: 'Segoe UI', 'Arial'; font-size: 12px; }
QWidget#titleRow { background: #101721; }
QLabel#appTitle { font-weight: 800; font-size: 18px; color: white; }
QLabel#tagLine { color: #a4afbd; font-size: 11px; }
QLabel#panelTitle { color: #eaf0f7; font-weight: 700; font-size: 13px; }
QLabel#miniLabel { color: #a2b0c1; font-size: 11px; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: #252f3f; color: #eaf0f7; border: 1px solid #3b4658;
    border-radius: 5px; min-height: 27px; padding: 3px 7px;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: #559feb; }
QTabWidget#ribbonTabs::pane { background: #eef1f6; border: none; }
QTabWidget#ribbonTabs QTabBar { background: #171e29; }
QTabWidget#ribbonTabs QTabBar::tab {
    background: #171e29; color: #d8dfe8; padding: 10px 16px; border: none;
    font-weight: 600; min-width: 50px;
}
QTabWidget#ribbonTabs QTabBar::tab:selected {
    color: #132031; background: #f4f6fa; border-top-left-radius: 5px;
    border-top-right-radius: 5px;
}
QTabWidget#ribbonTabs QTabBar::tab:first { background: #d9232e; color: white; }
QTabWidget#ribbonTabs QTabBar::tab:first:selected { background: #c71924; color: white; }
QWidget#ribbonContent { background: #eef1f6; color: #1c2c3c; }
QToolButton#ribbonButton {
    background: transparent; color: #263545; border: none; border-radius: 5px;
    min-width: 66px; min-height: 66px; padding: 5px; font-weight: 600;
}
QToolButton#ribbonButton:hover { background: #d9e8f8; }
QToolButton#ribbonButton:disabled { color: #9da6b1; }
QTabWidget#documentTabs::pane { border: none; background: #303a49; }
QTabWidget#documentTabs QTabBar::tab {
    padding: 10px 15px; background: #263040; color: #dce5f1;
    margin-right: 2px; border-top-left-radius: 5px; border-top-right-radius: 5px;
}
QTabWidget#documentTabs QTabBar::tab:selected { background: #e8ecf2; color: #101827; }
QWidget#leftPanel, QWidget#rightPanel { background: #232c3a; }
QListWidget#pageList { background: #232c3a; border: none; color: #dae4f1; outline: none; }
QListWidget#pageList::item { border: 1px solid transparent; border-radius: 6px; padding: 6px; }
QListWidget#pageList::item:selected { background: #344254; border: 2px solid #ec3c46; }
QListWidget#pageList::item:hover { background: #344254; }
QScrollArea#canvasScroll { background: #414b5b; border: none; }
QScrollArea#canvasScroll > QWidget > QWidget { background: #414b5b; }
QPushButton#panelButton {
    background: #f0f3f8; color: #1d2a38; border: none;
    border-radius: 7px; font-weight: 600; padding: 11px; text-align: left;
}
QPushButton#panelButton:hover { background: #d8e8fa; }
QPushButton#panelButton:disabled { color: #9198a3; background: #e4e7ed; }
QPushButton#flatButton {
    background: #303c4c; color: #e2e8f0; border: 1px solid #3f4e61;
    border-radius: 5px; padding: 6px 9px;
}
QPushButton#flatButton:hover { background: #43566c; }
QWidget#bottomBar { background: #202a38; color: #e1eaf5; }
QSlider::groove:horizontal { height: 4px; background: #526071; border-radius: 2px; }
QSlider::handle:horizontal { background: #f3f7fd; width: 14px; margin: -5px 0; border-radius: 7px; }
QSplitter::handle { background: #364152; width: 2px; }
QScrollBar:vertical { background: #263242; width: 10px; }
QScrollBar::handle:vertical { background: #758397; border-radius: 5px; min-height: 24px; }
"""


class ThumbnailList(QListWidget):
    order_dropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setObjectName("pageList")
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setIconSize(QSize(102, 132))
        self.setSpacing(4)

    def dropEvent(self, event):
        before = [self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())]
        super().dropEvent(event)
        after = [self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())]
        if after != before:
            self.order_dropped.emit(after)


class RegionPageLabel(QLabel):
    """Mouse-drawn redaction rectangle over the rasterized PDF page."""
    region_drawn = Signal(tuple)

    def __init__(self):
        super().__init__()
        self.region_mode = False
        self._origin = None
        self._rubber = QRubberBand(QRubberBand.Shape.Rectangle, self)

    def mousePressEvent(self, event):
        if self.region_mode and event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.position().toPoint()
            self._rubber.setGeometry(QRect(self._origin, QSize()))
            self._rubber.show()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.region_mode and self._origin is not None:
            self._rubber.setGeometry(QRect(self._origin, event.position().toPoint()).normalized())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.region_mode and self._origin is not None:
            selection = QRect(self._origin, event.position().toPoint()).normalized()
            self._origin = None
            self._rubber.hide()
            self.region_mode = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            if selection.width() >= 5 and selection.height() >= 5:
                self.region_drawn.emit((selection.left(), selection.top(),
                                        selection.right(), selection.bottom()))
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class DocumentView(QWidget):
    region_selected = Signal(tuple)

    def __init__(self, doc: PDFDocument, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.index = 0
        self.zoom = 1.0
        self.matches: list[SearchHit] = []
        self.active_hit = -1
        self.fit_mode = "none"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.scroller = QScrollArea()
        self.scroller.setObjectName("canvasScroll")
        self.scroller.setWidgetResizable(False)
        self.scroller.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_label = RegionPageLabel()
        self.page_label.region_drawn.connect(self._region_to_pdf_coords)
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_label.setStyleSheet("background: white; border: 1px solid #b9c4d3;")
        self.page_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.scroller.setWidget(self.page_label)
        layout.addWidget(self.scroller)
        self.render()

    def render(self):
        if self.doc.page_count == 0:
            return
        pix = self.doc.render(self.index, self.zoom)
        qt_image = QImage(pix.samples, pix.width, pix.height, pix.stride,
                          QImage.Format.Format_RGB888).copy()
        page = self.doc._page(self.index)
        highlights = [(idx, hit) for idx, hit in enumerate(self.matches)
                      if hit.display_index == self.index]
        if highlights:
            painter = QPainter(qt_image)
            painter.setPen(Qt.PenStyle.NoPen)
            sx = qt_image.width() / max(page.rect.width, 1)
            sy = qt_image.height() / max(page.rect.height, 1)
            for match_index, hit in highlights:
                box = fitz_rect(hit.bounds) * page.rotation_matrix
                painter.setBrush(QColor(249, 211, 53, 130) if match_index != self.active_hit
                                 else QColor(244, 106, 40, 160))
                painter.drawRect(QRectF(box.x0 * sx, box.y0 * sy,
                                        box.width * sx, box.height * sy))
            painter.end()
        self.page_label.setPixmap(QPixmap.fromImage(qt_image))
        self.page_label.resize(qt_image.size())

    def _region_to_pdf_coords(self, pixel_bounds: tuple):
        """Convert widget pixels into PDF coordinates, including rotation."""
        page = self.doc._page(self.index)
        rx = page.rect.width / max(self.page_label.width(), 1)
        ry = page.rect.height / max(self.page_label.height(), 1)
        region = fitz_rect((max(0, pixel_bounds[0]*rx), max(0, pixel_bounds[1]*ry),
                            min(page.rect.width, pixel_bounds[2]*rx),
                            min(page.rect.height, pixel_bounds[3]*ry)))
        if region.is_empty:
            return
        # Search and redaction coordinates use an unrotated page frame.
        region = region * page.derotation_matrix
        self.region_selected.emit(tuple(region))

    def activate_region_redaction(self):
        self.page_label.region_mode = True
        self.page_label.setCursor(Qt.CursorShape.CrossCursor)
        self.page_label.setToolTip("Drag to choose the area to permanently redact")

    def set_page(self, index: int):
        self.page_label.region_mode = False
        self.page_label.setCursor(Qt.CursorShape.ArrowCursor)
        if 0 <= index < self.doc.page_count:
            self.index = index
            self.render()
            self.scroller.verticalScrollBar().setValue(0)

    def set_zoom(self, percent: int):
        self.zoom = max(0.25, min(3.0, percent / 100.0))
        self.fit_mode = "none"
        self.render()

    def fit(self, mode: str) -> int:
        width, height = self.doc.page_size(self.index)
        available_width = max(100, self.scroller.viewport().width() - 38)
        available_height = max(100, self.scroller.viewport().height() - 38)
        scale = available_width / max(width, 1)
        if mode == "page":
            scale = min(scale, available_height / max(height, 1))
        percent = int(max(25, min(300, round(scale * 100))))
        self.zoom = percent / 100
        self.fit_mode = mode
        self.render()
        return percent


def fitz_rect(values):
    # Import kept local so the Qt display module depends only on documented
    # engine types; not on mutable page internals.
    import fitz
    return fitz.Rect(values)


class CropDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Crop current PDF page")
        self.setMinimumWidth(350)
        self.setStyleSheet("QDialog { background: #1e2835; color: white; } QLabel { color: white; }")
        outer = QVBoxLayout(self)
        outer.addWidget(QLabel("Enter margins to remove from the visible page (points)."))
        outer.addWidget(QLabel("72 points = 1 inch. Cropping is non-destructive."))
        form = QFormLayout()
        self.fields = {}
        for name in ("Left", "Top", "Right", "Bottom"):
            field = QDoubleSpinBox()
            field.setRange(0.0, 10000.0)
            field.setSuffix(" pt")
            field.setDecimals(1)
            field.setSingleStep(5.0)
            self.fields[name.lower()] = field
            form.addRow(f"{name} margin", field)
        outer.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def values(self) -> tuple[float, float, float, float]:
        return tuple(self.fields[n].value() for n in ("left", "top", "right", "bottom"))


class LicenseSignals(QObject):
    validation_finished = Signal(bool, str)


class MainWindow(QMainWindow):
    def __init__(self, license_manager: LicenseManager | None = None):
        super().__init__()
        self.license_manager = license_manager
        self._license_busy = False
        self.setWindowTitle("PDF Studio Pro — v1.0")
        self.resize(1430, 850)
        self.setMinimumSize(950, 610)
        self.setAcceptDrops(True)
        self.setStyleSheet(STYLESHEET)
        self.setWindowIcon(QIcon(str(ASSET_ROOT / "pdfstudio-icon.png")))
        self._syncing_pages = False
        self._syncing_zoom = False
        self._actions: dict[str, QAction] = {}
        self._build_ui()
        self._register_shortcuts()
        self._sync_document()
        if self.license_manager:
            self._license_signals = LicenseSignals(self)
            self._license_signals.validation_finished.connect(self._license_checked)
            self._license_timer = QTimer(self)
            self._license_timer.setInterval(10 * 60 * 1000)
            self._license_timer.timeout.connect(self._background_license_check)
            self._license_timer.start()

    def _background_license_check(self):
        if self._license_busy or self.license_manager is None:
            return
        self._license_busy = True
        def verify():
            try:
                self.license_manager.verify()
                self._license_signals.validation_finished.emit(True, '')
            except Exception as exc:
                self._license_signals.validation_finished.emit(False, str(exc))
        threading.Thread(target=verify, name='LicenseVerification', daemon=True).start()

    def _license_checked(self, valid: bool, reason: str):
        self._license_busy = False
        if not valid:
            self._license_timer.stop()
            QMessageBox.critical(self, 'License verification failed',
                reason + '\n\nThe editor will close. Reconnect to the license server or contact the administrator.')
            QApplication.instance().quit()

    def _build_ui(self):
        body = QWidget()
        body.setObjectName("main")
        self.setCentralWidget(body)
        root = QVBoxLayout(body)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setObjectName("titleRow")
        title_layout = QHBoxLayout(header)
        title_layout.setContentsMargins(15, 7, 14, 7)
        icon = QLabel()
        icon.setPixmap(QPixmap(str(ASSET_ROOT / "pdfstudio-icon.png")).scaled(
            39, 39, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        title_layout.addWidget(icon)
        title = QLabel("PDF Studio Pro")
        title.setObjectName("appTitle")
        title_layout.addWidget(title)
        tagline = QLabel("Professional PDF Editor & Reader  |  v1.0")
        tagline.setObjectName("tagLine")
        title_layout.addWidget(tagline)
        title_layout.addStretch(1)
        if self.license_manager:
            lic_label = QLabel('◆ Lifetime License')
            lic_label.setStyleSheet('color:#93e0b0;font-size:11px;padding:4px;')
            lic_label.setToolTip('Online verified, one registered Windows PC')
            title_layout.addWidget(lic_label)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search text in document  (Ctrl+F)")
        self.search_input.setToolTip("Search for text in the active PDF")
        self.search_input.setMinimumWidth(240)
        self.search_input.setMaximumWidth(315)
        self.search_input.returnPressed.connect(self.find_text)
        title_layout.addWidget(self.search_input)
        search_next = QPushButton("Next  ↵")
        search_next.setObjectName("flatButton")
        search_next.clicked.connect(self.next_result)
        title_layout.addWidget(search_next)
        root.addWidget(header)

        self.ribbon = QTabWidget()
        self.ribbon.setObjectName("ribbonTabs")
        self.ribbon.setDocumentMode(True)
        self.ribbon.setFixedHeight(128)
        for tab in ("File", "Home", "Edit", "Comment", "Convert", "Organize", "Forms", "Protect", "OCR", "Tools"):
            self.ribbon.addTab(self._ribbon_page(tab), tab)
        self.ribbon.setCurrentIndex(1)
        root.addWidget(self.ribbon)

        horizontal = QSplitter(Qt.Orientation.Horizontal)
        horizontal.setChildrenCollapsible(False)
        self.left_panel = QWidget()
        self.left_panel.setObjectName("leftPanel")
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(10, 11, 8, 8)
        label_row = QHBoxLayout()
        label = QLabel("Pages")
        label.setObjectName("panelTitle")
        label_row.addWidget(label)
        label_row.addStretch()
        self.btn_move_up = self._flat_button("↑", self.move_up, "Move page up")
        self.btn_move_down = self._flat_button("↓", self.move_down, "Move page down")
        label_row.addWidget(self.btn_move_up)
        label_row.addWidget(self.btn_move_down)
        left_layout.addLayout(label_row)
        help_label = QLabel("Drag thumbnails to reorder pages")
        help_label.setObjectName("miniLabel")
        help_label.setWordWrap(True)
        left_layout.addWidget(help_label)
        self.thumbnails = ThumbnailList()
        self.thumbnails.currentRowChanged.connect(self._thumbnail_selected)
        self.thumbnails.order_dropped.connect(self._pages_reordered)
        left_layout.addWidget(self.thumbnails)
        horizontal.addWidget(self.left_panel)

        self.doc_tabs = QTabWidget()
        self.doc_tabs.setObjectName("documentTabs")
        self.doc_tabs.setTabsClosable(True)
        self.doc_tabs.setMovable(True)
        self.doc_tabs.tabCloseRequested.connect(self.close_tab)
        self.doc_tabs.currentChanged.connect(self._sync_document)
        self.doc_tabs.setStyleSheet(self.doc_tabs.styleSheet())
        horizontal.addWidget(self.doc_tabs)

        self.right_panel = QWidget()
        self.right_panel.setObjectName("rightPanel")
        panel_root = QVBoxLayout(self.right_panel)
        panel_root.setContentsMargins(9, 12, 9, 10)
        header_tools = QLabel("PDF Tools")
        header_tools.setObjectName("panelTitle")
        panel_root.addWidget(header_tools)
        tools_scroll = QScrollArea()
        tools_scroll.setWidgetResizable(True)
        tools_scroll.setFrameShape(QFrame.Shape.NoFrame)
        tools_scroll.setStyleSheet("QScrollArea { background: #232c3a; border: none; }")
        tools_container = QWidget()
        tools_container.setStyleSheet("background: #232c3a;")
        right = QVBoxLayout(tools_container)
        right.setContentsMargins(0, 7, 0, 5)
        right.setSpacing(6)
        for icon_text, title, caption, callback, enabled in (
            ("▣", "Organize Pages", "Drag, move, undo or redo", self.focus_pages, True),
            ("▧", "Crop PDF", "Trim visible page margins", self.crop_page, True),
            ("◩", "Convert PDF", "Export pages to PNG", self.export_png, True),
            ("▧", "Images to PDF", "Build PDF from image files", self.images_to_pdf, True),
            ("⌕", "Find Text", "Search / next result", self.focus_search, True),
            ("✎", "Add Text", "Insert editable document text", self.add_text, True),
            ("◧", "Highlight Text", "Mark matching phrases", self.highlight_text, True),
            ("▣", "Redact Text", "Permanently remove matches", self.redact_text, True),
            ("▨", "Redact Region", "Draw area to permanently remove", self.redact_region, True),
            ("▧", "Insert Image", "Place pictures on PDF pages", self.insert_image, True),
            ("W", "Watermark", "Transparent text watermark", self.add_watermark, True),
            ("≡", "Edit Metadata", "Title, author, subject, keywords", self.edit_metadata, True),
            ("▣", "Compress PDF", "Lossless optimized Save As", self.compress_pdf, True),
            ("◆", "Protect PDF", "AES-256 password encryption", self.protect_pdf, True),
            ("♢", "OCR & Forms", "Future phase, not included", None, False),
        ):
            button = QPushButton(f"{icon_text}   {title}\n      {caption}")
            button.setObjectName("panelButton")
            button.setMinimumHeight(54)
            button.setToolTip(caption)
            if callback:
                button.clicked.connect(callback)
            button.setEnabled(enabled)
            right.addWidget(button)
        right.addStretch()
        tools_scroll.setWidget(tools_container)
        panel_root.addWidget(tools_scroll)
        horizontal.addWidget(self.right_panel)
        horizontal.setSizes([218, 950, 255])
        horizontal.setStretchFactor(0, 0)
        horizontal.setStretchFactor(1, 1)
        horizontal.setStretchFactor(2, 0)
        root.addWidget(horizontal, 1)

        bottom = QWidget()
        bottom.setObjectName("bottomBar")
        status = QHBoxLayout(bottom)
        status.setContentsMargins(13, 6, 13, 6)
        self.status_text = QLabel("Ready — Open a PDF or create one from images")
        self.status_text.setObjectName("miniLabel")
        status.addWidget(self.status_text)
        status.addStretch()
        status.addWidget(self._flat_button("◀", self.previous_page, "Previous page"))
        self.page_spin = QSpinBox()
        self.page_spin.setRange(0, 0)
        self.page_spin.setFixedWidth(65)
        self.page_spin.valueChanged.connect(self._go_to_page)
        status.addWidget(self.page_spin)
        self.page_total = QLabel("/ 0")
        status.addWidget(self.page_total)
        status.addWidget(self._flat_button("▶", self.next_page, "Next page"))
        status.addSpacing(15)
        status.addWidget(self._flat_button("Fit page", self.fit_page))
        status.addWidget(self._flat_button("Fit width", self.fit_width))
        status.addWidget(self._flat_button("−", self.zoom_out))
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(25, 300)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(130)
        self.zoom_slider.valueChanged.connect(self._zoom_changed)
        status.addWidget(self.zoom_slider)
        status.addWidget(self._flat_button("+", self.zoom_in))
        self.zoom_spin = QSpinBox()
        self.zoom_spin.setRange(25, 300)
        self.zoom_spin.setSuffix("%")
        self.zoom_spin.setValue(100)
        self.zoom_spin.setFixedWidth(76)
        self.zoom_spin.valueChanged.connect(self._zoom_changed)
        status.addWidget(self.zoom_spin)
        root.addWidget(bottom)

    def _ribbon_page(self, name: str) -> QWidget:
        page = QWidget()
        page.setObjectName("ribbonContent")
        line = QHBoxLayout(page)
        line.setContentsMargins(12, 4, 12, 4)
        line.setSpacing(4)
        configs = {
            "File": [
                ("Open", "📂", self.open_file), ("Images → PDF", "▧", self.images_to_pdf),
                ("Save", "▣", self.save_file), ("Save As", "▤", self.save_as),
                ("Metadata", "≡", self.edit_metadata),
            ],
            "Home": [
                ("Open", "📂", self.open_file), ("Images → PDF", "▧", self.images_to_pdf),
                ("Save", "▣", self.save_file), ("Prev", "‹", self.previous_page),
                ("Next", "›", self.next_page), ("Find", "⌕", self.focus_search),
                ("Zoom −", "⊖", self.zoom_out), ("Zoom +", "⊕", self.zoom_in),
                ("Fit Page", "▣", self.fit_page), ("Fit Width", "↔", self.fit_width),
            ],
            "Edit": [("Add Text", "T", self.add_text), ("Insert Image", "▧", self.insert_image),
                     ("Watermark", "W", self.add_watermark), ("Metadata", "≡", self.edit_metadata),
                     ("Crop", "▧", self.crop_page), ("Undo Order", "↶", self.undo_order),
                     ("Redo Order", "↷", self.redo_order)],
            "Comment": [("Highlight", "▧", self.highlight_text),
                        ("Redact Text", "▣", self.redact_text),
                        ("Redact Region", "▨", self.redact_region)],
            "Convert": [("PDF → PNG", "▧", self.export_png),
                        ("Images → PDF", "▤", self.images_to_pdf),
                        ("Compress", "≡", self.compress_pdf)],
            "Organize": [("Pages", "▤", self.focus_pages), ("Move Up", "↑", self.move_up),
                         ("Move Down", "↓", self.move_down), ("Crop", "▧", self.crop_page),
                         ("Undo Order", "↶", self.undo_order), ("Redo Order", "↷", self.redo_order)],
            "Forms": [("Forms — Future", "▤", None)],
            "Protect": [("Password", "▣", self.protect_pdf),
                        ("AES-256", "◈", self.protect_pdf),
                        ("Redact Text", "▨", self.redact_text),
                        ("Redact Region", "▣", self.redact_region)],
            "OCR": [("OCR — Future", "⌕", None)],
            "Tools": [("Search Text", "⌕", self.focus_search),
                      ("Export PNG", "▣", self.export_png),
                      ("Compress", "▥", self.compress_pdf),
                      ("Metadata", "≡", self.edit_metadata),
                      ("About", "ⓘ", self.show_about)],
        }
        for label, glyph, callback in configs[name]:
            btn = QToolButton()
            btn.setObjectName("ribbonButton")
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setIcon(self._tool_icon(glyph))
            btn.setIconSize(QSize(25, 25))
            btn.setText(label)
            if callback:
                btn.clicked.connect(callback)
            else:
                btn.setEnabled(False)
                btn.setToolTip("Not included in the approved feature scope")
            line.addWidget(btn)
        line.addStretch(1)
        return page

    @staticmethod
    def _tool_icon(glyph: str) -> QIcon:
        from PySide6.QtGui import QFont
        pix = QPixmap(40, 40)
        pix.fill(Qt.GlobalColor.transparent)
        paint = QPainter(pix)
        paint.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint.setPen(QColor("#c91f2b") if glyph in ("📂", "▧", "⊕") else QColor("#2675b9"))
        font = QFont("Segoe UI Symbol", 22)
        paint.setFont(font)
        paint.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, glyph)
        paint.end()
        return QIcon(pix)

    def _flat_button(self, label: str, callback, tooltip: str = "") -> QPushButton:
        btn = QPushButton(label)
        btn.setObjectName("flatButton")
        btn.setToolTip(tooltip)
        btn.clicked.connect(callback)
        return btn

    def _register_shortcuts(self):
        bindings = {
            "open": ("Ctrl+O", self.open_file),
            "save": ("Ctrl+S", self.save_file),
            "save_as": ("Ctrl+Shift+S", self.save_as),
            "undo": ("Ctrl+Z", self.undo_order),
            "redo": ("Ctrl+Y", self.redo_order),
            "find": ("Ctrl+F", self.focus_search),
            "next_find": ("F3", self.next_result),
            "prev": ("PgUp", self.previous_page),
            "next": ("PgDown", self.next_page),
            "zoom_in": ("Ctrl++", self.zoom_in),
            "zoom_out": ("Ctrl+-", self.zoom_out),
            "fit_width": ("Ctrl+0", self.fit_width),
            "export": ("Ctrl+E", self.export_png),
            "images": ("Ctrl+I", self.images_to_pdf),
            "crop": ("Ctrl+Shift+C", self.crop_page),
            "text": ("Ctrl+Shift+T", self.add_text),
            "highlight": ("Ctrl+Shift+H", self.highlight_text),
            "redact": ("Ctrl+Shift+R", self.redact_text),
            "protect": ("Ctrl+Shift+P", self.protect_pdf),
        }
        for name, (sequence, callback) in bindings.items():
            action = QAction(self)
            action.setShortcut(QKeySequence(sequence))
            action.triggered.connect(callback)
            self.addAction(action)
            self._actions[name] = action

    def active(self) -> DocumentView | None:
        tab = self.doc_tabs.currentWidget()
        return tab if isinstance(tab, DocumentView) else None

    def _error(self, title: str, exc: Exception):
        QMessageBox.critical(self, title, str(exc))

    def open_file(self, filename: str | None = None):
        if not isinstance(filename, str):
            filename = QFileDialog.getOpenFileName(self, "Open PDF", "", "PDF documents (*.pdf)")[0]
        if not filename:
            return
        try:
            try:
                doc = PDFDocument.open(filename)
            except PasswordRequired:
                password, ok = QInputDialog.getText(self, "Password required",
                                                     "Enter the PDF password:",
                                                     QLineEdit.EchoMode.Password)
                if not ok:
                    return
                doc = PDFDocument.open(filename, password=password)
            self._add_document(doc)
        except PDFStudioError as exc:
            self._error("Could not open PDF", exc)

    def _add_document(self, doc: PDFDocument):
        view = DocumentView(doc)
        view.region_selected.connect(lambda bounds, v=view: self._redact_selected_region(v, bounds))
        index = self.doc_tabs.addTab(view, doc.title)
        self.doc_tabs.setCurrentIndex(index)
        self._sync_document()

    def images_to_pdf(self):
        paths = QFileDialog.getOpenFileNames(
            self, "Choose images to convert", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff)")[0]
        if not paths:
            return
        try:
            self._add_document(PDFDocument.from_images(paths))
            self.status_text.setText(f"Created {len(paths)}-page PDF from images. Save to keep it.")
        except PDFStudioError as exc:
            self._error("Could not create PDF", exc)

    def _sync_document(self, *_):
        view = self.active()
        if view is None:
            self._syncing_pages = True
            self.thumbnails.clear()
            self._syncing_pages = False
            self.page_spin.setRange(0, 0)
            self.page_total.setText("/ 0")
            self.status_text.setText("Ready — Open a PDF or create one from images")
            return
        self.refresh_thumbnails()
        self._update_status()
        self._sync_zoom(view.zoom)

    def refresh_thumbnails(self, selected: int | None = None):
        view = self.active()
        if view is None:
            return
        if selected is None:
            selected = view.index
        self._syncing_pages = True
        self.thumbnails.blockSignals(True)
        self.thumbnails.clear()
        for i in range(view.doc.page_count):
            try:
                pix = view.doc.render(i, 0.20)
                qimage = QImage(pix.samples, pix.width, pix.height, pix.stride,
                                QImage.Format.Format_RGB888).copy()
                icon = QIcon(QPixmap.fromImage(qimage).scaled(
                    98, 125, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
                item = QListWidgetItem(icon, f"Page {i+1}")
            except Exception:
                item = QListWidgetItem(f"Page {i+1}")
            item.setData(Qt.ItemDataRole.UserRole, view.doc.order[i])
            item.setSizeHint(QSize(126, 155))
            self.thumbnails.addItem(item)
        self.thumbnails.setCurrentRow(min(max(selected, 0), view.doc.page_count - 1))
        self.thumbnails.blockSignals(False)
        self._syncing_pages = False
        self._update_status()

    def _thumbnail_selected(self, index: int):
        if self._syncing_pages or index < 0:
            return
        view = self.active()
        if view and index < view.doc.page_count:
            view.set_page(index)
            self._update_status()

    def _pages_reordered(self, order: list[int]):
        view = self.active()
        if not view:
            return
        try:
            previously_selected = view.doc.order[view.index]
            if view.doc.set_order(order):
                view.index = view.doc.order.index(previously_selected)
                view.matches = []
                view.active_hit = -1
                view.render()
                self.refresh_thumbnails()
                self._update_tab_title(view)
                self.status_text.setText("Page order updated. Ctrl+Z to undo.")
        except PDFStudioError as exc:
            self._error("Cannot reorder pages", exc)
            self.refresh_thumbnails()

    def move_up(self):
        self._move_selected(-1)

    def move_down(self):
        self._move_selected(1)

    def _move_selected(self, delta: int):
        view = self.active()
        if not view:
            return
        old = view.index
        new = old + delta
        try:
            changed = 0 <= new < view.doc.page_count and view.doc.move_page(old, new)
        except PDFStudioError as exc:
            self._error("Move page failed", exc)
            return
        if changed:
            view.index = new
            view.matches = []
            view.active_hit = -1
            view.render()
            self.refresh_thumbnails(new)
            self._update_tab_title(view)

    def undo_order(self):
        self._history_change("undo_order")

    def redo_order(self):
        self._history_change("redo_order")

    def _history_change(self, method: str):
        view = self.active()
        if not view:
            return
        original_page = view.doc.order[view.index]
        try:
            changed = getattr(view.doc, method)()
        except PDFStudioError as exc:
            self._error("Page order", exc)
            return
        if changed:
            view.index = view.doc.order.index(original_page)
            view.matches = []
            view.active_hit = -1
            view.render()
            self.refresh_thumbnails()
            self._update_tab_title(view)

    def _go_to_page(self, page_num: int):
        view = self.active()
        if view and 1 <= page_num <= view.doc.page_count:
            view.set_page(page_num - 1)
            with QSignalBlocker(self.thumbnails):
                self.thumbnails.setCurrentRow(view.index)
            self._update_status()

    def _set_page(self, new_index: int):
        view = self.active()
        if view and 0 <= new_index < view.doc.page_count:
            view.set_page(new_index)
            with QSignalBlocker(self.thumbnails):
                self.thumbnails.setCurrentRow(new_index)
            self._update_status()

    def previous_page(self):
        view = self.active()
        if view:
            self._set_page(view.index - 1)

    def next_page(self):
        view = self.active()
        if view:
            self._set_page(view.index + 1)

    def _update_status(self):
        view = self.active()
        if not view:
            return
        with QSignalBlocker(self.page_spin):
            self.page_spin.setRange(1, max(1, view.doc.page_count))
            self.page_spin.setValue(view.index + 1)
        self.page_total.setText(f"/ {view.doc.page_count}")
        suffix = "  •  Unsaved changes" if view.doc.dirty else ""
        self.status_text.setText(f"{view.doc.title}  •  {view.doc.page_count} pages{suffix}")

    def _update_tab_title(self, view: DocumentView):
        index = self.doc_tabs.indexOf(view)
        if index >= 0:
            self.doc_tabs.setTabText(index, view.doc.title + (" *" if view.doc.dirty else ""))
        self._update_status()

    def _sync_zoom(self, factor: float):
        value = int(round(factor * 100))
        with QSignalBlocker(self.zoom_spin), QSignalBlocker(self.zoom_slider):
            self.zoom_spin.setValue(value)
            self.zoom_slider.setValue(value)

    def _zoom_changed(self, value: int):
        view = self.active()
        if view:
            view.set_zoom(value)
            self._sync_zoom(view.zoom)

    def zoom_in(self):
        view = self.active()
        if view:
            self._zoom_changed(min(300, int(view.zoom * 100) + 25))

    def zoom_out(self):
        view = self.active()
        if view:
            self._zoom_changed(max(25, int(view.zoom * 100) - 25))

    def fit_page(self):
        view = self.active()
        if view:
            self._sync_zoom(view.fit("page") / 100)

    def fit_width(self):
        view = self.active()
        if view:
            self._sync_zoom(view.fit("width") / 100)

    def focus_pages(self):
        self.thumbnails.setFocus()

    def focus_search(self):
        self.search_input.setFocus()
        self.search_input.selectAll()

    def find_text(self):
        view = self.active()
        if not view:
            return
        needle = self.search_input.text().strip()
        if not needle:
            view.matches = []
            view.active_hit = -1
            view.render()
            return
        try:
            view.matches = view.doc.search(needle)
            view.active_hit = -1
            if view.matches:
                self.next_result()
                self.status_text.setText(f"Found {len(view.matches)} match(es) for '{needle}'")
            else:
                view.render()
                self.status_text.setText(f"No matches for '{needle}' (scanned PDFs need OCR)")
        except PDFStudioError as exc:
            self._error("Search failed", exc)

    def next_result(self):
        view = self.active()
        if not view:
            return
        if not view.matches:
            self.find_text()
            return
        view.active_hit = (view.active_hit + 1) % len(view.matches)
        hit = view.matches[view.active_hit]
        self._set_page(hit.display_index)
        view.render()
        self.status_text.setText(f"Match {view.active_hit+1} of {len(view.matches)}")

    def crop_page(self):
        view = self.active()
        if not view:
            return
        dialog = CropDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                margins = dialog.values()
                if any(margins):
                    view.doc.crop_margins(view.index, *margins)
                    view.matches = []
                    view.active_hit = -1
                    view.render()
                    self.refresh_thumbnails()
                    self._update_tab_title(view)
                    self.status_text.setText("Cropped current page. Save PDF to keep the change.")
            except PDFStudioError as exc:
                self._error("Crop failed", exc)

    def _after_edit(self, view: DocumentView, message: str, update_thumbnails: bool = True):
        view.matches = []
        view.active_hit = -1
        view.render()
        if update_thumbnails:
            self.refresh_thumbnails()
        self._update_tab_title(view)
        self.status_text.setText(message + "  |  Save to keep changes")

    def add_text(self):
        view = self.active()
        if view is None:
            return
        dialog = TextDialog(view.doc.edit_page_size(view.index), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            view.doc.add_text(view.index, **dialog.values())
            self._after_edit(view, "Text added")
        except PDFStudioError as exc:
            self._error("Insert text failed", exc)

    def highlight_text(self):
        view = self.active()
        if view is None:
            return
        dialog = PhraseDialog("Highlight", self)
        dialog.text.setText(self.search_input.text())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            count = view.doc.highlight_text(view.index, dialog.text.text(),
                                            all_pages=dialog.scope.isChecked())
            if count:
                self._after_edit(view, f"Created {count} highlight annotation(s)")
            else:
                QMessageBox.information(self, "No matches", "No matching searchable text found.")
        except PDFStudioError as exc:
            self._error("Highlight failed", exc)

    def redact_text(self):
        view = self.active()
        if view is None:
            return
        dialog = PhraseDialog("Permanently redact", self)
        dialog.text.setText(self.search_input.text())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        phrase = dialog.text.text().strip()
        if not phrase:
            self._error("Redaction failed", PDFStudioError("Enter a phrase to redact."))
            return
        try:
            candidates = view.doc.search(phrase)
            if not dialog.scope.isChecked():
                candidates = [h for h in candidates if h.display_index == view.index]
            if not candidates:
                QMessageBox.information(self, "No matches", "No matching searchable text found.")
                return
            confirmation = QMessageBox.warning(
                self, "Permanent content removal",
                f"Remove {len(candidates)} matching text occurrence(s) and any overlapping images?\n"
                "This changes the working PDF immediately. It cannot be undone.\n"
                "Save As to preserve your original document.\n\nContinue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if confirmation != QMessageBox.StandardButton.Yes:
                return
            count = view.doc.redact_text(view.index, phrase,
                                         all_pages=dialog.scope.isChecked())
            self._after_edit(view, f"Permanently redacted {count} match(es)")
        except PDFStudioError as exc:
            self._error("Redaction failed", exc)

    def redact_region(self):
        view = self.active()
        if view is None:
            return
        if not view.doc.can_edit:
            self._error("Redaction unavailable", PDFStudioError(
                "Reopen this protected document using the owner password."))
            return
        view.activate_region_redaction()
        self.status_text.setText("Drag a rectangle over the PDF page to permanently redact that region")

    def _redact_selected_region(self, view: DocumentView, bounds: tuple):
        if self.active() is not view:
            return
        answer = QMessageBox.warning(self, "Permanently redact region",
                                     "Delete all content (including images) intersecting the selected area?\n"
                                     "This operation cannot be undone.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            view.doc.redact_region(view.index, bounds)
            self._after_edit(view, "Selected region permanently redacted")
        except PDFStudioError as exc:
            self._error("Region redaction failed", exc)

    def insert_image(self):
        view = self.active()
        if view is None:
            return
        filename = QFileDialog.getOpenFileName(self, "Select image", "",
                                               "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp)")[0]
        if not filename:
            return
        dialog = ImageDialog(view.doc.edit_page_size(view.index), filename, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            view.doc.insert_image(view.index, filename, **dialog.values())
            self._after_edit(view, "Image inserted")
        except PDFStudioError as exc:
            self._error("Insert image failed", exc)

    def add_watermark(self):
        view = self.active()
        if view is None:
            return
        dialog = WatermarkDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            count = view.doc.add_watermark(display_index=view.index, **dialog.values())
            self._after_edit(view, f"Watermark added to {count} page(s)")
        except PDFStudioError as exc:
            self._error("Watermark failed", exc)

    def edit_metadata(self):
        view = self.active()
        if view is None:
            return
        dialog = MetadataDialog(view.doc.metadata, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            view.doc.edit_metadata(dialog.values())
            self._after_edit(view, "Document metadata updated", update_thumbnails=False)
        except PDFStudioError as exc:
            self._error("Metadata failed", exc)

    def protect_pdf(self):
        view = self.active()
        if view is None:
            return
        dialog = ProtectDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            view.doc.protect(*dialog.values())
            self._after_edit(view, "AES-256 configured; save the document to encrypt it",
                             update_thumbnails=False)
        except PDFStudioError as exc:
            self._error("Password protection failed", exc)

    def compress_pdf(self):
        view = self.active()
        if view is None:
            return
        filename = QFileDialog.getSaveFileName(
            self, "Save optimized PDF", "optimized.pdf", "PDF documents (*.pdf)")[0]
        if not filename:
            return
        if not filename.lower().endswith(".pdf"):
            filename += ".pdf"
        try:
            original = view.doc.path.stat().st_size if view.doc.path and view.doc.path.exists() else None
            view.doc.enable_compression()
            if not self._save_view(view, False, override_filename=filename):
                return
            result_size = Path(filename).stat().st_size
            report = (f"Optimized PDF saved ({result_size:,} bytes)."
                      if original is None else
                      f"Original {original:,} bytes → optimized {result_size:,} bytes "
                      f"({((original - result_size)/original*100) if original else 0:+.1f}% reduction).")
            QMessageBox.information(self, "Compression complete", report +
                                    "\nLossless optimization may not reduce every PDF.")
        except (PDFStudioError, OSError) as exc:
            self._error("Compression failed", exc)

    def export_png(self):
        view = self.active()
        if not view:
            return
        choice = QMessageBox.question(self, "Export PDF to PNG",
                                      "Export all pages?\nYes: all pages   No: current page",
                                      QMessageBox.StandardButton.Yes |
                                      QMessageBox.StandardButton.No |
                                      QMessageBox.StandardButton.Cancel)
        if choice == QMessageBox.StandardButton.Cancel:
            return
        all_pages = choice == QMessageBox.StandardButton.Yes
        dpi, ok = QInputDialog.getInt(self, "PNG quality", "Resolution (DPI)", 150, 36, 600, 1)
        if not ok:
            return
        folder = QFileDialog.getExistingDirectory(self, "Choose output directory")
        if not folder:
            return
        try:
            pages = range(view.doc.page_count) if all_pages else [view.index]
            stem = (view.doc.path.stem if view.doc.path else "images")
            for i in pages:
                view.doc.export_png(i, Path(folder) / f"{stem}-page-{i+1:03d}.png", dpi)
            QMessageBox.information(self, "PNG export complete", f"Exported {len(pages)} PNG file(s).")
        except PDFStudioError as exc:
            self._error("Export failed", exc)

    def save_file(self):
        view = self.active()
        if view:
            self._save_view(view, force_dialog=view.doc.path is None)

    def save_as(self):
        view = self.active()
        if view:
            self._save_view(view, force_dialog=True)

    def _save_view(self, view: DocumentView, force_dialog: bool,
                   override_filename: str | None = None) -> bool:
        filename = override_filename if override_filename is not None else (str(view.doc.path) if view.doc.path else "")
        if override_filename is None and (force_dialog or not filename):
            filename = QFileDialog.getSaveFileName(self, "Save PDF", filename or "document.pdf",
                                                    "PDF documents (*.pdf)")[0]
        if not filename:
            return False
        if not filename.lower().endswith(".pdf"):
            filename += ".pdf"
        try:
            view.doc.save(filename)
            view.index = min(view.index, view.doc.page_count - 1)
            view.render()
            self.refresh_thumbnails()
            self._update_tab_title(view)
            self.status_text.setText(f"Saved: {filename}")
            return True
        except PDFStudioError as exc:
            self._error("Save failed", exc)
            return False

    def close_tab(self, index: int):
        view = self.doc_tabs.widget(index)
        if not isinstance(view, DocumentView):
            return
        if view.doc.dirty:
            choice = QMessageBox.warning(self, "Unsaved changes",
                                         f"Save changes to {view.doc.title}?",
                                         QMessageBox.StandardButton.Save |
                                         QMessageBox.StandardButton.Discard |
                                         QMessageBox.StandardButton.Cancel)
            if choice == QMessageBox.StandardButton.Cancel:
                return False
            if choice == QMessageBox.StandardButton.Save and not self._save_view(view, view.doc.path is None):
                return False
        self.doc_tabs.removeTab(index)
        view.doc.close()
        view.deleteLater()
        self._sync_document()
        return True

    def closeEvent(self, event):
        while self.doc_tabs.count():
            if not self.close_tab(0):
                event.ignore()
                return
        event.accept()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(u.toLocalFile().lower().endswith(".pdf")
                                               for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".pdf"):
                self.open_file(path)
        event.acceptProposedAction()

    def show_about(self):
        QMessageBox.about(self, "About PDF Studio Pro",
                          "PDF Studio Pro — Part 3 (v1.0)\n\n"
                          "Viewer, page management, editing, true redaction,\n"
                          "lossless compression and AES-256 protection.\n"
                          "Designed with PySide6 + PyMuPDF.\n\n"
                          "Online lifetime licensing, one PC, Windows portable and installer builds.")


def run_app():
    app = QApplication(sys.argv)
    app.setApplicationName("PDF Studio Pro")
    app.setOrganizationName("PDF Studio Pro")
    app.setWindowIcon(QIcon(str(ASSET_ROOT / "pdfstudio-icon.png")))
    try:
        manager = LicenseManager()
    except ActivationError as exc:
        QMessageBox.critical(None, 'License configuration',
                             str(exc) + "\n\nContact the administrator to configure a license server.")
        return 2
    try:
        manager.verify()   # Online verification is mandatory on every launch.
    except ActivationError as exc:
        dialog = LicenseDialog(manager, str(exc))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return 1
    window = MainWindow(license_manager=manager)
    window.show()
    for filename in sys.argv[1:]:
        if filename.lower().endswith(".pdf"):
            window.open_file(filename)
    return app.exec()
