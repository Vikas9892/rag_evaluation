from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

RAW_DATA_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DATA_DIR = BASE_DIR / "data" / "processed"
INDEX_DIR = BASE_DIR / "index"
LOG_DIR = BASE_DIR / "logs"

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown"}

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
CHUNK_SIZE = 512
CHUNK_OVERLAP = 64
TOP_K = 5
