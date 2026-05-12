"""File I/O for reading novel files (.txt, .epub)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class NovelFile:
    """Represents a loaded novel file."""
    path: Path
    title: str
    author: str
    text: str


def read_novel(filepath: str | Path) -> NovelFile:
    """
    Read a novel file. Supports .txt and .epub formats.
    Returns a NovelFile with title, author, and full text.
    """
    path = Path(filepath)
    suffix = path.suffix.lower()

    if suffix == ".txt":
        text = path.read_text(encoding="utf-8")
        title = path.stem
        author = ""
        # Try to extract title/author from first lines
        lines = text.strip().split("\n")
        for line in lines[:5]:
            line = line.strip()
            if line.startswith("书名") or line.startswith("《"):
                title = line.replace("书名：", "").replace("书名:", "").strip()
            if line.startswith("作者"):
                author = line.replace("作者：", "").replace("作者:", "").strip()

    elif suffix == ".epub":
        try:
            import ebooklib
            from ebooklib import epub
        except ImportError:
            raise ImportError(
                "ebooklib is required to read .epub files. "
                "Install it with: pip install ebooklib"
            )

        book = epub.read_epub(str(path))
        title = book.get_metadata("DC", "title")
        title = title[0][0] if title else path.stem
        author = book.get_metadata("DC", "creator")
        author = author[0][0] if author else ""

        # Extract text from all document items
        from bs4 import BeautifulSoup
        parts = []
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            soup = BeautifulSoup(item.get_body_content(), "html.parser")
            parts.append(soup.get_text())
        text = "\n\n".join(parts)

    else:
        raise ValueError(f"Unsupported file format: {suffix}. Supported: .txt, .epub")

    return NovelFile(path=path, title=title, author=author, text=text)
