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
CHUNK_SIZE = 250
CHUNK_OVERLAP = 50
# Chunks shorter than this are merged into their neighbour rather than indexed
# on their own. Splitting on headings otherwise emits heading-only chunks
# ("## ACID Properties"), which match a query's phrasing while carrying none of
# the answer. Clamped to CHUNK_SIZE // 2 at runtime so it can never cascade.
MIN_CHUNK_CHARS = 50
# Heading separators come first so a chunk aligns to one concept rather than
# straddling several sections; paragraph/sentence/word fallbacks follow.
SEPARATORS = ["\n## ", "\n### ", "\n\n", "\n", ". ", " ", ""]
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

# Browser origins allowed to call the API. The frontend calls FastAPI directly
# (ADR 008), so this is the only thing standing between a public endpoint that
# spends Groq budget and any page on the internet. Comma-separated; override
# with the ALLOWED_ORIGINS environment variable in deployment.
DEFAULT_ALLOWED_ORIGINS = ["http://localhost:3000"]

REPORTS_DIR = BASE_DIR / "reports"
DATASET_PATH = BASE_DIR / "evaluation" / "dataset.json"
