from dataclasses import dataclass, field
from typing import Dict


@dataclass
class Chunk:
    """One indexed unit of text.

    `document_id` is the source: it is the filename the chunk was parsed from,
    so a citation can name the document without a second lookup.

    `corpus_id` scopes the chunk to one collection. It is last and defaulted so
    that every existing construction — the offline pipeline, the evaluation
    fixtures, the tests — keeps working unchanged and lands in the evaluation
    corpus, which is where it was already going.
    """

    chunk_id: str
    document_id: str
    text: str
    start_char: int
    end_char: int
    metadata: Dict = field(default_factory=dict)
    corpus_id: str = "evaluation"
