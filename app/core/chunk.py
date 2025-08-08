from typing import Iterator


def chunk_text(text: str, max_chars: int = 4000) -> Iterator[str]:
    """Yield text in chunks not exceeding max_chars, breaking on paragraph or sentence boundaries when possible."""
    if not text:
        return
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    current = []
    current_len = 0

    def flush():
        nonlocal current, current_len
        if current:
            yield_text = "\n\n".join(current).strip()
            if yield_text:
                yield yield_text
            current = []
            current_len = 0

    for para in paragraphs:
        if len(para) > max_chars:
            # hard split long paragraphs
            start = 0
            while start < len(para):
                end = min(start + max_chars, len(para))
                piece = para[start:end]
                if piece.strip():
                    if current:
                        yield from flush()
                    yield piece
                start = end
            continue
        if current_len + len(para) + (2 if current else 0) > max_chars:
            yield from flush()
        current.append(para)
        current_len += len(para) + (2 if current_len > 0 else 0)

    # final flush
    if current:
        yield "\n\n".join(current).strip()