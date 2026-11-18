"""Run Qt initialization without showing a window when PySide6 is installed."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication
from pdfstudio.ui import MainWindow


def test_window_opens_and_tabs_exist():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    assert window.ribbon.count() == 10
    assert window.doc_tabs.count() == 0
    assert window.windowTitle().startswith("PDF Studio Pro")
    window.close()


def test_ui_open_reorder_and_save(tmp_path):
    import fitz
    source = tmp_path / "ui_input.pdf"
    with fitz.open() as doc:
        for label in ("First", "Second", "Third"):
            doc.new_page().insert_text((72, 72), label)
        doc.save(source)
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.open_file(str(source))
    assert window.doc_tabs.count() == 1
    assert window.thumbnails.count() == 3
    view = window.active()
    assert view is not None
    window._pages_reordered([2, 0, 1])
    assert view.doc.order == [2, 0, 1]
    window.undo_order()
    assert view.doc.order == [0, 1, 2]
    window.redo_order()
    assert view.doc.order == [2, 0, 1]
    assert window._save_view(view, False)
    with fitz.open(source) as verified:
        assert "Third" in verified[0].get_text()
    window.close()


def test_part2_dialogs_and_edit_ribbons():
    from PySide6.QtWidgets import QTabWidget
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    assert window.ribbon.tabText(2) == "Edit"
    assert window.ribbon.tabText(3) == "Comment"
    assert window.ribbon.tabText(7) == "Protect"
    for action in ("text", "highlight", "redact", "protect"):
        assert action in window._actions
    assert window.windowTitle().endswith("Part 2")
    window.close()
