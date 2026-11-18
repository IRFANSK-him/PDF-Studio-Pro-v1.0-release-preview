"""PDF Studio Pro Part 2 features, validated against real saved PDF files."""
from pathlib import Path
from io import BytesIO

import fitz
import pytest
from PIL import Image

from pdfstudio.engine import PDFDocument, PDFStudioError


@pytest.fixture
def source(tmp_path: Path):
    pdf = fitz.open()
    page = pdf.new_page(width=595, height=842)
    page.insert_text((72, 80), "CONFIDENTIAL-ALPHA", fontsize=13)
    page.insert_text((72, 115), "Highlight target Highlight target", fontsize=11)
    page.insert_text((72, 150), "Public information", fontsize=11)
    pdf.new_page().insert_text((72, 80), "CONFIDENTIAL-ALPHA second page", fontsize=12)
    path = tmp_path / "source.pdf"
    pdf.save(path)
    pdf.close()
    return path


def test_add_text_image_watermark_and_metadata(source, tmp_path):
    image = tmp_path / "stamp.png"
    Image.new("RGB", (40, 20), (40, 160, 200)).save(image)
    doc = PDFDocument.open(source)
    try:
        doc.add_text(0, "APPROVED", 72, 210, font_size=17, color=(0, .5, 0))
        doc.insert_image(0, image, 200, 180, 100, 50)
        assert doc.add_watermark("WATERMARK", font_size=25, all_pages=True) == 2
        doc.edit_metadata({"title": "New Title", "author": "PDF Studio Pro", "subject": "Audit"})
        out = doc.save(tmp_path / "decorated.pdf")
        assert not doc.dirty
        with fitz.open(out) as check:
            assert "APPROVED" in check[0].get_text()
            assert "WATERMARK" in check[1].get_text()
            assert check[0].get_images()
            assert check.metadata["title"] == "New Title"
    finally:
        doc.close()


def test_highlight_is_annotation_and_text_remains(source, tmp_path):
    doc = PDFDocument.open(source)
    try:
        assert doc.highlight_text(0, "Highlight target") == 2
        assert doc.highlight_text(1, "doesn't exist") == 0
        result = doc.save(tmp_path / "highlight.pdf")
        with fitz.open(result) as saved:
            assert sum(1 for a in saved[0].annots() if a.type[1] == "Highlight") == 2
            assert "Highlight target" in saved[0].get_text()
    finally:
        doc.close()


def test_redaction_removes_underlying_text_and_saves(source, tmp_path):
    doc = PDFDocument.open(source)
    try:
        assert doc.redact_text(0, "CONFIDENTIAL-ALPHA", all_pages=True) == 2
        assert doc.search("CONFIDENTIAL-ALPHA") == []
        out = doc.save(tmp_path / "redacted.pdf")
        with fitz.open(out) as saved:
            assert not any("CONFIDENTIAL-ALPHA" in p.get_text() for p in saved)
            assert "Public information" in saved[0].get_text()
        assert b"CONFIDENTIAL-ALPHA" not in out.read_bytes()
    finally:
        doc.close()


def test_region_redact_removes_text(source, tmp_path):
    doc = PDFDocument.open(source)
    try:
        match = doc._page(0).search_for("CONFIDENTIAL-ALPHA")[0]
        doc.redact_region(0, (match.x0-1, match.y0-1, match.x1+1, match.y1+1))
        assert not doc._page(0).search_for("CONFIDENTIAL-ALPHA")
        assert doc.search("CONFIDENTIAL-ALPHA")[0].display_index == 1
        with pytest.raises(PDFStudioError):
            doc.redact_region(0, (-10, -10, 100, 100))
    finally:
        doc.close()


def test_aes256_encryption_and_subsequent_edit_preserves_it(source, tmp_path):
    doc = PDFDocument.open(source)
    try:
        doc.protect("reader_pw_123", "owner_pw_456")
        path = doc.save(tmp_path / "encrypted.pdf")
        with fitz.open(path) as protected:
            assert protected.needs_pass
            assert protected.authenticate("reader_pw_123") & 2
            assert "256-bit AES" in protected.metadata.get("encryption", "")
        doc.add_text(0, "AFTER SAVE", 72, 300)
        doc.save(path)
        with fitz.open(path) as checked:
            assert checked.needs_pass
            assert checked.authenticate("owner_pw_456") & 4
            assert "AFTER SAVE" in checked[0].get_text()
    finally:
        doc.close()


def test_owner_access_preserves_existing_encryption_and_user_access_is_readonly(source, tmp_path):
    protected = tmp_path / "original_encrypted.pdf"
    with fitz.open(source) as pdf:
        pdf.save(protected, encryption=fitz.PDF_ENCRYPT_AES_256,
                 user_pw="userOriginal", owner_pw="ownerOriginal")
    reader = PDFDocument.open(protected, password="userOriginal")
    try:
        assert not reader.can_edit
        with pytest.raises(PDFStudioError, match="owner password"):
            reader.add_text(0, "no", 50, 50)
        with pytest.raises(PDFStudioError, match="owner password"):
            reader.save(tmp_path / "not_allowed.pdf")
    finally:
        reader.close()
    owner = PDFDocument.open(protected, password="ownerOriginal")
    try:
        assert owner.can_edit
        owner.add_text(0, "OWNER CHANGE", 72, 240)
        out = owner.save(tmp_path / "still_protected.pdf")
        with fitz.open(out) as check:
            assert check.needs_pass
            assert check.authenticate("userOriginal") & 2
            assert "OWNER CHANGE" in check[0].get_text()
    finally:
        owner.close()


def test_lossless_compression_keeps_content(source, tmp_path):
    doc = PDFDocument.open(source)
    try:
        doc.enable_compression()
        out = doc.save(tmp_path / "compressed.pdf")
        assert out.exists()
        with fitz.open(out) as saved:
            assert saved.page_count == 2
            assert "Public information" in saved[0].get_text()
    finally:
        doc.close()


def test_invalid_edit_inputs_leave_document_clean(source, tmp_path):
    doc = PDFDocument.open(source)
    try:
        with pytest.raises(PDFStudioError):
            doc.add_text(0, "", 10, 20)
        with pytest.raises(PDFStudioError):
            doc.highlight_text(0, "")
        with pytest.raises(PDFStudioError):
            doc.redact_text(0, "")
        with pytest.raises(PDFStudioError):
            doc.insert_image(0, tmp_path / "missing.png", 0, 0, 50, 50)
        with pytest.raises(PDFStudioError):
            doc.edit_metadata({"invalidkey": "value"})
        with pytest.raises(PDFStudioError):
            doc.protect("same", "same")
        assert not doc.dirty
    finally:
        doc.close()


def test_reorder_edited_pages_then_save(source, tmp_path):
    doc = PDFDocument.open(source)
    try:
        doc.add_text(0, "PAGE ZERO EDIT", 72, 350)
        doc.move_page(0, 1)
        out = doc.save(tmp_path / "edited_reordered.pdf")
        with fitz.open(out) as check:
            assert "PAGE ZERO EDIT" in check[1].get_text()
    finally:
        doc.close()


def test_rotated_pdf_edit_coordinates(source, tmp_path):
    rotated = tmp_path / "rotated.pdf"
    with fitz.open(source) as pdf:
        pdf[0].set_rotation(90)
        pdf.save(rotated)
    doc = PDFDocument.open(rotated)
    try:
        assert doc.page_size(0) == pytest.approx((842, 595))
        assert doc.edit_page_size(0) == pytest.approx((595, 842))
        doc.add_text(0, "ROTATED TEST", 100, 310)
        doc.add_watermark("ROTATED", all_pages=False, display_index=0)
        out = doc.save(tmp_path / "rotated_saved.pdf")
        with fitz.open(out) as check:
            assert "ROTATED TEST" in check[0].get_text()
    finally:
        doc.close()


def test_encrypted_reorder_and_optimized_save_preserves_passwords(source, tmp_path):
    protected = tmp_path / "protected_reorder_source.pdf"
    with fitz.open(source) as pdf:
        pdf.save(protected, encryption=fitz.PDF_ENCRYPT_AES_256,
                 owner_pw="adminOriginal", user_pw="readerOriginal")
    doc = PDFDocument.open(protected, password="adminOriginal")
    try:
        doc.move_page(1, 0)
        doc.enable_compression()
        out = doc.save(tmp_path / "optimized_protected.pdf")
        with fitz.open(out) as verified:
            assert verified.needs_pass
            assert verified.authenticate("readerOriginal") & 2
            assert "second page" in verified[0].get_text()
            assert "Public information" in verified[1].get_text()
    finally:
        doc.close()


def test_owner_can_replace_protection_with_new_aes256_keys(source, tmp_path):
    protected = tmp_path / "protected_source.pdf"
    with fitz.open(source) as pdf:
        pdf.save(protected, encryption=fitz.PDF_ENCRYPT_AES_256,
                 owner_pw="oldAdmin", user_pw="oldUser")
    doc = PDFDocument.open(protected, password="oldAdmin")
    try:
        doc.protect("newUser", "newAdmin", permissions=fitz.PDF_PERM_ACCESSIBILITY)
        out = doc.save(tmp_path / "new_protection.pdf")
        with fitz.open(out) as check:
            assert check.needs_pass
            assert check.authenticate("oldUser") == 0
            assert check.authenticate("newUser") & 2
            assert "CONFIDENTIAL-ALPHA" in check[0].get_text()
    finally:
        doc.close()


def test_region_redaction_removes_overlapping_image_resource(source, tmp_path):
    stamp = tmp_path / "visible.png"
    Image.new("RGB", (120, 80), "red").save(stamp)
    doc = PDFDocument.open(source)
    try:
        doc.insert_image(0, stamp, 300, 300, 120, 80)
        assert doc._page(0).get_images()
        doc.redact_region(0, (315, 315, 335, 340))
        saved = doc.save(tmp_path / "image_redacted.pdf")
        with fitz.open(saved) as checked:
            # Policy: whole intersecting image is removed for safer redaction.
            assert not checked[0].get_images()
    finally:
        doc.close()


def test_custom_unicode_font_with_supported_simple_glyphs(source, tmp_path):
    font = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    if not font.is_file():
        pytest.skip('Developer workstation does not include DejaVu Sans')
    doc = PDFDocument.open(source)
    try:
        doc.add_text(0, "Caf\u00e9", 72, 260, font_file=font)
        output = doc.save(tmp_path / "custom_font.pdf")
        with fitz.open(output) as check:
            assert "Caf\u00e9" in check[0].get_text()
    finally:
        doc.close()
