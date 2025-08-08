from pathlib import Path
from typing import Iterator, Tuple

from loguru import logger
from pypdf import PdfReader

# Optional OCR imports guarded at runtime
try:
    from pdf2image import convert_from_path  # type: ignore
    import pytesseract  # type: ignore
    from PIL import Image  # type: ignore
    OCR_AVAILABLE = True
except Exception:  # pragma: no cover - environment dependent
    OCR_AVAILABLE = False


def extract_text_pages_from_pdf(path: Path, ocr: bool = False) -> Iterator[Tuple[int, str]]:
    """Yield (page_index, text) for each page. If no text and OCR requested, attempt OCR.

    OCR requires poppler (pdftoppm) and tesseract binaries installed.
    """
    reader = PdfReader(str(path))
    for page_index, page in enumerate(reader.pages):
        text = ""
        try:
            text = page.extract_text() or ""
        except Exception as e:
            logger.warning(f"Text extraction failed on {path} page {page_index+1}: {e}")
            text = ""
        if text.strip():
            yield page_index, text
            continue
        if ocr and OCR_AVAILABLE:
            try:
                images = convert_from_path(str(path), first_page=page_index + 1, last_page=page_index + 1, dpi=300)
                if images:
                    img = images[0]
                    ocr_text = pytesseract.image_to_string(img)
                    if ocr_text.strip():
                        yield page_index, ocr_text
                        continue
            except Exception as e:  # pragma: no cover - environment dependent
                logger.warning(f"OCR failed on {path} page {page_index+1}: {e}")
        else:
            if ocr and not OCR_AVAILABLE:
                logger.debug("OCR requested but dependencies not available")
            # yield empty or skip
            yield page_index, ""