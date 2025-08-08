import hashlib
import json
import gzip
from pathlib import Path
from typing import Dict, List


SUPPORTED_EXTS = {".pdf", ".xlsx", ".xls", ".xlsm"}


def discover_input_files(path: Path) -> List[Path]:
    results: List[Path] = []
    if path.is_file():
        if path.suffix.lower() in SUPPORTED_EXTS:
            results.append(path)
        return results
    for p in path.rglob("*"):
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
            results.append(p)
    return sorted(results)


def compute_file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class CompressedJsonlWriter:
    def __init__(self, path: Path, level: int = 9):
        self.path = Path(path)
        self.level = level
        self._fh = None

    def __enter__(self):
        # Ensure .gz extension if not provided
        if self.path.suffix.lower() not in {".gz"}:
            self.path = self.path.with_suffix(self.path.suffix + ".gz")
        self._fh = gzip.open(self.path, mode="wt", compresslevel=self.level, encoding="utf-8")
        return self

    def write(self, obj: Dict):
        data = json.dumps(obj, ensure_ascii=False)
        self._fh.write(data + "\n")

    def __exit__(self, exc_type, exc, tb):
        if self._fh:
            self._fh.flush()
            self._fh.close()