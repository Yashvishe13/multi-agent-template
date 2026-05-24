---
name: pdf
description: Use this skill whenever the user wants to do anything with PDF files. This includes reading or extracting text/tables from PDFs, combining or merging multiple PDFs into one, splitting PDFs apart, rotating pages, adding watermarks, creating new PDFs, filling PDF forms, encrypting/decrypting PDFs, extracting images, and OCR on scanned PDFs to make them searchable. If the user mentions a .pdf file or asks to produce one, use this skill.
license: Proprietary. LICENSE.txt has complete terms
---

# PDF Processing Guide

## IMPORTANT: Read This First

When using this skill, follow these rules:
1. **Check what's installed first**: Run `pip list | grep -iE "pdf"` and `which pdftotext` before choosing a library.
2. **Prefer CLI tools** (pdftotext, qpdf) over Python for simple extraction — they're faster and less error-prone.
3. **Never extract all pages at once** for large PDFs. Extract first 3-5 pages, check output, then continue.
4. **Always write Python as multiline scripts**, never semicolon-joined one-liners.

## Quick Start — Text Extraction (Preferred Methods)

### Method 1: pdftotext CLI (fastest, most reliable)

```bash
# Extract all text (most common operation)
pdftotext input.pdf -

# Extract with layout preserved
pdftotext -layout input.pdf -

# Extract specific pages only (RECOMMENDED for large PDFs)
pdftotext -f 1 -l 5 input.pdf -    # Pages 1-5

# Save to file instead of stdout
pdftotext input.pdf output.txt
```

### Method 2: pdfplumber (Python, good for tables)

```bash
python3 -c "
import pdfplumber

with pdfplumber.open('document.pdf') as pdf:
    for i, page in enumerate(pdf.pages[:5]):
        text = page.extract_text()
        if text:
            print(f'--- Page {i+1} ---')
            print(text)
"
```

### Method 3: pdfminer (Python, detailed control)

```bash
python3 -c "
from pdfminer.high_level import extract_text

text = extract_text('document.pdf', page_numbers=[0,1,2,3,4])
print(text)
"
```

### Method 4: pypdf (if installed)

```bash
python3 -c "
from pypdf import PdfReader

reader = PdfReader('document.pdf')
print(f'Total pages: {len(reader.pages)}')
for i, page in enumerate(reader.pages[:5]):
    print(f'--- Page {i+1} ---')
    print(page.extract_text())
"
```

## Table Extraction

```bash
python3 -c "
import pdfplumber

with pdfplumber.open('document.pdf') as pdf:
    for i, page in enumerate(pdf.pages):
        tables = page.extract_tables()
        for j, table in enumerate(tables):
            print(f'Table {j+1} on page {i+1}:')
            for row in table:
                print(row)
"
```

## Merge PDFs

```bash
# With qpdf (CLI, if available)
qpdf --empty --pages file1.pdf file2.pdf -- merged.pdf

# With pypdf (Python)
python3 -c "
from pypdf import PdfWriter, PdfReader

writer = PdfWriter()
for pdf_file in ['doc1.pdf', 'doc2.pdf']:
    reader = PdfReader(pdf_file)
    for page in reader.pages:
        writer.add_page(page)

with open('merged.pdf', 'wb') as output:
    writer.write(output)
"
```

## Split PDF

```bash
# Extract specific pages with qpdf
qpdf input.pdf --pages . 1-5 -- pages1-5.pdf

# Split each page to separate file with pypdf
python3 -c "
from pypdf import PdfReader, PdfWriter

reader = PdfReader('input.pdf')
for i, page in enumerate(reader.pages):
    writer = PdfWriter()
    writer.add_page(page)
    with open(f'page_{i+1}.pdf', 'wb') as output:
        writer.write(output)
"
```

## Rotate Pages

```bash
python3 -c "
from pypdf import PdfReader, PdfWriter

reader = PdfReader('input.pdf')
writer = PdfWriter()
page = reader.pages[0]
page.rotate(90)
writer.add_page(page)
with open('rotated.pdf', 'wb') as output:
    writer.write(output)
"
```

## Create PDFs (reportlab)

```bash
python3 -c "
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

c = canvas.Canvas('hello.pdf', pagesize=letter)
width, height = letter
c.drawString(100, height - 100, 'Hello World!')
c.save()
"
```

**IMPORTANT for reportlab**: Never use Unicode subscript/superscript characters. Use `<sub>` and `<super>` tags in Paragraph objects instead.

## Extract Images

```bash
# Using pdfimages (poppler-utils, if available)
pdfimages -j input.pdf output_prefix
```

## Password Protection

```bash
python3 -c "
from pypdf import PdfReader, PdfWriter

reader = PdfReader('input.pdf')
writer = PdfWriter()
for page in reader.pages:
    writer.add_page(page)
writer.encrypt('userpassword', 'ownerpassword')
with open('encrypted.pdf', 'wb') as output:
    writer.write(output)
"
```

## OCR Scanned PDFs

```bash
# Requires: pip install pytesseract pdf2image
python3 -c "
import pytesseract
from pdf2image import convert_from_path

images = convert_from_path('scanned.pdf')
for i, image in enumerate(images[:5]):
    print(f'--- Page {i+1} ---')
    print(pytesseract.image_to_string(image))
"
```

## Quick Reference

| Task | Best Tool | Notes |
|------|-----------|-------|
| Extract text | `pdftotext` CLI | Fastest, works on any PDF |
| Extract text (Python) | pdfplumber or pdfminer | Check which is installed |
| Extract tables | pdfplumber | `page.extract_tables()` |
| Merge PDFs | qpdf or pypdf | Check which is available |
| Create PDFs | reportlab | Canvas or Platypus |
| OCR scanned PDFs | pytesseract + pdf2image | Convert to image first |
| Fill PDF forms | See FORMS.md | |

## Troubleshooting

- **ModuleNotFoundError**: Run `pip install <package>` first. Check which PDF libraries are actually installed with `pip list | grep -iE pdf`.
- **SyntaxError on one-liner**: Use multiline python3 -c with real newlines. Never use semicolons before `with`/`for`/`if`.
- **Process killed (exit code -9)**: Output too large. Limit pages: use `pdftotext -f 1 -l 5` or slice `pdf.pages[:5]`.
- **Empty output**: PDF might be scanned images, not text. Use OCR method above.
