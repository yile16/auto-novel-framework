"""Text chunking — split novel text by chapters with token-awareness."""

import re
from dataclasses import dataclass


# Approximate: Chinese characters ≈ 0.5 tokens each, English words ≈ 1.3 tokens
def estimate_tokens(text: str) -> int:
    """Estimate token count for mixed Chinese/English text."""
    chinese_chars = len(re.findall(r'[一-鿿]', text))
    other_chars = len(text) - chinese_chars
    return int(chinese_chars * 0.6 + other_chars * 0.25)


@dataclass
class Chunk:
    index: int
    chapter_start: int
    chapter_end: int
    title: str
    text: str
    estimated_tokens: int


def split_by_chapter(text: str, max_tokens: int = 8000, overlap_tokens: int = 500) -> list[Chunk]:
    """
    Split novel text into chunks by chapter boundaries.

    Detects chapter headers via common patterns:
    - 第X章, 第X回, Chapter X, 卷一·第X章, etc.

    Long chapters (> max_tokens) are further split by paragraphs with overlap.
    """
    # Detect chapter boundaries
    chapter_pattern = re.compile(
        r'(?:^|\n)\s*'
        r'(?:第[零一二三四五六七八九十百千万\d]+[章回卷节]|'
        r'Chapter\s+\d+|'
        r'CH\s*\d+|'
        r'[Vv]olume\s+\d+)'
        r'.*?(?:\n|$)',
        re.MULTILINE,
    )

    boundaries = list(chapter_pattern.finditer(text))

    if not boundaries:
        # No chapter markers found — treat as single chunk, split by size
        return _split_long_text(text, max_tokens, overlap_tokens, start_ch=1, end_ch=1)

    chunks: list[Chunk] = []
    chunk_index = 0

    for i, match in enumerate(boundaries):
        start = match.start()
        end = boundaries[i + 1].start() if i + 1 < len(boundaries) else len(text)
        ch_text = text[start:end].strip()
        ch_num = i + 1
        title_line = match.group().strip()

        if estimate_tokens(ch_text) <= max_tokens:
            chunks.append(Chunk(
                index=chunk_index,
                chapter_start=ch_num,
                chapter_end=ch_num,
                title=title_line,
                text=ch_text,
                estimated_tokens=estimate_tokens(ch_text),
            ))
            chunk_index += 1
        else:
            # Long chapter — split by paragraphs
            sub_chunks = _split_long_text(
                ch_text, max_tokens, overlap_tokens,
                start_ch=ch_num, end_ch=ch_num,
                base_title=title_line,
                start_index=chunk_index,
            )
            chunks.extend(sub_chunks)
            chunk_index += len(sub_chunks)

    return chunks


def _split_long_text(
    text: str,
    max_tokens: int,
    overlap_tokens: int,
    start_ch: int,
    end_ch: int,
    base_title: str = "",
    start_index: int = 0,
) -> list[Chunk]:
    """Split a long text by paragraphs, keeping token budget with overlap."""
    paragraphs = text.split("\n\n")
    chunks: list[Chunk] = []
    current: list[str] = []
    current_tokens = 0
    chunk_idx = start_index

    for para in paragraphs:
        para_tokens = estimate_tokens(para)

        if current_tokens + para_tokens > max_tokens and current:
            # Flush current chunk
            chunk_text = "\n\n".join(current)
            if base_title:
                label = f"{base_title} (part {len(chunks) + 1})"
            else:
                label = ""
            chunks.append(Chunk(
                index=chunk_idx,
                chapter_start=start_ch,
                chapter_end=end_ch,
                title=label,
                text=chunk_text,
                estimated_tokens=estimate_tokens(chunk_text),
            ))
            chunk_idx += 1

            # Start new chunk with overlap: keep last few paragraphs
            overlap_text = ""
            overlap_count = 0
            for p in reversed(current):
                if estimate_tokens(overlap_text + p) <= overlap_tokens:
                    overlap_text = p + "\n\n" + overlap_text
                    overlap_count += 1
                else:
                    break
            current = [overlap_text.strip(), para] if overlap_text.strip() else [para]
            current_tokens = estimate_tokens("\n\n".join(current))
        else:
            current.append(para)
            current_tokens += para_tokens

    # Flush remaining
    if current:
        chunk_text = "\n\n".join(current)
        if base_title:
            label = f"{base_title} (part {len(chunks) + 1})"
        else:
            label = ""
        chunks.append(Chunk(
            index=chunk_idx,
            chapter_start=start_ch,
            chapter_end=end_ch,
            title=label,
            text=chunk_text,
            estimated_tokens=estimate_tokens(chunk_text),
        ))

    return chunks
