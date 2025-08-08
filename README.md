# Board Reports Ingestion & Anonymization CLI

A Python CLI to ingest large board reports (PDF, OCR, Excel), anonymize sensitive information, and export normalized JSONL chunks compressed with gzip. Optionally attempts OCR on image-only PDFs.

By default, anonymization uses a lightweight regex-based detector (emails, phones, IPs, credit cards, SSNs, dates) with deterministic pseudonymization. You may extend it or swap in Presidio if desired.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

For OCR support, ensure `poppler-utils` and `tesseract-ocr` binaries are installed and on PATH.

## Usage

```bash
python -m app.cli ingest \
  --input /path/to/folder_or_file \
  --output /path/to/output.jsonl.gz \
  --secret "YOUR_DETERMINISTIC_KEY" \
  --ocr  # optional, attempt OCR for scanned PDFs
```

- Input can be a file or directory. Multiple `--input` flags are allowed.
- Output is a gzip-compressed JSONL. Each line is a chunk with metadata and anonymized text.
- Use `--secret` or set `ANONYMIZATION_SECRET` env var (.env supported).

## Notes
- OCR requires `pdftoppm` (poppler) and `tesseract-ocr` binaries available in PATH.
- If OCR is unavailable, the app continues and skips OCR-only pages.
- Excel sheets are flattened into text with cell coordinates for context.

## Optional: Presidio/SpaCy
If you want richer PII detection, install Presidio and SpaCy in your environment and wire them into `app/core/anonymize.py`.
