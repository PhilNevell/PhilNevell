import base64
import io
import json
import math
import os
import time
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

from PIL import Image
import pytesseract
from pdf2image import convert_from_path


@dataclass
class WordBox:
    text: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # x, y, w, h


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def resize_to_max_dim(image: Image.Image, max_dim: int) -> Image.Image:
    width, height = image.size
    if max(width, height) <= max_dim:
        return image
    if width >= height:
        new_width = max_dim
        new_height = int(height * (max_dim / float(width)))
    else:
        new_height = max_dim
        new_width = int(width * (max_dim / float(height)))
    return image.resize((new_width, new_height), Image.LANCZOS)


def merge_overlapping_boxes(boxes: List[Tuple[int, int, int, int]], expand_px: int = 6) -> List[Tuple[int, int, int, int]]:
    if not boxes:
        return []
    # Convert to x1,y1,x2,y2 and expand
    expanded: List[Tuple[int, int, int, int]] = []
    for x, y, w, h in boxes:
        x1 = max(0, x - expand_px)
        y1 = max(0, y - expand_px)
        x2 = x + w + expand_px
        y2 = y + h + expand_px
        expanded.append((x1, y1, x2, y2))

    expanded.sort(key=lambda b: (b[1], b[0]))

    merged: List[Tuple[int, int, int, int]] = []
    for box in expanded:
        if not merged:
            merged.append(box)
            continue
        mx1, my1, mx2, my2 = merged[-1]
        x1, y1, x2, y2 = box
        # check overlap or adjacency
        if not (x1 > mx2 or x2 < mx1 or y1 > my2 or y2 < my1):
            nx1 = min(mx1, x1)
            ny1 = min(my1, y1)
            nx2 = max(mx2, x2)
            ny2 = max(my2, y2)
            merged[-1] = (nx1, ny1, nx2, ny2)
        else:
            merged.append(box)

    # Convert back to x,y,w,h
    results: List[Tuple[int, int, int, int]] = []
    for x1, y1, x2, y2 in merged:
        results.append((x1, y1, max(1, x2 - x1), max(1, y2 - y1)))
    return results


def encode_image_to_webp_bytes(image: Image.Image, quality: int = 60) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="WEBP", quality=quality, method=6)
    return buffer.getvalue()


def save_or_embed_crop(crop_img: Image.Image, out_dir: str, page_index: int, region_index: int, embed_images: bool, max_webp_dim: int, quality: int = 60) -> Dict[str, str]:
    resized = resize_to_max_dim(crop_img, max_webp_dim)
    if embed_images:
        webp_bytes = encode_image_to_webp_bytes(resized, quality=quality)
        data_uri = "data:image/webp;base64," + base64.b64encode(webp_bytes).decode("ascii")
        return {"data_uri": data_uri}
    else:
        crops_dir = os.path.join(out_dir, "crops")
        ensure_dir(crops_dir)
        filename = f"page{page_index+1:04d}_region{region_index+1:03d}.webp"
        file_path = os.path.join(crops_dir, filename)
        resized.save(file_path, format="WEBP", quality=quality, method=6)
        return {"path": os.path.relpath(file_path, out_dir)}


def run_tesseract_on_image(image: Image.Image, lang: str) -> Dict[str, List]:
    config = "--oem 1 --psm 6"  # LSTM OCR, assume a block of text
    data = pytesseract.image_to_data(image, lang=lang, config=config, output_type=pytesseract.Output.DICT)
    return data


def extract_words(data: Dict[str, List]) -> List[WordBox]:
    words: List[WordBox] = []
    n = len(data.get("text", []))
    for i in range(n):
        text = (data["text"][i] or "").strip()
        try:
            conf_raw = float(data.get("conf", ["-1"][i]))
        except Exception:
            conf_raw = -1.0
        if text == "" and conf_raw < 0:
            continue
        x = int(data.get("left", [0])[i])
        y = int(data.get("top", [0])[i])
        w = int(data.get("width", [0])[i])
        h = int(data.get("height", [0])[i])
        words.append(WordBox(text=text, confidence=conf_raw, bbox=(x, y, w, h)))
    return words


def page_text_from_words(words: List[WordBox]) -> str:
    # Simple concatenation by lines (group words by y proximity)
    if not words:
        return ""
    sorted_words = sorted(words, key=lambda wb: (wb.bbox[1], wb.bbox[0]))
    lines: List[List[WordBox]] = []
    line_y_tol = 8
    for w in sorted_words:
        if not lines:
            lines.append([w])
            continue
        last_line = lines[-1]
        avg_y = sum(ww.bbox[1] for ww in last_line) / len(last_line)
        if abs(w.bbox[1] - avg_y) <= line_y_tol:
            last_line.append(w)
        else:
            lines.append([w])
    parts: List[str] = []
    for line in lines:
        line_sorted = sorted(line, key=lambda ww: ww.bbox[0])
        parts.append(" ".join(ww.text for ww in line_sorted if ww.text))
    return "\n".join(p for p in parts if p)


def ocr_pdf_to_compact(
    pdf_path: str,
    out_dir: str,
    lang: str = "eng",
    dpi: int = 300,
    conf_threshold: int = 70,
    fmt: str = "json",
    embed_images: bool = False,
    max_webp_dim: int = 1200,
    webp_quality: int = 60,
) -> str:
    ensure_dir(out_dir)
    basename = os.path.splitext(os.path.basename(pdf_path))[0]

    pages: List[Image.Image] = convert_from_path(pdf_path, dpi=dpi)

    doc = {
        "version": "1.0",
        "source_file": os.path.basename(pdf_path),
        "created_ts": int(time.time()),
        "lang": lang,
        "pages": [],
    }

    overall_text_parts: List[str] = []

    for page_index, pil_image in enumerate(pages):
        width, height = pil_image.size
        data = run_tesseract_on_image(pil_image, lang=lang)
        words = extract_words(data)

        low_conf_boxes: List[Tuple[int, int, int, int]] = [wb.bbox for wb in words if wb.confidence >= 0 and wb.confidence < conf_threshold]
        merged_regions = merge_overlapping_boxes(low_conf_boxes)

        crops_meta: List[Dict] = []
        for region_index, (x, y, w, h) in enumerate(merged_regions):
            crop_img = pil_image.crop((x, y, x + w, y + h))
            link = save_or_embed_crop(
                crop_img=crop_img,
                out_dir=out_dir,
                page_index=page_index,
                region_index=region_index,
                embed_images=embed_images,
                max_webp_dim=max_webp_dim,
                quality=webp_quality,
            )
            meta = {"bbox": [x, y, w, h], **link}
            crops_meta.append(meta)

        page_text = page_text_from_words([wb for wb in words if wb.text])
        overall_text_parts.append(page_text)

        page_entry = {
            "page_index": page_index,
            "width": width,
            "height": height,
            "text": page_text,
            "words": [
                {"text": wb.text, "conf": wb.confidence, "bbox": [*wb.bbox]}
                for wb in words
            ],
            "low_conf_crops": crops_meta,
        }
        doc["pages"].append(page_entry)

    doc["text"] = "\n\n".join(p for p in overall_text_parts if p)

    out_json_path = os.path.join(out_dir, f"{basename}.compact.json")
    if fmt in ("json", "both"):
        with open(out_json_path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))

    if fmt in ("md", "both"):
        out_md_path = os.path.join(out_dir, f"{basename}.compact.md")
        with open(out_md_path, "w", encoding="utf-8") as f:
            f.write(f"# {basename} (compact OCR)\n\n")
            f.write("## Extracted Text\n\n")
            f.write(doc["text"] + "\n\n")
            for page in doc["pages"]:
                if page.get("low_conf_crops"):
                    f.write(f"## Page {page['page_index']+1} low-confidence regions\n\n")
                    for idx, crop in enumerate(page["low_conf_crops"]):
                        if "path" in crop:
                            f.write(f"![page {page['page_index']+1} region {idx+1}]({crop['path']})\n\n")
                        elif "data_uri" in crop:
                            f.write(f"![page {page['page_index']+1} region {idx+1}]({crop['data_uri']})\n\n")
        if fmt == "md":
            return out_md_path

    return out_json_path