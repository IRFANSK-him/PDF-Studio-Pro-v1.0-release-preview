"""Integration-level engine tests; use real PDFs, not mocked page operations."""
from __future__ import annotations

from pathlib import Path
import pytest
import fitz
from PIL import Image

from pdfstudio.engine import PDFDocument, PDFStudioError, PasswordRequired


@pytest.fixture
def input_pdf(tmp_path: Path) -> Path:
    filename = tmp_path / "original.pdf"
    pdf = fitz.open()
    for index, label in enumerate(("Alpha unique", "Beta unique", "Gamma unique")):
        page = pdf.new_page(width=595, height=842)
        page.insert_text((70, 90), label, fontsize=16)
        page.insert_text((70, 130), "Recurring Keyword", fontsize=12)
    pdf.save(filename)
    pdf.close()
    return filename


def test_open_render_search_and_navigation(input_pdf):
    doc = PDFDocument.open(input_pdf)
    try:
        assert doc.page_count == 3
        assert doc.page_size(0) == pytest.approx((595, 842))
        assert doc.render(0, 1.0).width == 595
        assert len(doc.search("Recurring Keyword")) == 3
        assert [hit.display_index for hit in doc.search("Gamma unique")] == [2]
        assert doc.search("missing") == []
        assert doc.dirty is False
    finally:
        doc.close()


def test_reorder_undo_redo_and_saved_pages(input_pdf, tmp_path):
    doc = PDFDocument.open(input_pdf)
    try:
        assert doc.move_page(2, 0)
        assert doc.order == [2, 0, 1]
        assert doc.dirty
        assert doc.undo_order() and doc.order == [0, 1, 2]
        assert doc.redo_order() and doc.order == [2, 0, 1]
        assert [hit.display_index for hit in doc.search("Gamma unique")] == [0]
        out = doc.save(tmp_path / "reordered.pdf")
        assert not doc.dirty
        assert doc.order == [0, 1, 2]
        assert not doc.can_undo_order
        with fitz.open(out) as check:
            assert "Gamma unique" in check[0].get_text()
            assert "Alpha unique" in check[1].get_text()
            assert "Beta unique" in check[2].get_text()
    finally:
        doc.close()


def test_crop_and_save_to_same_source_file(input_pdf):
    doc = PDFDocument.open(input_pdf)
    try:
        width, height = doc.crop_margins(0, 10, 20, 30, 40)
        assert width == pytest.approx(555)
        assert height == pytest.approx(782)
        assert doc.dirty
        doc.save(input_pdf)
        assert not doc.dirty
        assert doc.page_size(0) == pytest.approx((555, 782))
        with fitz.open(input_pdf) as check:
            assert check[0].rect.width == pytest.approx(555)
            assert check[1].rect.width == pytest.approx(595)
    finally:
        doc.close()


def test_export_png(input_pdf, tmp_path):
    doc = PDFDocument.open(input_pdf)
    try:
        path = doc.export_png(1, tmp_path / "png" / "page.png", dpi=72)
        assert path.is_file()
        with Image.open(path) as image:
            assert image.size == (595, 842)
    finally:
        doc.close()


def test_images_to_pdf_and_saving(tmp_path):
    filenames = []
    for i in range(2):
        path = tmp_path / f"image{i}.png"
        Image.new("RGBA", (300, 200), (i * 90, 80, 160, 180)).save(path)
        filenames.append(path)
    doc = PDFDocument.from_images(filenames)
    try:
        assert doc.page_count == 2
        assert doc.dirty
        assert doc.path is None
        path = doc.save(tmp_path / "images.pdf")
        assert path.is_file()
        assert not doc.dirty
        with fitz.open(path) as check:
            assert check.page_count == 2
            assert check[0].get_images()
    finally:
        doc.close()


def test_invalid_operations_do_not_change_document(input_pdf):
    doc = PDFDocument.open(input_pdf)
    try:
        with pytest.raises(PDFStudioError):
            doc.set_order([0, 0, 2])
        with pytest.raises(PDFStudioError):
            doc.move_page(0, 9)
        with pytest.raises(PDFStudioError):
            doc.crop_margins(0, 1000, 0, 0, 0)
        with pytest.raises(PDFStudioError):
            doc.export_png(0, input_pdf.with_suffix(".png"), dpi=900)
        assert not doc.dirty
    finally:
        doc.close()


def test_password_protected_open(input_pdf, tmp_path):
    protected = tmp_path / "protected.pdf"
    with fitz.open(input_pdf) as pdf:
        pdf.save(protected, encryption=fitz.PDF_ENCRYPT_AES_256,
                 owner_pw="admin-password", user_pw="reader-password")
    with pytest.raises(PasswordRequired):
        PDFDocument.open(protected)
    with pytest.raises(PasswordRequired):
        PDFDocument.open(protected, password="wrong")
    doc = PDFDocument.open(protected, password="reader-password")
    assert doc.page_count == 3
    with pytest.raises(PDFStudioError, match="owner password"):
        doc.save(tmp_path / "decrypted.pdf")
    doc.close()


def test_history_branch_clears_redo(input_pdf):
    doc = PDFDocument.open(input_pdf)
    try:
        doc.move_page(2, 0)
        doc.undo_order()
        doc.move_page(0, 2)
        assert doc.order == [1, 2, 0]
        assert not doc.can_redo_order
    finally:
        doc.close()
