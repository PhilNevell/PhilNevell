# OCR Compact Pipeline

Converts PDFs (including scanned/handwritten) into a compact representation with:
- Extracted text (word-level boxes and confidences)
- Small WEBP crops for low-confidence regions to preserve critical details
- Output formats: JSON (primary) and/or Markdown

## Why JSON over Markdown?
- JSON is structured (coordinates, confidence, per-word data), enabling precise reconstruction/search.
- Markdown is readable but loses spatial metadata. Prefer JSON when fidelity matters; emit Markdown for human-friendly summaries.

## Requirements
System tools (already installed here): `tesseract-ocr`, `poppler-utils` (for PDF rasterization). Python packages in `requirements.txt`.

## Install
```
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Usage
```
python -m ocr_compact.cli /path/to/input.pdf --out-dir ./ocr_output --format both --lang eng --dpi 300 --conf-threshold 70
```
Options:
- `--format`: json | md | both
- `--embed-images`: inline crops as base64 (bigger files, easier sharing)
- `--max-webp-dim`: limit crop size (default 1200px)
- `--webp-quality`: 0-100 (default 60)

## Output
- `NAME.compact.json`: structured text, per page words with bbox and confidences, and list of low-confidence crops (paths or data URIs).
- `NAME.compact.md`: human-readable text with embedded/linked crops.
- `ocr_output/crops/`: WEBP crops.

## Notes
- Size reduction target (90–95%) is achieved by storing text + small crops instead of full images.
- For born-digital PDFs, consider adding a text-extraction fast path. For heavy handwriting, add a specialized OCR engine.
