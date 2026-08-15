"""Safe handling of uploaded files.

Everything here treats the filename as hostile. It arrives from a browser, it is
attacker-controlled, and it is the input to a filesystem write — which is the
exact shape of a path-traversal bug.
"""

import hashlib
import re
import unicodedata
import uuid
from pathlib import Path
from typing import BinaryIO, Tuple

from config.settings import INDEX_DIR

UPLOAD_ROOT = INDEX_DIR / "uploads"

#: Formats the existing parsers handle. Nothing else is accepted, because
#: accepting a format with no parser produces a document that can never leave
#: PARSING.
SUPPORTED_SUFFIXES = {".pdf", ".txt", ".md", ".markdown"}

#: 25 MB. Large enough for a real handbook, small enough that a single upload
#: cannot exhaust the disk or block the worker for minutes.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class UnsupportedFileType(ValueError):
    """The extension has no parser behind it."""


class FileTooLarge(ValueError):
    """Above MAX_UPLOAD_BYTES."""


class EmptyFile(ValueError):
    """Zero bytes — there is nothing to index."""


def safe_display_name(filename: str) -> str:
    """A filename fit to store and show, derived from an untrusted one.

    Only the final component is kept, so `../../etc/passwd` becomes `passwd`.
    Unicode is normalised and anything outside a conservative set is replaced,
    which also removes the separators, null bytes and control characters that
    make a name dangerous in a path or a header.

    This is for display and for the stored copy's suffix. It is never the whole
    path: the stored file is named by a generated id, so even a name that
    survives this cannot collide with or overwrite another.
    """
    tail = Path(filename.replace("\\", "/")).name
    normalised = unicodedata.normalize("NFKD", tail)
    # Control characters and null bytes are removed rather than substituted:
    # they carry no display value, and turning them into underscores would let
    # an injected byte show up as a visible character in the stored name.
    without_control = "".join(c for c in normalised if unicodedata.category(c)[0] != "C")
    cleaned = _SAFE_NAME.sub("_", without_control).strip("._")
    # Everything was stripped, or the name was only separators.
    return cleaned[:120] or "upload"


def suffix_of(filename: str) -> str:
    return Path(safe_display_name(filename)).suffix.lower()


def validate(filename: str, size_bytes: int) -> None:
    """Reject what cannot be indexed, before anything is written to disk."""
    if size_bytes <= 0:
        raise EmptyFile("The file is empty")
    if size_bytes > MAX_UPLOAD_BYTES:
        raise FileTooLarge(
            f"{size_bytes / 1024 / 1024:.1f} MB exceeds the "
            f"{MAX_UPLOAD_BYTES // 1024 // 1024} MB limit"
        )
    if suffix_of(filename) not in SUPPORTED_SUFFIXES:
        raise UnsupportedFileType(
            f"{suffix_of(filename) or 'no extension'} is not supported — "
            f"expected one of {', '.join(sorted(SUPPORTED_SUFFIXES))}"
        )


def store(corpus_id: str, document_id: str, filename: str, data: bytes) -> Tuple[Path, str]:
    """Write the upload under a generated name, returning its path and hash.

    The stored name is the document id plus the validated suffix, so nothing
    attacker-controlled forms a path segment. The directory is per corpus, so a
    corpus's files can be removed as a unit.
    """
    directory = UPLOAD_ROOT / corpus_id
    directory.mkdir(parents=True, exist_ok=True)

    path = directory / f"{document_id}{suffix_of(filename)}"
    path.write_bytes(data)

    return path, hashlib.sha256(data).hexdigest()


def new_document_id() -> str:
    return uuid.uuid4().hex


def read_limited(stream: BinaryIO, limit: int = MAX_UPLOAD_BYTES) -> bytes:
    """Read at most limit + 1 bytes.

    The extra byte is what makes an oversized file detectable: reading exactly
    the limit cannot distinguish "at the limit" from "larger and truncated", and
    reading it all would let one request exhaust memory before the size check.
    """
    return stream.read(limit + 1)
