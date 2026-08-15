"""Where a corpus's artefacts live on disk.

The evaluation corpus keeps the paths it has always had (`index/faiss.index` and
friends). Everything else lives under `index/corpora/<corpus_id>/`. That is a
deliberate special case: moving the evaluation index would invalidate the
baseline, break CI's build step and make every previously recorded benchmark
number unreproducible, for no benefit.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

from config.settings import FAISS_INDEX_FILE, INDEX_DIR, METADATA_FILE, VECTORS_FILE

#: The corpus the offline pipeline builds and the evaluation harness measures.
DEFAULT_CORPUS_ID = "evaluation"

#: Where non-default corpora live.
CORPORA_DIR = INDEX_DIR / "corpora"

# Corpus ids reach the filesystem, so they are restricted to characters that
# cannot escape a directory or mean something to a shell. This is the only
# defence against `../../etc` arriving as a path segment, so it is a whitelist
# rather than a blacklist.
_VALID_CORPUS_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class InvalidCorpusIdError(ValueError):
    """The id is not a shape this application will put on a filesystem."""


class CorpusNotFoundError(LookupError):
    """No corpus with that id has been indexed."""


def is_valid_corpus_id(corpus_id: str) -> bool:
    return bool(_VALID_CORPUS_ID.match(corpus_id))


@dataclass(frozen=True)
class CorpusLayout:
    """The four paths that make up one corpus."""

    corpus_id: str
    root: Path
    vectors_path: Path
    metadata_path: Path
    faiss_path: Path

    @property
    def exists(self) -> bool:
        """Whether this corpus has been indexed.

        Both files, not either: a metadata file without vectors is a half-built
        index that would fail at search time rather than at load time.
        """
        return self.metadata_path.exists() and self.faiss_path.exists()

    @property
    def is_default(self) -> bool:
        return self.corpus_id == DEFAULT_CORPUS_ID


def corpus_layout(corpus_id: str = DEFAULT_CORPUS_ID) -> CorpusLayout:
    """Resolve a corpus id to its paths.

    Raises InvalidCorpusIdError rather than sanitising a bad id. Silently
    rewriting `../../etc/passwd` into something safe hides an attack; refusing
    it surfaces one.
    """
    if not is_valid_corpus_id(corpus_id):
        raise InvalidCorpusIdError(
            f"Invalid corpus id {corpus_id!r}: expected lowercase letters, digits, "
            "'-' or '_', starting with a letter or digit, at most 64 characters."
        )

    if corpus_id == DEFAULT_CORPUS_ID:
        # Unchanged paths, so the evaluation baseline stays reproducible.
        return CorpusLayout(
            corpus_id=corpus_id,
            root=Path(INDEX_DIR),
            vectors_path=Path(VECTORS_FILE),
            metadata_path=Path(METADATA_FILE),
            faiss_path=Path(FAISS_INDEX_FILE),
        )

    root = CORPORA_DIR / corpus_id
    return CorpusLayout(
        corpus_id=corpus_id,
        root=root,
        vectors_path=root / "vectors.npy",
        metadata_path=root / "metadata.json",
        faiss_path=root / "faiss.index",
    )


def list_corpus_ids() -> List[str]:
    """Every corpus that has actually been indexed, default first.

    Directories that exist but hold no index are omitted: a corpus whose
    indexing failed half way through should not be offered as somewhere to
    search.
    """
    found: List[str] = []
    if corpus_layout(DEFAULT_CORPUS_ID).exists:
        found.append(DEFAULT_CORPUS_ID)

    if CORPORA_DIR.is_dir():
        for child in sorted(CORPORA_DIR.iterdir()):
            if not child.is_dir() or not is_valid_corpus_id(child.name):
                continue
            if corpus_layout(child.name).exists:
                found.append(child.name)

    return found
