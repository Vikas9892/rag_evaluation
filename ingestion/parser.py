from abc import ABC, abstractmethod
from pathlib import Path
from typing import Tuple, Dict


class BaseParser(ABC):
    @abstractmethod
    def parse(self, filepath: Path) -> Tuple[str, Dict]:
        """Return (text, metadata) for the given file."""


class PDFParser(BaseParser):
    def parse(self, filepath: Path) -> Tuple[str, Dict]:
        import fitz  # PyMuPDF

        doc = fitz.open(str(filepath))
        text = "".join(page.get_text() for page in doc)
        metadata = {
            "type": "pdf",
            "pages": len(doc),
            "size": filepath.stat().st_size,
        }
        doc.close()
        return text, metadata


class TXTParser(BaseParser):
    def parse(self, filepath: Path) -> Tuple[str, Dict]:
        text = filepath.read_text(encoding="utf-8", errors="replace")
        return text, {
            "type": "txt",
            "size": filepath.stat().st_size,
        }


class MarkdownParser(BaseParser):
    def parse(self, filepath: Path) -> Tuple[str, Dict]:
        text = filepath.read_text(encoding="utf-8", errors="replace")
        return text, {
            "type": "markdown",
            "size": filepath.stat().st_size,
        }


PARSER_REGISTRY: Dict[str, BaseParser] = {
    ".pdf": PDFParser(),
    ".txt": TXTParser(),
    ".md": MarkdownParser(),
    ".markdown": MarkdownParser(),
}
