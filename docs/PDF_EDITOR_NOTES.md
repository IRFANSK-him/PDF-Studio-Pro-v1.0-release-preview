# PDF Editor Limits & Behavior (Parts 1–2)

- **Permanent redaction** removes matching content from the PDF page, not a cosmetic overlay. Images intersecting redaction regions may be removed entirely to prevent leaking hidden pixels. Test saved PDFs, including text extraction, before relying on redaction.
- **Crop** changes the visible CropBox; it does not securely destroy cropped page content.
- **Undo/redo** is for **page-order changes**, not content edits or redaction. Back up important documents and prefer Save As.
- **Encrypted input:** user-password-opened files are read-only; owner-password-opened PDFs can be edited. Existing encryption is preserved on save unless explicitly replaced.
- **AES-256** protection is configured and takes effect when saving to a new output PDF. This is different from the Part 3 app's online licensing.
- **Compression** uses lossless optimization; file sizes are not guaranteed to shrink.
- Search/highlight/phrase redaction apply only to extractable PDF text; OCR remains out of scope.
- PDF text insertion is limited for complex Indic font shaping. Some fonts require the user to select an embeddable font file.
- Extremely large PDFs may require substantial memory; search and thumbnails are synchronous.
