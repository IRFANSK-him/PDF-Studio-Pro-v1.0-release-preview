"""PDF Studio Pro 0.2 — Qt-independent, testable PDF processing engine.

Documents are loaded into RAM so source files are not held open on Windows.
Save is atomic. Editing operations modify the working document, never the source
until the user saves. Page-order undo remains distinct from destructive edits.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import os
from pathlib import Path
import tempfile
from typing import Iterable

import fitz
from PIL import Image, ImageOps


class PDFStudioError(Exception):
    """Friendly error for invalid or unsupported document operations."""


class PasswordRequired(PDFStudioError):
    pass


@dataclass(frozen=True)
class SearchHit:
    display_index: int
    bounds: tuple[float, float, float, float]


@dataclass(frozen=True)
class PDFSecurity:
    """Pending save policy. Passwords are kept only in the process memory."""
    user_password: str
    owner_password: str
    permissions: int


METADATA_KEYS = frozenset(("title", "author", "subject", "keywords", "creator", "producer"))
DEFAULT_PERMISSIONS = (fitz.PDF_PERM_PRINT | fitz.PDF_PERM_PRINT_HQ |
                       fitz.PDF_PERM_COPY | fitz.PDF_PERM_ACCESSIBILITY)


class PDFDocument:
    def __init__(self, pdf: fitz.Document, path: str | Path | None = None,
                 *, original_password: str | None = None, owner_access: bool = False,
                 source_encrypted: bool = False):
        if not pdf.is_pdf:
            pdf.close()
            raise PDFStudioError("Only PDF documents are supported.")
        if pdf.is_encrypted:
            pdf.close()
            raise PasswordRequired("This PDF requires a valid password.")
        # PyMuPDF may reset decrypted stream state when needs_pass is inspected
        # after authenticate(). Capture it BEFORE authentication instead.
        self._source_was_encrypted = source_encrypted
        self._original_password = original_password
        self._owner_access = owner_access
        self._security: PDFSecurity | None = None
        self._optimize = False
        self._redacted = False
        self._pdf = pdf
        self.path = Path(path).resolve() if path else None
        self.order = list(range(pdf.page_count))
        self._history = [self.order.copy()]
        self._history_position = 0
        self._edited = False
        self._closed = False

    @classmethod
    def open(cls, filename: str | Path, password: str | None = None) -> "PDFDocument":
        path = Path(filename)
        try:
            pdf = fitz.open(stream=path.read_bytes(), filetype="pdf")
            was_encrypted = bool(pdf.needs_pass)
            owner_access = not was_encrypted
            if was_encrypted:
                auth = pdf.authenticate(password or "") if password else 0
                if not auth:
                    pdf.close()
                    raise PasswordRequired("A valid PDF password is required.")
                owner_access = bool(auth & 4)
            return cls(pdf, path, original_password=password, owner_access=owner_access,
                       source_encrypted=was_encrypted)
        except PDFStudioError:
            raise
        except (OSError, RuntimeError, ValueError) as exc:
            raise PDFStudioError(f"Cannot open PDF: {exc}") from exc

    @classmethod
    def from_images(cls, filenames: Iterable[str | Path]) -> "PDFDocument":
        images = [Path(f) for f in filenames]
        if not images:
            raise PDFStudioError("Choose at least one image.")
        pdf = fitz.open()
        try:
            for filename in images:
                with Image.open(filename) as original:
                    image = ImageOps.exif_transpose(original)
                    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
                        rgba = image.convert("RGBA")
                        background = Image.new("RGB", rgba.size, "white")
                        background.paste(rgba, mask=rgba.getchannel("A"))
                        image = background
                    else:
                        image = image.convert("RGB")
                    width, height = (max(1, dim * 72 / 96) for dim in image.size)
                    page = pdf.new_page(width=width, height=height)
                    data = BytesIO()
                    image.save(data, format="JPEG", quality=93, optimize=True)
                    page.insert_image(page.rect, stream=data.getvalue())
            result = cls(pdf)
            result._edited = True
            return result
        except Exception as exc:
            pdf.close()
            if isinstance(exc, PDFStudioError):
                raise
            raise PDFStudioError(f"Cannot convert images: {exc}") from exc

    @property
    def page_count(self) -> int:
        return len(self.order)

    @property
    def dirty(self) -> bool:
        return self._edited or self.order != list(range(self._pdf.page_count))

    @property
    def title(self) -> str:
        return self.path.name if self.path else "Untitled Images.pdf"

    @property
    def can_edit(self) -> bool:
        """User-password-only authorization is treated as read-only."""
        return not self._source_was_encrypted or self._owner_access

    @property
    def encrypted(self) -> bool:
        return self._security is not None or self._source_was_encrypted

    @property
    def metadata(self) -> dict[str, str]:
        return {key: self._pdf.metadata.get(key, "") or "" for key in METADATA_KEYS}

    @property
    def can_undo_order(self) -> bool:
        return self._history_position > 0

    @property
    def can_redo_order(self) -> bool:
        return self._history_position < len(self._history) - 1

    def _require_edit(self) -> None:
        if not self.can_edit:
            raise PDFStudioError("This protected PDF is opened with a user password. "
                                 "Reopen it with the owner password to make changes.")

    def _page(self, display_index: int) -> fitz.Page:
        if not (0 <= display_index < self.page_count):
            raise PDFStudioError("Page number is outside the document.")
        return self._pdf.load_page(self.order[display_index])

    def page_size(self, display_index: int) -> tuple[float, float]:
        r = self._page(display_index).rect
        return r.width, r.height

    def edit_page_size(self, display_index: int) -> tuple[float, float]:
        """Unrotated PDF coordinates used by PyMuPDF insertion/redaction APIs."""
        page = self._page(display_index)
        rect = page.rect * page.derotation_matrix
        return rect.width, rect.height

    def render(self, display_index: int, zoom: float = 1.0) -> fitz.Pixmap:
        if not 0.20 <= zoom <= 4.0:
            raise PDFStudioError("Zoom must be between 20% and 400%.")
        return self._page(display_index).get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)

    def set_order(self, new_order: Iterable[int]) -> bool:
        self._require_edit()
        order = list(new_order)
        if len(order) != self.page_count or set(order) != set(self.order):
            raise PDFStudioError("Page order must include every page exactly once.")
        if order == self.order:
            return False
        self.order = order
        self._history = self._history[:self._history_position + 1]
        self._history.append(order.copy())
        if len(self._history) > 101:
            self._history.pop(0)
        self._history_position = len(self._history) - 1
        return True

    def move_page(self, source: int, destination: int) -> bool:
        if not 0 <= source < self.page_count or not 0 <= destination < self.page_count:
            raise PDFStudioError("Invalid source or destination page.")
        order = self.order.copy()
        page = order.pop(source)
        order.insert(destination, page)
        return self.set_order(order)

    def undo_order(self) -> bool:
        self._require_edit()
        if not self.can_undo_order:
            return False
        self._history_position -= 1
        self.order = self._history[self._history_position].copy()
        return True

    def redo_order(self) -> bool:
        self._require_edit()
        if not self.can_redo_order:
            return False
        self._history_position += 1
        self.order = self._history[self._history_position].copy()
        return True

    def crop_margins(self, display_index: int, left: float, top: float,
                     right: float, bottom: float) -> tuple[float, float]:
        """CropBox-only: visible crop, not removal of hidden data."""
        self._require_edit()
        margins = (left, top, right, bottom)
        if any(v < 0 for v in margins):
            raise PDFStudioError("Crop margins cannot be negative.")
        page = self._page(display_index)
        bounds = page.cropbox
        candidate = fitz.Rect(bounds.x0 + left, bounds.y0 + top,
                              bounds.x1 - right, bounds.y1 - bottom)
        if candidate.width < 5 or candidate.height < 5:
            raise PDFStudioError("Margins would leave less than 5 points of visible page.")
        try:
            page.set_cropbox(candidate)
        except ValueError as exc:
            raise PDFStudioError(f"Cannot crop page: {exc}") from exc
        if any(margins):
            self._edited = True
        return candidate.width, candidate.height

    def search(self, text: str) -> list[SearchHit]:
        if not text.strip():
            return []
        hits: list[SearchHit] = []
        for display_index in range(self.page_count):
            page = self._page(display_index)
            for rect in page.search_for(text.strip()):
                hits.append(SearchHit(display_index, tuple(rect)))
        return hits

    @staticmethod
    def _rgb(color: tuple[float, float, float]) -> tuple[float, float, float]:
        if len(color) != 3 or any(not 0 <= v <= 1 for v in color):
            raise PDFStudioError("Color must be an RGB tuple with values between 0 and 1.")
        return color

    def add_text(self, display_index: int, text: str, x: float, y: float,
                 font_size: float = 14, color: tuple[float, float, float] = (0, 0, 0),
                 font_file: str | Path | None = None) -> None:
        """Add actual PDF text at a baseline coordinate, not a text-box image."""
        self._require_edit()
        if not text or not text.strip():
            raise PDFStudioError("Enter text to insert.")
        if not 4 <= font_size <= 144:
            raise PDFStudioError("Text size must be 4–144 points.")
        page = self._page(display_index)
        edit_rect = page.rect * page.derotation_matrix
        if not (0 <= x <= edit_rect.width and 0 <= y <= edit_rect.height):
            raise PDFStudioError("Text coordinates are outside the visible page.")
        if font_file:
            path = Path(font_file)
            if not path.is_file() or path.suffix.lower() not in (".ttf", ".otf"):
                raise PDFStudioError("Choose an existing TTF or OTF font.")
            options = {"fontname": "CustomFont", "fontfile": str(path)}
        else:
            if any(ord(char) > 255 for char in text):
                raise PDFStudioError("Unicode text needs a compatible TTF or OTF font. "
                                     "Complex scripts may require external shaping.")
            options = {"fontname": "helv"}
        try:
            page.insert_text((x, y), text, fontsize=font_size,
                             color=self._rgb(color), overlay=True, **options)
            self._edited = True
        except Exception as exc:
            raise PDFStudioError(f"Cannot insert text: {exc}") from exc

    def highlight_text(self, display_index: int, phrase: str, *, all_pages: bool = False,
                       color: tuple[float, float, float] = (1.0, 0.9, 0.25)) -> int:
        """Add real highlight annotations for every matching phrase."""
        self._require_edit()
        if not phrase.strip():
            raise PDFStudioError("Enter the text to highlight.")
        count = 0
        self._rgb(color)
        for i in (range(self.page_count) if all_pages else (display_index,)):
            page = self._page(i)
            quads = page.search_for(phrase.strip(), quads=True)
            if quads:
                for quad in quads:
                    annotation = page.add_highlight_annot(quad)
                    annotation.set_colors(stroke=color)
                    annotation.update()
                count += len(quads)
        if count:
            self._edited = True
        return count

    def _apply_redactions(self, page: fitz.Page) -> None:
        # Remove intersecting images entirely. Also removes intersected vector
        # graphics and PDF text rather than merely painting a black rectangle.
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_REMOVE,
                              graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
                              text=fitz.PDF_REDACT_TEXT_REMOVE)

    def redact_text(self, display_index: int, phrase: str, *, all_pages: bool = False) -> int:
        """Permanently remove every matching text instance from PDF page content."""
        self._require_edit()
        if not phrase.strip():
            raise PDFStudioError("Enter the text to redact.")
        total = 0
        for i in (range(self.page_count) if all_pages else (display_index,)):
            page = self._page(i)
            matches = page.search_for(phrase.strip())
            if matches:
                for rect in matches:
                    page.add_redact_annot(rect, fill=(0, 0, 0), cross_out=False)
                self._apply_redactions(page)
                total += len(matches)
        if total:
            self._edited = True
            self._redacted = True
        return total

    def redact_region(self, display_index: int, rect: tuple[float, float, float, float]) -> None:
        """Permanently remove all page content intersecting a region."""
        self._require_edit()
        page = self._page(display_index)
        r = fitz.Rect(rect)
        visible = page.rect * page.derotation_matrix
        if (r.is_empty or r.is_infinite or r.width < 2 or r.height < 2 or
                not visible.contains(r)):
            raise PDFStudioError("Choose a region at least 2 points wide entirely within the page.")
        page.add_redact_annot(r, fill=(0, 0, 0), cross_out=False)
        self._apply_redactions(page)
        self._edited = True
        self._redacted = True

    def insert_image(self, display_index: int, filename: str | Path, x: float, y: float,
                     width: float, height: float) -> None:
        self._require_edit()
        path = Path(filename)
        if not path.is_file():
            raise PDFStudioError("Image file does not exist.")
        page = self._page(display_index)
        area = fitz.Rect(x, y, x + width, y + height)
        edit_rect = page.rect * page.derotation_matrix
        if (area.is_empty or width < 1 or height < 1 or not edit_rect.contains(area)):
            raise PDFStudioError("Image placement must fit entirely inside the page.")
        try:
            with Image.open(path) as img:
                img.verify()
            page.insert_image(area, filename=str(path), keep_proportion=True, overlay=True)
            self._edited = True
        except Exception as exc:
            raise PDFStudioError(f"Cannot insert image: {exc}") from exc

    def add_watermark(self, text: str, *, all_pages: bool = True,
                      display_index: int = 0, font_size: float = 44,
                      opacity: float = 0.23, position: str = "center") -> int:
        """Add centered (or corner) translucent text to selected pages."""
        self._require_edit()
        if not text.strip():
            raise PDFStudioError("Watermark text cannot be blank.")
        if any(ord(char) > 255 for char in text):
            raise PDFStudioError("Watermark currently supports Latin-1 text only.")
        if not 8 <= font_size <= 144 or not 0.05 <= opacity <= 1.0:
            raise PDFStudioError("Use 8–144 pt and opacity between 0.05 and 1.0.")
        if position not in ("center", "bottom-right", "top-right"):
            raise PDFStudioError("Unsupported watermark position.")
        count = 0
        for i in (range(self.page_count) if all_pages else (display_index,)):
            page = self._page(i)
            edit_rect = page.rect * page.derotation_matrix
            width = fitz.get_text_length(text, fontname="helv", fontsize=font_size)
            # Reduce for long watermarks to keep text in page bounds.
            effective_size = min(font_size, font_size * max(0.2, (edit_rect.width - 36) / max(width, 1)))
            width = fitz.get_text_length(text, fontname="helv", fontsize=effective_size)
            if position == "center":
                x, y = (edit_rect.width - width) / 2, edit_rect.height / 2
            elif position == "bottom-right":
                x, y = edit_rect.width - width - 18, edit_rect.height - 20
            else:
                x, y = edit_rect.width - width - 18, effective_size + 20
            page.insert_text((max(x, 0), y), text, fontname="helv",
                             fontsize=effective_size, color=(0.5, 0.5, 0.5),
                             fill_opacity=opacity, overlay=True)
            count += 1
        if count:
            self._edited = True
        return count

    def edit_metadata(self, values: dict[str, str]) -> None:
        self._require_edit()
        if set(values) - METADATA_KEYS:
            raise PDFStudioError("Unsupported metadata field.")
        metadata = {**self._pdf.metadata, **{k: str(v) for k, v in values.items()}}
        try:
            self._pdf.set_metadata(metadata)
            self._edited = True
        except (ValueError, RuntimeError) as exc:
            raise PDFStudioError(f"Cannot update metadata: {exc}") from exc

    def protect(self, user_password: str, owner_password: str,
                permissions: int = DEFAULT_PERMISSIONS) -> None:
        """Configure AES-256 at save time, without writing plaintext intermediate files."""
        self._require_edit()
        if not user_password or not owner_password:
            raise PDFStudioError("Enter both user and owner passwords.")
        if user_password == owner_password:
            raise PDFStudioError("The owner password must be different from the user password.")
        self._security = PDFSecurity(user_password, owner_password, permissions)
        self._edited = True

    def enable_compression(self) -> None:
        """Request a lossless, full-rewrite optimized save (not always smaller)."""
        self._require_edit()
        self._optimize = True
        self._edited = True

    def export_png(self, display_index: int, destination: str | Path, dpi: int = 150) -> Path:
        if not 36 <= dpi <= 600:
            raise PDFStudioError("PNG resolution must be between 36 and 600 dpi.")
        output = Path(destination)
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._page(display_index).get_pixmap(dpi=dpi, alpha=False).save(str(output))
        except (OSError, RuntimeError) as exc:
            raise PDFStudioError(f"Cannot export PNG: {exc}") from exc
        return output

    def save(self, destination: str | Path) -> Path:
        """Atomic save preserving protection, page order, metadata and changes.

        The save clone is kept in memory; the temporary file contains only the
        final encrypted bytes when security is selected. The original stays
        intact if saving fails.
        """
        self._require_edit()
        output = Path(destination).expanduser().resolve()
        if output.suffix.lower() != ".pdf":
            raise PDFStudioError("Saved documents must use a .pdf extension.")
        if not output.parent.is_dir():
            raise PDFStudioError("The destination folder does not exist.")
        temp_path: Path | None = None
        clone: fitz.Document | None = None
        restore_bytes: bytes | None = None
        protected_keep = self._security is None and self._source_was_encrypted
        try:
            if protected_keep:
                # IMPORTANT: do not round-trip encrypted data through an encrypted
                # .tobytes() clone before KEEP saving. That can double-encrypt
                # edited streams with MuPDF. Save the authenticated document
                # directly, backing up bytes before mutating its page tree.
                encryption = fitz.PDF_ENCRYPT_KEEP
                clone = self._pdf
                if self.order != list(range(clone.page_count)):
                    restore_bytes = clone.tobytes(encryption=fitz.PDF_ENCRYPT_KEEP)
                    clone.select(self.order)
            else:
                encryption = fitz.PDF_ENCRYPT_AES_256 if self._security else fitz.PDF_ENCRYPT_NONE
                source_bytes = self._pdf.tobytes(garbage=3, deflate=True,
                                                 encryption=fitz.PDF_ENCRYPT_NONE)
                clone = fitz.open(stream=source_bytes, filetype="pdf")
                if self.order != list(range(clone.page_count)):
                    clone.select(self.order)
            options = dict(garbage=4 if (self._optimize or self._redacted) else 3,
                           deflate=True, encryption=encryption,
                           deflate_images=self._optimize,
                           deflate_fonts=self._optimize,
                           use_objstms=1 if self._optimize else 0)
            if self._security is not None:
                options.update(user_pw=self._security.user_password,
                               owner_pw=self._security.owner_password,
                               permissions=self._security.permissions)
            with tempfile.NamedTemporaryFile(prefix=".pdfstudio-", suffix=".pdf",
                                             dir=output.parent, delete=False) as tmp:
                temp_path = Path(tmp.name)
            clone.save(str(temp_path), **options)
            if not protected_keep:
                clone.close()
            clone = None
            # Check the file can be reopened BEFORE replacing existing output.
            verification = fitz.open(str(temp_path))
            if verification.needs_pass:
                owner_password = (self._security.owner_password if self._security
                                  else self._original_password or "")
                if not verification.authenticate(owner_password):
                    verification.close()
                    raise PDFStudioError("Saved PDF failed password verification.")
            if verification.page_count != self.page_count:
                verification.close()
                raise PDFStudioError("Saved PDF has an unexpected page count.")
            verification.close()
            os.replace(temp_path, output)
            temp_path = None
            reloaded = fitz.open(stream=output.read_bytes(), filetype="pdf")
            was_encrypted = bool(reloaded.needs_pass)
            if was_encrypted:
                auth_password = (self._security.owner_password if self._security
                                 else self._original_password or "")
                if not reloaded.authenticate(auth_password):
                    reloaded.close()
                    raise PDFStudioError("Cannot reopen newly saved protected PDF.")
            self._pdf.close()
            self._pdf = reloaded
            self.path = output
            self.order = list(range(self._pdf.page_count))
            self._history = [self.order.copy()]
            self._history_position = 0
            self._edited = False
            self._optimize = False
            self._redacted = False
            self._source_was_encrypted = was_encrypted
            if self._security:
                self._original_password = self._security.owner_password
                self._owner_access = True
            return output
        except PDFStudioError:
            raise
        except (OSError, RuntimeError, ValueError) as exc:
            raise PDFStudioError(f"Cannot save PDF: {exc}") from exc
        finally:
            if clone is not None and clone is not self._pdf:
                clone.close()
            if restore_bytes is not None and self._pdf is not None and self._pdf.page_count == len(self.order) and self.order != list(range(len(self.order))):
                # Applied only after an unsuccessful save. A successful save
                # resets self.order to identity and replaces self._pdf.
                self._pdf.close()
                self._pdf = fitz.open(stream=restore_bytes, filetype="pdf")
                self._pdf.authenticate(self._original_password or "")
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def close(self) -> None:
        if not self._closed:
            self._pdf.close()
            self._closed = True
