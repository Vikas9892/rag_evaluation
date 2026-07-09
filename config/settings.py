from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

RAW_DATA_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DATA_DIR = BASE_DIR / "data" / "processed"
INDEX_DIR = BASE_DIR / "index"
LOG_DIR = BASE_DIR / "logs"

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown"}

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
BATCH_SIZE = 32
DEVICE = "cpu"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 100
SEPARATORS = ["\n\n", "\n", ". ", " ", ""]
TOP_K = 5

VECTORS_FILE = INDEX_DIR / "vectors.npy"
METADATA_FILE = INDEX_DIR / "metadata.json"
FAISS_INDEX_FILE = INDEX_DIR / "faiss.index"

LLM_MODEL = "llama-3.1-8b-instant"
LLM_TEMPERATURE = 0.0
LLM_MAX_TOKENS = 1024
REQUEST_TIMEOUT = 30.0
MAX_RETRIES = 3
MAX_CONTEXT_CHUNKS = 5
