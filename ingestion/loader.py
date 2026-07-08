from pathlib import Path
from typing import List

from config.logging_config import get_logger
from ingestion.cleaner import TextCleaner
from ingestion.document import Document
from ingestion.parser import PARSER_REGISTRY

logger = get_logger(__name__)


class DocumentLoader:
    """Walks a directory, dispatches each file to the right parser, and returns
    a list of cleaned Document objects.  One bad file never stops the pipeline.
    """

    def __init__(self, raw_dir: str | Path):
        self.raw_dir = Path(raw_dir)
        self.cleaner = TextCleaner()

    def load(self) -> List[Document]:
        if not self.raw_dir.exists():
            raise FileNotFoundError(f"Raw data directory not found: {self.raw_dir}")

        all_files = [p for p in self.raw_dir.rglob("*") if p.is_file()]
        logger.info("Found %d file(s) in %s", len(all_files), self.raw_dir)

        documents: List[Document] = []
        for filepath in all_files:
            doc = self._process_file(filepath)
            if doc is not None:
                documents.append(doc)

        logger.info("Successfully ingested %d document(s)", len(documents))
        return documents

    def _process_file(self, filepath: Path):
        ext = filepath.suffix.lower()
        parser = PARSER_REGISTRY.get(ext)

        if parser is None:
            logger.warning("Unsupported file type, skipping: %s", filepath.name)
            return None

        try:
            raw_text, metadata = parser.parse(filepath)
            clean_text = self.cleaner.clean(raw_text)
            metadata["source"] = filepath.name
            doc = Document(
                id=filepath.name,
                source=str(filepath),
                text=clean_text,
                metadata=metadata,
            )
            logger.info("Loaded %s", filepath.name)
            return doc
        except Exception as exc:
            logger.error("Failed to parse %s: %s", filepath.name, exc)
            return None
