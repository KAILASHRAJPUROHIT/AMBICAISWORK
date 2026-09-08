"""
Aradhana 355sdnw letterhead overlay.

Takes a single-page bill PDF captured from Ornate (copy 2, the customer
copy) and produces a 2-page duplex-ready PDF:
  - page 1: the bill content composited on top of the front letterhead
             image (logo/header)
  - page 2: the back terms-and-conditions image, printed as-is

Ornate's captured output (via Bullzip/Ghostscript) draws an explicit
opaque white rectangle covering the entire page as its very first drawing
operation - standard for report-generator output, but it defeats any
"insert image behind existing content" approach since that white fill
still sits between the inserted image and the rest of the content. This
strips that specific full-page white fill from the content stream before
compositing, so the letterhead can show through the (now genuinely blank)
background.

Usage:
    python overlay_merge.py <input_bill.pdf> <output_merged.pdf> <front_image> <back_image>
"""

import re
import sys
import fitz  # PyMuPDF

# Matches "1 1 1 rg" (white fill color) followed by a rectangle definition
# and a fill operator (f or f*). Only strips the first match, since that's
# the full-page background - later occurrences (e.g. individual table
# cells) are legitimate content and must stay untouched.
WHITE_BG_PATTERN = re.compile(
    rb"1 1 1 rg\s*\n[\d.]+ [\d.]+ [\d.]+ [\d.]+ re\s*\nf\*?\s*\n"
)


def strip_full_page_white_fill(doc, page):
    xrefs = page.get_contents()
    if not xrefs:
        return

    xref = xrefs[0]
    raw = doc.xref_stream(xref)

    new_raw, count = WHITE_BG_PATTERN.subn(b"", raw, count=1)
    if count > 0:
        doc.update_stream(xref, new_raw)


def main():
    if len(sys.argv) != 5:
        print("Usage: overlay_merge.py <input_bill.pdf> <output_merged.pdf> <front_image> <back_image>")
        sys.exit(1)

    input_pdf_path, output_pdf_path, front_image_path, back_image_path = sys.argv[1:5]

    doc = fitz.open(input_pdf_path)
    if doc.page_count == 0:
        print("ERROR: input PDF has no pages")
        sys.exit(1)

    front_page = doc[0]
    rect = front_page.rect

    strip_full_page_white_fill(doc, front_page)

    front_page.insert_image(rect, filename=front_image_path, overlay=False)

    back_page = doc.new_page(pno=1, width=rect.width, height=rect.height)
    back_page.insert_image(back_page.rect, filename=back_image_path)

    doc.save(output_pdf_path)
    doc.close()

    print("OK: wrote " + output_pdf_path + " (" + str(rect.width) + "x" + str(rect.height) + "pt, 2 pages)")


if __name__ == "__main__":
    main()
