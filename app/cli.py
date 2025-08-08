import hashlib
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Tuple

import typer
from rich.console import Console
from rich.progress import Progress
from tqdm import tqdm
from loguru import logger

from .core.anonymize import Anonymizer
from .core.extract_excel import extract_text_from_excel
from .core.extract_pdf import extract_text_pages_from_pdf
from .core.io_utils import (
    CompressedJsonlWriter,
    compute_file_sha256,
    discover_input_files,
)
from .core.chunk import chunk_text

app = typer.Typer(add_completion=False)
console = Console()


@dataclass
class IngestConfig:
    inputs: List[Path]
    output: Path
    secret: str
    ocr: bool = False
    max_chars_per_chunk: int = 4000


@app.command()
def ingest(
    input: List[Path] = typer.Option(
        ..., "--input", help="Input file or directory. Repeatable.")
    ,
    output: Path = typer.Option(..., "--output", help="Output .jsonl.gz path (gzipped JSON Lines)"),
    secret: Optional[str] = typer.Option(None, "--secret", help="Deterministic anonymization secret (or set ANONYMIZATION_SECRET)"),
    ocr: bool = typer.Option(False, "--ocr", help="Attempt OCR for scanned PDFs (requires poppler & tesseract)"),
    max_chars_per_chunk: int = typer.Option(4000, "--max-chars-per-chunk", help="Max characters per chunk for JSONL output"),
):
    """Ingest PDFs/Excels, anonymize, and write compressed JSONL chunks."""

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    secret_value = secret or os.getenv("ANONYMIZATION_SECRET")
    if not secret_value:
        console.print("[red]Missing --secret or ANONYMIZATION_SECRET[/red]")
        raise typer.Exit(code=2)

    inputs_list = []
    for p in input:
        inputs_list.extend(discover_input_files(Path(p)))

    if not inputs_list:
        console.print("[red]No input files found[/red]")
        raise typer.Exit(code=2)

    cfg = IngestConfig(inputs=inputs_list, output=out_path, secret=secret_value, ocr=ocr, max_chars_per_chunk=max_chars_per_chunk)

    anonymizer = Anonymizer(secret_key=cfg.secret)

    num_files = len(cfg.inputs)
    console.print(f"[bold]Discovered {num_files} files[/bold]")

    with CompressedJsonlWriter(cfg.output) as writer:
        for file_path in tqdm(cfg.inputs, desc="Processing files"):
            try:
                process_file(file_path, cfg, anonymizer, writer)
            except Exception as e:
                logger.exception(f"Failed to process {file_path}: {e}")
                continue

    console.print(f"[green]Done. Wrote {cfg.output if cfg.output.suffix.endswith('.gz') else str(cfg.output)+'.gz'}[/green]")


def process_file(file_path: Path, cfg: IngestConfig, anonymizer: Anonymizer, writer: CompressedJsonlWriter) -> None:
    ext = file_path.suffix.lower()
    file_id = str(uuid.uuid4())
    file_hash = compute_file_sha256(file_path)

    if ext in {".pdf"}:
        for page_index, page_text in extract_text_pages_from_pdf(file_path, ocr=cfg.ocr):
            if not page_text:
                continue
            for chunk_index, chunk in enumerate(chunk_text(page_text, max_chars=cfg.max_chars_per_chunk)):
                anonymized_text, entities = anonymizer.anonymize(chunk)
                record = {
                    "doc_id": file_id,
                    "source_path": str(file_path),
                    "file_sha256": file_hash,
                    "file_type": "pdf",
                    "page_number": page_index + 1,
                    "chunk_index": chunk_index,
                    "text": anonymized_text,
                    "entities": entities,
                }
                writer.write(record)

    elif ext in {".xlsx", ".xls", ".xlsm"}:
        text_stream = extract_text_from_excel(file_path)
        buffer = []
        current_len = 0
        chunk_counter = 0
        for line in text_stream:
            if line:
                buffer.append(line)
                current_len += len(line) + 1
            if current_len >= cfg.max_chars_per_chunk:
                chunk = "\n".join(buffer)
                anonymized_text, entities = anonymizer.anonymize(chunk)
                writer.write({
                    "doc_id": file_id,
                    "source_path": str(file_path),
                    "file_sha256": file_hash,
                    "file_type": "excel",
                    "page_number": None,
                    "chunk_index": chunk_counter,
                    "text": anonymized_text,
                    "entities": entities,
                })
                buffer = []
                current_len = 0
                chunk_counter += 1
        if buffer:
            chunk = "\n".join(buffer)
            anonymized_text, entities = anonymizer.anonymize(chunk)
            writer.write({
                "doc_id": file_id,
                "source_path": str(file_path),
                "file_sha256": file_hash,
                "file_type": "excel",
                "page_number": None,
                "chunk_index": chunk_counter,
                "text": anonymized_text,
                "entities": entities,
            })

    else:
        logger.warning(f"Unsupported file type: {file_path}")


if __name__ == "__main__":
    app()