from dataclasses import dataclass, field
from typing import Dict


@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    text: str
    start_char: int
    end_char: int
    metadata: Dict = field(default_factory=dict)
