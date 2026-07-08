from dataclasses import dataclass, field
from typing import Dict


@dataclass
class Document:
    id: str
    source: str
    text: str
    metadata: Dict = field(default_factory=dict)
