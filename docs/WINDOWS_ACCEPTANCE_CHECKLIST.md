# Archived Part 2 Windows acceptance checklist (historical)

Test against a **copy** of a PDF you own. These are manual GUI checks that cannot be completed in a headless environment without PySide6. Record outcomes on the target Windows machine.

| ID | Manual test | Expected result |
|---|---|---|
| W01 | Install Python 3.11/3.12, run `scripts\setup_windows.bat` | Dependency installation and full suite succeed |
| W02 | Launch `scripts\run_windows.bat` | Premium dark window opens without exception; title and original ribbon layout visible |
| W03 | Open multi-page PDF, switch tabs | Real PDF rendered and tab switching preserves document state |
| W04 | Reorder by dragging thumbnails; undo/redo | Page order changes correctly and returns with Ctrl+Z/Ctrl+Y |
| W05 | Crop first page, Save As, reopen | Visible CropBox matches chosen margins; source retained |
| W06 | Export current/all pages to PNG | Files render and match visible PDF pages |
| W07 | Convert two PNG/JPEG images to PDF | PDF page count and image content match |
| W08 | Add Text via Edit tab, Save As, reopen | Inserted text remains selectable/searchable |
| W09 | Highlight phrase via Comment tab | Yellow highlight annotation stays visible after reopen |
| W10 | Redact a uniquely identifiable phrase, confirm, Save As, reopen | Underlying phrase no longer appears in text extraction/search |
| W11 | Redact region by dragging on page, confirm | Content in region is removed; images touching region may be removed entirely |
| W12 | Insert Image, watermark current/all pages, save | Images and translucent text appear on the requested pages |
| W13 | Change metadata, reopen with PDF inspector | Title, author, subject and keywords persist |
| W14 | Save optimized PDF | Reopens without loss of readable text; resulting size shown (may be larger) |
| W15 | Configure AES-256 user + different owner passwords; save | Cannot open without password; both valid passwords work |
| W16 | Reopen encrypted PDF with user password only | Viewing works; editing is prohibited with a clear explanation |
| W17 | Reopen encrypted PDF with owner password, edit + save | Correctly edited and remains encrypted; user password still opens |
| W18 | Save after prior AES-256-protected save | Protection remains enabled on subsequent saves |
| W19 | On a PDF with 90°-rotated page, use text and region redaction | Coordinates map to correct content |
| W20 | Run `scripts\build_windows_portable.bat`, launch from `dist` folder | Portable executable starts and opens a PDF from a separate folder |

### Not part of Part 2 acceptance

Online licensing and installer configuration are now implemented in Part 3 source, but require the Part 3 Windows release checklist before acceptance. Certificate signing, OCR, and Office converters remain outside the approved feature scope.

### Security review

- Inspect permanently redacted output with an independent PDF reader and extraction tool.
- Check attachments, metadata and duplicate copies for separately stored sensitive data.
- Test AES-256 with separate user and owner passwords, and record any permission differences across readers.
- Avoid submitting user-provided confidential PDFs or passwords with bug reports.
